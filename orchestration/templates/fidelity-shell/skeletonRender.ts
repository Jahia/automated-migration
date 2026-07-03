/**
 * skeletonRender — shared server-side skeleton composition (QUALITY-PLAN P2.5/C).
 *
 * A skeleton node's `skeleton` property is its OWN captured markup where:
 *   {{f:title}} / {{f:body*}} / {{f:linkLabel}}  lifted text values
 *   {{media:imageN}}                             a whole <picture>/<img> unit
 *   {{link:href}}                                the contributor link target
 *   {{child:N}}                                  the N-th item child node
 *
 * Substitution rules MIRROR the extractor's recompose_group() — the render of
 * an unedited node must be byte-identical to the captured source:
 *   - body* values splice RAW (they are richtext HTML)
 *   - other field values are minimal-escaped (&, <, > — quotes stay raw)
 *   - a media unit renders its ORIGINAL markup verbatim while the weakref
 *     still points at the DAM copy of the original file (imageNOrigRef);
 *     once an editor picks another image, the chosen one must WIN: <source>
 *     elements and srcset are dropped, the <img> src becomes the node URL
 *   - {{link:href}} <- j:url (external) | j:linknode URL (internal) |
 *     linkOrig (unresolved fallback), attribute-escaped
 */

type JCRProp = {
  getName: () => string;
  getString: () => string;
  getNode: () => JCRNode;
};
type JCRNode = {
  getName: () => string;
  getIdentifier: () => string;
  getUrl: () => string;
  getProperties: () => { hasNext: () => boolean; nextProperty: () => JCRProp };
  getNodes: () => { hasNext: () => boolean; nextNode: () => JCRNode };
};

export const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
export const escapeAttr = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

type Media = { name: string; orig: string; url: string | null; edited: boolean };
type Payload = {
  skeleton: string;
  values: Record<string, string>;
  media: Media[];
  linkHref: string | null;
};

/** Read a skeleton node's payload through the localized JCR session (i18n
 * props resolve to the current locale; works for the current node AND items). */
export function nodePayload(node: JCRNode): Payload {
  const values: Record<string, string> = {};
  const origs: Record<string, string> = {};
  const origRefs: Record<string, string> = {};
  const chosen: Record<string, JCRNode> = {};
  let skeleton = "";
  let jUrl = "";
  let linkOrig = "";
  let linknodeUrl = "";
  try {
    const it = node.getProperties();
    while (it.hasNext()) {
      const p = it.nextProperty();
      let name = "";
      try {
        name = String(p.getName());
      } catch {
        continue;
      }
      try {
        if (name === "skeleton") skeleton = p.getString();
        else if (name === "jcr:title") values.title = p.getString();
        else if (name === "linkLabel") values.linkLabel = p.getString();
        else if (name === "body" || /^body\d+$/.test(name)) values[name] = p.getString();
        else if (/^image\d*Orig$/.test(name)) origs[name.replace(/Orig$/, "")] = p.getString();
        else if (/^image\d*OrigRef$/.test(name)) origRefs[name.replace(/OrigRef$/, "")] = p.getString();
        else if (/^image\d*$/.test(name)) chosen[name] = p.getNode();
        else if (name === "j:url") jUrl = p.getString();
        else if (name === "linkOrig") linkOrig = p.getString();
        else if (name === "j:linknode") linknodeUrl = p.getNode().getUrl();
      } catch {
        /* unreadable prop (broken weakref…) — fall back to the verbatim default */
      }
    }
  } catch {
    /* not a JCR content node */
  }
  const media: Media[] = Object.keys(origs).map((name) => {
    const img = chosen[name];
    let edited = false;
    let url: string | null = null;
    try {
      if (img) {
        url = img.getUrl();
        edited = Boolean(origRefs[name]) && img.getIdentifier() !== origRefs[name];
      }
    } catch {
      edited = false;
    }
    return { name, orig: origs[name], url, edited };
  });
  return { skeleton, values, media, linkHref: jUrl || linknodeUrl || linkOrig || null };
}

/** Edited media render: the chosen image must win — drop <source>/srcset,
 * swap the <img> src, keep every other attribute (classes, dimensions, alt). */
const editedMedia = (orig: string, url: string): string =>
  orig
    .replace(/<source\b[^>]*\/?>/gi, "")
    .replace(/\s+srcset="[^"]*"/gi, "")
    .replace(/(<img\b[^>]*?\bsrc=")[^"]*(")/i, (_a, pre, post) => pre + escapeAttr(url) + post);

const substitute = (p: Payload): string => {
  let html = p.skeleton;
  for (const m of p.media) {
    const marker = `{{media:${m.name}}}`;
    if (html.includes(marker)) {
      html = html.split(marker).join(!m.edited || !m.url ? m.orig : editedMedia(m.orig, m.url));
    }
  }
  if (html.includes("{{link:href}}")) {
    html = html.split("{{link:href}}").join(escapeAttr(p.linkHref ?? ""));
  }
  for (const [k, v] of Object.entries(p.values)) {
    if (typeof v !== "string" || !v) continue;
    const marker = `{{f:${k}}}`;
    if (html.includes(marker)) {
      html = html.split(marker).join(k.startsWith("body") ? v : escapeHtml(v));
    }
  }
  return html;
};

/** Full composition: substitute this node's markers, then splice item children
 * into {{child:N}} slots in document order. Items added beyond the original
 * count render after the last slot; deleted items drop out. Leftover markers
 * are stripped. */
export function composeNode(node: JCRNode): string {
  const p = nodePayload(node);
  let html = substitute(p);
  if (html.includes("{{child:")) {
    const rendered: string[] = [];
    try {
      const it = node.getNodes();
      while (it.hasNext()) {
        const child = it.nextNode();
        if (String(child.getName()).startsWith("j:")) continue; // translations/acl
        const cp = nodePayload(child);
        if (cp.skeleton) rendered.push(substitute(cp));
      }
    } catch {
      /* no readable children */
    }
    let maxIdx = -1;
    for (const m of html.matchAll(/\{\{child:(\d+)\}\}/g)) {
      maxIdx = Math.max(maxIdx, Number(m[1]));
    }
    const extras = rendered.slice(maxIdx + 1).join("");
    html = html.replace(/\{\{child:(\d+)\}\}/g, (_all, n) => {
      const i = Number(n);
      return (rendered[i] ?? "") + (i === maxIdx ? extras : "");
    });
  }
  return html.replace(/\{\{(?:f|media|link):[^}]+\}\}/g, "");
}
