#!/usr/bin/env python3
"""install_base_library.py — install the AGNOSTIC P6.1 base component library.

The base library (orchestration/templates/base-library/) is the project-agnostic
palette of typed atoms + composable containers + style mixins generalized from the
DEPLOYED lesalondelaphoto module (MODULARITY-PLAN Pillar 1 / LIBRARY-SPEC). It is
the composable half of the model; it COEXISTS with fidelity-shell's $NS:rawHtml
passthrough (the byte-exact safety net — fidelity-first).

Stamps the library into a project module, substituting the CND namespace only:
  $NS    -> project content prefix (e.g. asr)
  $NSMIX -> project mixin prefix   (e.g. asrmix)

Installs:
  - views  -> src/components/<Component>/{default.server.tsx, *.module.css} + lib.ts
  - CND     appended to settings/definitions.cnd (idempotent: skips types already
            present — the category mixins usually already exist from cnd_emit.py)
  - page templates (home/basic) -> src/templates/Page/  [--templates]
  - resource bundles -> settings/resources/<module>_{en,fr}.properties (appended)
  - UI locales      -> merged into settings/locales/{en,fr}.json
  - static/css/library-tokens.css

DOES NOT deploy, publish, or mutate Jahia — pure file generation (P6.1 scope).

Usage: install_base_library.py <project> --ns NS --nsmix NSMIX [--module-dir DIR]
       [--templates] [--dry-run]
"""
import argparse
import json
import os
import re
import shutil
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "base-library")
TYPE_RE = re.compile(r"^\s*\[([\w$]+:[\w$]+)\]")


def stamp(text, ns, nsmix):
    # $NSMIX must be replaced BEFORE $NS ($NS is a prefix of $NSMIX-free tokens,
    # but $NSMIX contains "$NS" — replace the longer token first).
    return text.replace("$NSMIX", nsmix).replace("$NS", ns)


def cnd_types(text):
    return {m.group(1) for ln in text.splitlines() if (m := TYPE_RE.match(ln))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ns", required=True)
    ap.add_argument("--nsmix", required=True)
    ap.add_argument("--module-dir")
    ap.add_argument("--templates", action="store_true",
                    help="also install home/basic page templates (overwrites)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    module = a.module_dir or f"projects/{a.project}"
    if not os.path.isdir(f"{module}/src"):
        sys.exit(f"FAIL: {module}/src missing (scaffold first)")

    actions = []  # (dst, "write"|"append"|"merge")

    def write(dst, content):
        actions.append((dst, "write"))
        if a.dry_run:
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)

    # ── views: copy each component dir, stamping .tsx/.ts, copying .css verbatim ──
    views_src = os.path.join(SRC, "views")
    for entry in sorted(os.listdir(views_src)):
        ep = os.path.join(views_src, entry)
        if os.path.isfile(ep):  # shared lib.ts
            write(f"{module}/src/components/{entry}", stamp(open(ep, encoding="utf-8").read(), a.ns, a.nsmix))
            continue
        for fn in sorted(os.listdir(ep)):
            fp = os.path.join(ep, fn)
            dst = f"{module}/src/components/{entry}/{fn}"
            if fn.endswith((".tsx", ".ts")):
                write(dst, stamp(open(fp, encoding="utf-8").read(), a.ns, a.nsmix))
            else:  # .css module — no namespace inside
                actions.append((dst, "write"))
                if not a.dry_run:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(fp, dst)

    # ── CND: append library types not already present ──
    lib_cnd = stamp(open(os.path.join(SRC, "definitions.cnd"), encoding="utf-8").read(), a.ns, a.nsmix)
    proj_cnd = f"{module}/settings/definitions.cnd"
    existing = cnd_types(open(proj_cnd, encoding="utf-8").read()) if os.path.isfile(proj_cnd) else set()
    lib_types = cnd_types(lib_cnd)
    new_types = lib_types - existing
    # keep only blocks whose header type is new (skip already-declared category mixins)
    blocks, cur, keep = [], [], False
    for ln in lib_cnd.splitlines():
        m = TYPE_RE.match(ln)
        if m:
            if cur:
                blocks.append((keep, "\n".join(cur)))
            cur, keep = [ln], (m.group(1) in new_types)
        elif cur or ln.strip().startswith("//") or not ln.strip():
            cur.append(ln)
    if cur:
        blocks.append((keep, "\n".join(cur)))
    appended = "\n".join(b for k, b in blocks if k).strip()
    actions.append((proj_cnd, f"append {len(new_types)}/{len(lib_types)} types"))
    if not a.dry_run and appended:
        with open(proj_cnd, "a", encoding="utf-8") as f:
            f.write("\n\n// ── P6.1 base component library ──\n" + appended + "\n")

    # ── resource bundles: append stamped EN/FR to <module>_<lang>.properties ──
    for lang in ("en", "fr"):
        rb = stamp(open(os.path.join(SRC, "resources", f"base-library_{lang}.properties"),
                        encoding="utf-8").read(), a.ns, a.nsmix)
        dst = f"{module}/settings/resources/{a.project}_{lang}.properties"
        actions.append((dst, "append"))
        if not a.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "a", encoding="utf-8") as f:
                f.write("\n\n# ── P6.1 base component library ──\n" + rb)

    # ── UI locales: deep-merge base-library keys into en/fr.json ──
    for lang in ("en", "fr"):
        add = json.load(open(os.path.join(SRC, "locales", f"{lang}.json")))
        dst = f"{module}/settings/locales/{lang}.json"
        cur = json.load(open(dst)) if os.path.isfile(dst) else {}

        def merge(base, extra):
            for k, v in extra.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    merge(base[k], v)
                else:
                    base.setdefault(k, v)
            return base

        merged = merge(cur, add)
        actions.append((dst, "merge"))
        if not a.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
                f.write("\n")

    # ── static tokens ──
    write(f"{module}/static/css/library-tokens.css",
          open(os.path.join(SRC, "static", "css", "library-tokens.css"), encoding="utf-8").read())

    # ── page templates (optional — overwrites the shell's basic template) ──
    if a.templates:
        for fn in ("home.server.tsx", "basic.server.tsx"):
            write(f"{module}/src/templates/Page/{fn}",
                  stamp(open(os.path.join(SRC, "templates", "Page", fn), encoding="utf-8").read(), a.ns, a.nsmix))

    print(f"[install_base_library] ns={a.ns} nsmix={a.nsmix} -> {module}"
          + (" (DRY RUN)" if a.dry_run else ""))
    print(f"  {len(new_types)} new CND type(s) appended (of {len(lib_types)} library types)")
    for dst, kind in actions:
        print(f"    {kind:24s} {os.path.relpath(dst, module)}")


if __name__ == "__main__":
    main()
