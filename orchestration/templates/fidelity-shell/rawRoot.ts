/**
 * splitRoot — parse a single-root HTML fragment into { tag, attrs, inner } so a
 * view can render the REAL root element (createElement) with the inner markup
 * as dangerouslySetInnerHTML. A display:contents wrapper is layout-transparent
 * but NOT selector-transparent: `.parent > section` and `section + section`
 * CSS rules stop matching through it (measured: 128px of lost section spacing).
 * Rendering the actual root element restores child/sibling selector semantics.
 * Returns null for multi-root/text fragments (caller falls back to a wrapper).
 */
export type RootSplit = { tag: string; attrs: Record<string, string>; inner: string };

export function splitRoot(html: string): RootSplit | null {
  const s = (html ?? "").trim();
  const m = /^<([a-zA-Z][\w-]*)/.exec(s);
  if (!m) return null;
  const tag = m[1].toLowerCase();
  // scan to the end of the opening tag, honoring quoted attribute values
  let i = m[0].length;
  let quote: string | null = null;
  for (; i < s.length; i++) {
    const ch = s[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === ">") {
      break;
    }
  }
  if (i >= s.length) return null;
  const attrStr = s.slice(m[0].length, i);
  const close = `</${tag}>`;
  if (!s.toLowerCase().endsWith(close)) return null;
  const inner = s.slice(i + 1, s.length - close.length);
  // the fragment must have exactly ONE root: if the inner closes the root early
  // (sibling roots), bail out to the wrapper fallback
  let depth = 1;
  const re = new RegExp(`<(/?)${tag}(?=[\\s>/])`, "gi");
  for (const t of inner.matchAll(re)) {
    depth += t[1] ? -1 : 1;
    if (depth === 0) return null;
  }
  const attrs: Record<string, string> = {};
  for (const a of attrStr.matchAll(/([\w:-]+)(?:\s*=\s*"([^"]*)"|\s*=\s*'([^']*)')?/g)) {
    attrs[a[1]] = a[2] ?? a[3] ?? "";
  }
  return { tag, attrs, inner };
}

/** Source attributes -> React DOM props (class -> className; style STRING
 * parsed into a React style object — dropping it erased every inline
 * background-image hero on wrappers that host {{child:N}} components
 * (2026-07-20: enterprise navy hero rendered white). Crawler-flattened
 * at-rules inside the attribute (invalid inline CSS) are cut at the first
 * `@` — browsers error-recover past them, React needs a clean object. */
export function rootProps(attrs: Record<string, string>): Record<string, unknown> {
  const { class: cls, style, ...rest } = attrs;
  const out: Record<string, unknown> = { ...rest };
  if (cls) out.className = cls;
  if (style) {
    const clean = style.split("@")[0];
    const obj: Record<string, string> = {};
    for (const decl of clean.split(";")) {
      const i = decl.indexOf(":");
      if (i < 1) continue;
      const prop = decl.slice(0, i).trim();
      const val = decl.slice(i + 1).trim();
      if (!prop || !val) continue;
      const key = prop.startsWith("--")
        ? prop
        : prop.replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase());
      obj[key] = val;
    }
    if (Object.keys(obj).length) out.style = obj;
  }
  return out;
}
