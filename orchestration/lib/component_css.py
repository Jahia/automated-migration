#!/usr/bin/env python3
"""component_css.py — per-component CSS capture (operator mandate, 2026-07-16).

When a component is captured from the source DOM, the CSS that styles it must
live WITH the component: this reads every component's captured markup (skeleton
+ classMap + rich-text field HTML) from the content-load, aggregates the class
set per component type, extracts the matching rules from the CAPTURED source
stylesheets (local-mirror assets + inline-head), and writes them into the
component's SDC folder as `component.module.css` (selectors wrapped
`:global(...)` so the source class names the views wear keep matching). Every
`*.server.tsx` view in the folder gets an `import "./component.module.css"`.

Mapping is by LOCAL type name: each SDC folder's own definition.cnd declares
its primary type — the manifest's instanceTypeMap has drifted namespaces
before (sgpnt: vs sgp:) and is not trusted here.

Usage: component_css.py <project> [--check]
  --check  gate mode: every SDC folder whose type has captured classes must
           hold a non-empty component.module.css whose selectors intersect
           the captured class set, imported by every *.server.tsx view.
Exit 0 clean / 1 violations.
"""
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# at-rules that are page-global by nature — they stay in the site-wide CSS
_SKIP_AT = ("@font-face", "@keyframes", "@-webkit-keyframes", "@import",
            "@charset", "@page", "@counter-style", "@property")


def _class_tokens_of_selector(sel):
    """Unescaped class names used by a selector (Tailwind escapes: .lg\\:flex)."""
    out = set()
    for m in re.finditer(r"\.((?:\\.|[A-Za-z0-9_-])+)", sel):
        out.add(m.group(1).replace("\\", ""))
    return out


def _class_tokens_of_html(html):
    """All class attribute tokens in a markup string."""
    out = set()
    for m in re.finditer(r'class="([^"]*)"', html or ""):
        out.update(t for t in m.group(1).split() if t)
    return out


def parse_rules(css):
    """[(media_or_None, selector, body)] — brace-walking parser that survives
    minified output and one level of @media/@supports nesting."""
    rules, i, n = [], 0, len(css)

    def _block(start):
        depth, j = 1, start
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        return css[start:j - 1], j

    def _walk(s, media):
        k, ln = 0, len(s)
        while k < ln:
            b = s.find("{", k)
            if b < 0:
                break
            sel = s[k:b].strip()
            depth, j = 1, b + 1
            while j < ln and depth:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                j += 1
            body = s[b + 1:j - 1]
            if sel.startswith(("@media", "@supports", "@container")):
                _walk(body, f"{media} and {sel}" if media else sel)
            elif sel.startswith("@layer") and "{" not in sel:
                # Tailwind v4 wraps every utility in @layer — transparent wrapper
                # (dropping it silently discarded the whole utilities layer)
                _walk(body, media)
            elif sel.startswith(_SKIP_AT) or sel.startswith("@"):
                pass
            elif sel:
                rules.append((media, sel, body.strip()))
            k = j
        return

    # strip comments once
    _walk(re.sub(r"/\*.*?\*/", "", css, flags=re.S), None)
    return rules


def _split_selectors(sel):
    """Split a selector list at TOP-LEVEL commas only — escaped commas
    (Tailwind `.transition-\\[color\\,box-shadow\\]`) and commas inside
    (), [] (`:is(a, b)`) belong to a single selector."""
    parts, buf, depth, i = [], [], 0, 0
    while i < len(sel):
        c = sel[i]
        if c == "\\" and i + 1 < len(sel):
            buf.append(sel[i:i + 2])
            i += 2
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth = max(depth - 1, 0)
        if c == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _globalize(sel):
    """Wrap each top-level selector in :global(...) so CSS-module scoping keeps
    the literal source class names the views render."""
    return ", ".join(f":global({p})" for p in _split_selectors(sel))


def _folder_types(comp_root):
    """SDC folder -> local type name (lowercased), read from its definition.cnd."""
    out = {}
    if not os.path.isdir(comp_root):
        return out
    for d in sorted(os.listdir(comp_root)):
        cnd = os.path.join(comp_root, d, "definition.cnd")
        if not os.path.isfile(cnd):
            continue
        m = re.search(r"^\[\s*\w+:(\w+)\s*\]", open(cnd, encoding="utf-8").read(), re.M)
        if m:
            out[d] = m.group(1).lower()
    return out


