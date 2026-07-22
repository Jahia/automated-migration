#!/usr/bin/env python3
"""apply_component_model.py — the COMPONENT MODEL is the authority (operator
mandate 2026-07-21: judgment where it belongs, determinism where it belongs).

Reads projects/<p>/workflow-output/component-model.json — the reviewed,
Claude-authored + operator-amended canonical model — and PATCHES the
component-manifest to execute it:
  * editor-facing display NAMES per type (nodeType identifiers never change:
    renaming deployed types is the Jackrabbit registry brick, memory-proven)
  * VIEW families per type (one component, multiple views)
  * extra FIELDS (e.g. cta.variant) — additive CND only
Then cnd_emit / merge_cnd / install_shell_templates regenerate from the
patched manifest, and reconcile-check's node-type ledger keeps the load
honest against it.

Usage: apply_component_model.py <project>
"""
import json
import sys


def main():
    p = sys.argv[1]
    mp = f"projects/{p}/workflow-output/component-manifest.json"
    cmp_ = f"projects/{p}/workflow-output/component-model.json"
    model = json.load(open(cmp_))
    m = json.load(open(mp))
    by_nt = {c["nodeType"]: c for c in (m.get("components") or []) +
             (m.get("crossCutting") or [])}
    changed = []
    for nt, spec in (model.get("types") or {}).items():
        c = by_nt.get(nt)
        if not c:
            print(f"  ! model type {nt} not in manifest — skipped", file=sys.stderr)
            continue
        if spec.get("name") and c.get("name") != spec["name"]:
            c["name"] = spec["name"]
            changed.append(f"{nt}: name -> {spec['name']}")
        if spec.get("views"):
            have = {v.get("name") for v in (c.get("views") or [])}
            for vn in spec["views"]:
                if vn not in have:
                    c.setdefault("views", []).append({"name": vn})
                    changed.append(f"{nt}: +view {vn}")
        for fld in spec.get("addFields") or []:
            if not any(f.get("name") == fld["name"] for f in (c.get("fields") or [])):
                c.setdefault("fields", []).append(fld)
                changed.append(f"{nt}: +field {fld['name']}")
    # contract child fields (cta / cardItem) live on childType entries too
    for nt, spec in (model.get("childTypes") or {}).items():
        for c in (m.get("components") or []):
            ct = c.get("childType")
            if isinstance(ct, dict) and ct.get("nodeType") == nt:
                for fld in spec.get("addFields") or []:
                    if not any(f.get("name") == fld["name"]
                               for f in (ct.get("fields") or [])):
                        ct.setdefault("fields", []).append(fld)
                        changed.append(f"{nt} (child): +field {fld['name']}")
    json.dump(m, open(mp, "w"), indent=1, ensure_ascii=False)
    print(f"apply_component_model: {len(changed)} change(s)")
    for x in changed:
        print("  ~", x)


if __name__ == "__main__":
    main()
