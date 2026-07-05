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

// ── Render-time fragment hardening (fidelity fixes, P5 groundtruth) ──
//
// Every view injects composed markup via dangerouslySetInnerHTML. Two source
// realities break the pixel render if injected raw; both are repaired here on
// the SERVED HTML only (stored content is never rewritten), so the fix survives
// regeneration and needs no re-load of the paused run.
//
// (1) loading="lazy": a below-the-fold lazy <img> never decodes in the render
//     window (the fidelity probe does not scroll), so it collapses to a 0×0 box
//     — measured live: the home brand-logos grid (19 logos) rendered as a blank
//     ~745px void while the reference mirror happened to win the same timing
//     race and showed them. Forcing eager decoding makes below-fold images
//     deterministic on BOTH sides (rule 30b — materialise what a visitor sees).
//     `loading` is invisible to pixels, so this is fidelity-safe.
const stripLazy = (html: string): string =>
  html.replace(/\s+loading=(["'])lazy\1/gi, "");

// (2) A truncated data: URI leaves an <img src="data:…"> with no closing quote
//     and no '>' (observed live: a ~38 KB chatbot data-URI clipped on the JCR
//     write of the `skeleton` property). The browser then swallows every
//     following sibling into the open attribute until the next quote — the
//     footer node and real page content get absorbed and its attributes render
//     as VISIBLE TEXT (`"="" style="display:contents">`). We cannot rebuild the
//     lost bytes, but we terminate the runaway attribute + tag so the broken
//     image stays contained and never corrupts its siblings. Guarded to `data:`
//     values (the only observed failure) so legitimate '<' inside an attribute
//     value is never touched; a no-op when the markup is already well-formed.
const repairUnterminatedDataUri = (html: string): string => {
  if (!html.includes("data:")) return html; // fast path — the failure is rare
  let out = "";
  let i = 0;
  const n = html.length;
  const isDataAttr = (openTag: string) => /=\s*["'][^"']*data:/i.test(openTag);
  while (i < n) {
    const lt = html.indexOf("<", i);
    if (lt === -1) { out += html.slice(i); break; }
    out += html.slice(i, lt);
    if (!/[a-zA-Z/!]/.test(html[lt + 1] || "")) { out += "<"; i = lt + 1; continue; }
    if (html.startsWith("<!--", lt)) {
      const end = html.indexOf("-->", lt);
      const e = end === -1 ? n : end + 3;
      out += html.slice(lt, e); i = e; continue;
    }
    let j = lt + 1;
    let quote: string | null = null;
    let handled = false;
    for (; j < n; j++) {
      const ch = html[j];
      if (quote) {
        if (ch === quote) quote = null;
        else if (ch === "<" && isDataAttr(html.slice(lt, j))) {
          out += html.slice(lt, j) + quote + ">"; // close runaway attr + tag
          i = j; handled = true; break;
        }
      } else if (ch === '"' || ch === "'") quote = ch;
      else if (ch === ">") { out += html.slice(lt, j + 1); i = j + 1; handled = true; break; }
    }
    if (handled) continue;
    if (quote && isDataAttr(html.slice(lt))) { out += html.slice(lt) + quote + ">"; }
    else out += html.slice(lt);
    i = n;
  }
  return out;
};

/** Harden a composed/passthrough fragment before it is injected verbatim into
 * the DOM: force eager image decoding and contain any truncated data: URI. A
 * no-op on already-valid, non-lazy markup (byte-identical LIVE fidelity). */
export const sanitizeFragment = (html: string): string =>
  repairUnterminatedDataUri(stripLazy(html));

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

/** Ordered, editorial child nodes (translations/acl filtered). */
export function childNodesOf(node: JCRNode): JCRNode[] {
  const out: JCRNode[] = [];
  try {
    const it = node.getNodes();
    while (it.hasNext()) {
      const child = it.nextNode();
      if (!String(child.getName()).startsWith("j:")) out.push(child);
    }
  } catch {
    /* no readable children */
  }
  return out;
}

/** Substitute a payload's field/media/link markers (children NOT composed —
 * the edit-mode path renders them through Jahia's pipeline instead). */
export function substitutePayload(p: Payload): string {
  return sanitizeFragment(substitute(p));
}

// ── Edit-mode support: split a fragment into TOP-LEVEL chunks ──
// Page Builder needs a real edit frame per item node, which only Jahia's
// render pipeline provides — so in edit mode the parent view interleaves
// balanced HTML chunks with <Render node={item}/> elements. Chunks are
// balanced BY CONSTRUCTION: markers replaced complete child elements, so at
// the marker-bearing level every sibling is a complete subtree.
const VOID_TAGS = new Set(["area", "base", "br", "col", "embed", "hr", "img",
                           "input", "link", "meta", "param", "source", "track", "wbr"]);
const RAWTEXT_TAGS = new Set(["script", "style", "textarea", "title"]);

export type Chunk = { kind: "html"; html: string } | { kind: "child"; idx: number };

/** End index (exclusive) of the complete element starting at `pos`, or -1. */
const scanElement = (s: string, pos: number): number => {
  const stack: string[] = [];
  let i = pos;
  while (i < s.length) {
    const lt = s.indexOf("<", i);
    if (lt === -1) return stack.length ? -1 : i;
    if (s.startsWith("<!--", lt)) {
      const end = s.indexOf("-->", lt);
      i = end === -1 ? s.length : end + 3;
      if (!stack.length && i > pos) return i;
      continue;
    }
    const m = /^<(\/)?([a-zA-Z][\w-]*)/.exec(s.slice(lt));
    if (!m) {
      i = lt + 1;
      continue;
    }
    // scan to the tag's real '>' honoring quoted attribute values
    let j = lt + m[0].length;
    let quote: string | null = null;
    for (; j < s.length; j++) {
      const ch = s[j];
      if (quote) {
        if (ch === quote) quote = null;
      } else if (ch === '"' || ch === "'") quote = ch;
      else if (ch === ">") break;
    }
    if (j >= s.length) return -1;
    const tag = m[2].toLowerCase();
    const selfClosed = s[j - 1] === "/";
    if (m[1]) {
      // closing tag — tolerant pop
      while (stack.length && stack[stack.length - 1] !== tag) stack.pop();
      stack.pop();
    } else if (!selfClosed && !VOID_TAGS.has(tag)) {
      if (RAWTEXT_TAGS.has(tag)) {
        const close = s.toLowerCase().indexOf(`</${tag}`, j + 1);
        if (close === -1) return -1;
        const gt = s.indexOf(">", close);
        i = gt === -1 ? s.length : gt + 1;
        if (!stack.length) return i;
        continue;
      }
      stack.push(tag);
    }
    i = j + 1;
    if (!stack.length) return i;
  }
  return stack.length ? -1 : i;
};

/** Fragment -> top-level chunks: complete elements/text merged into html
 * chunks; {{child:N}} markers become child chunks; an element whose subtree
 * CONTAINS markers stays its own chunk (the caller recurses into it). */
export function chunkTopLevel(html: string): Chunk[] {
  const chunks: Chunk[] = [];
  let buf = "";
  const flushBuf = () => {
    if (buf) {
      chunks.push({ kind: "html", html: buf });
      buf = "";
    }
  };
  const text = (t: string) => {
    const re = /\{\{child:(\d+)\}\}/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(t))) {
      buf += t.slice(last, m.index);
      flushBuf();
      chunks.push({ kind: "child", idx: Number(m[1]) });
      last = m.index + m[0].length;
    }
    buf += t.slice(last);
  };
  let i = 0;
  while (i < html.length) {
    const lt = html.indexOf("<", i);
    if (lt === -1) {
      text(html.slice(i));
      break;
    }
    if (lt > i) text(html.slice(i, lt));
    const end = scanElement(html, lt);
    if (end === -1) {
      buf += html.slice(lt);
      break;
    }
    const el = html.slice(lt, end);
    if (el.includes("{{child:")) {
      flushBuf();
      chunks.push({ kind: "html", html: el }); // caller recurses into this one
    } else {
      buf += el;
    }
    i = end;
  }
  flushBuf();
  return chunks;
}

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
  return sanitizeFragment(html.replace(/\{\{(?:f|media|link):[^}]+\}\}/g, ""));
}