def _captured_classes(project, site):
    """local type name (lowercased) -> class set, read from the LIVE JCR:
    every loaded node carrying the sourceMarkup mixin, with its CONCRETE
    primary type and its captured markup (skeleton/skeletonOrig/classMap/body).
    The content-load's instance `type` is a pre-resolution role name (the
    loader picks the concrete node type later) — the JCR is the truth of what
    each component actually wears."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcp_client import MCP
    m = MCP(project)
    # namespace from the DEPLOYED settings CND — manifests have carried stale
    # namespaces (sgpnt: while the emitted module is sgp:, observed 2026-07-16)
    ns = None
    try:
        cnd = open(f"{REPO}/projects/{project}/settings/definitions.cnd",
                   encoding="utf-8").read()
        mm = re.search(r"^\[(\w+)mix:sourceMarkup\]", cnd, re.M)
        ns = mm.group(1) if mm else None
    except OSError:
        pass
    if not ns:
        print("FAIL: component-css — cannot determine module namespace "
              "(no [<ns>mix:sourceMarkup] in settings/definitions.cnd)", file=sys.stderr)
        sys.exit(1)
    r = m.gql("""{ jcr(workspace: EDIT) { nodeByPath(path: "/sites/""" + site + """") {
      descendants(typesFilter:{types:[\"""" + ns + """mix:sourceMarkup"]}) { nodes {
        primaryNodeType { name }
        properties(names:["skeleton","skeletonOrig","classMap","body"]) {
          name value } } } } } }""")
    nodes = (((r.get("jcr") or {}).get("nodeByPath") or {})
             .get("descendants") or {}).get("nodes") or []
    by_type = {}
    for n in nodes:
        t = n["primaryNodeType"]["name"].split(":")[-1].lower()
        acc = by_type.setdefault(t, set())
        for p in (n.get("properties") or []):
            v = p.get("value") or ""
            if p["name"] == "classMap" and v.strip().startswith("{"):
                try:
                    for cv in json.loads(v).values():
                        acc.update(str(cv).split())
                except ValueError:
                    pass
            else:
                acc |= _class_tokens_of_html(v)
    return by_type


def _source_rules(project):
    """Parsed rules from every captured source stylesheet (deduped by basename)."""
    seen, rules = set(), []
    for d in (f"{REPO}/projects/{project}/workflow-output/local-mirror/assets",
              f"{REPO}/projects/{project}/static/assets"):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".css") or fn in seen:
                continue
            seen.add(fn)
            rules += parse_rules(open(os.path.join(d, fn), encoding="utf-8",
                                      errors="replace").read())
    return rules


def _emit(project, site, check=False):
    comp_root = f"{REPO}/projects/{project}/src/components"
    folders = _folder_types(comp_root)
    classes = _captured_classes(project, site)
    rules = _source_rules(project)
    if not rules:
        print("FAIL: component-css — no source stylesheet rules found "
              "(a gate that cannot measure must fail)", file=sys.stderr)
        sys.exit(1)
    bad, written = [], 0

    for folder, tname in folders.items():
        cset = classes.get(tname) or set()
        fdir = os.path.join(comp_root, folder)
        css_path = os.path.join(fdir, "component.module.css")
        views = [f for f in os.listdir(fdir) if f.endswith(".server.tsx")]
        if not cset:
            continue  # structural/fresh types with no captured markup
        matched = [(m, s, b) for (m, s, b) in rules
                   if _class_tokens_of_selector(s) & cset]
        if check:
            if not os.path.isfile(css_path) or not open(css_path).read().strip():
                bad.append(f"{folder}: captured {len(cset)} classes but no component.module.css")
                continue
            have = _class_tokens_of_selector(open(css_path, encoding="utf-8").read())
            if matched and not (have & cset):
                bad.append(f"{folder}: component.module.css selectors match none of the "
                           f"captured classes")
            for v in views:
                if "component.module.css" not in open(os.path.join(fdir, v),
                                                      encoding="utf-8").read():
                    bad.append(f"{folder}/{v}: view does not import component.module.css")
            continue
        # ── write mode ──────────────────────────────────────────────────────
        out = [f"/* component.module.css — CAPTURED source CSS for {folder}",
               f"   ({len(cset)} captured classes, {len(matched)} matching rules).",
               "   Extracted per-component from the mirrored source stylesheets;",
               "   :global() keeps the literal source class names the views wear. */"]
        plain = [(s, b) for (m, s, b) in matched if not m]
        medias = {}
        for m, s, b in matched:
            if m:
                medias.setdefault(m, []).append((s, b))
        for s, b in plain:
            out.append(f"{_globalize(s)} {{ {b} }}")
        for m in sorted(medias):
            out.append(f"{m} {{")
            for s, b in medias[m]:
                out.append(f"  {_globalize(s)} {{ {b} }}")
            out.append("}")
        with open(css_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        written += 1
        for v in views:
            vp = os.path.join(fdir, v)
            src = open(vp, encoding="utf-8").read()
            if "component.module.css" in src:
                continue
            lines = src.splitlines(True)
            last_imp = max((i for i, l in enumerate(lines)
                            if l.startswith("import ")), default=-1)
            lines.insert(last_imp + 1, 'import "./component.module.css";\n')
            open(vp, "w", encoding="utf-8").write("".join(lines))
        print(f"  {folder}: {len(matched)} rule(s) for {len(cset)} captured classes"
              f" -> component.module.css (+import in {len(views)} view(s))")

    if check:
        if bad:
            for x in bad[:20]:
                print(f"  - {x}")
            print(f"FAIL: component-css — {len(bad)} violation(s)", file=sys.stderr)
            sys.exit(1)
        n = sum(1 for f, t in folders.items() if classes.get(t))
        print(f"PASS: component-css — {n} component folder(s) carry their captured CSS module")
    else:
        print(f"component_css: {written} component.module.css written under {comp_root}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: component_css.py <project> <site> [--check]")
    _emit(sys.argv[1], sys.argv[2], check="--check" in sys.argv)
