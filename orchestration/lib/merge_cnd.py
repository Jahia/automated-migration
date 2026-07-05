#!/usr/bin/env python3
"""merge_cnd.py — DETERMINISTIC bridge of the analyze CND into the scaffolded module.

Takes the analyze-phase output (workflow-output/definitions.cnd from cnd_emit +
component-manifest.json) and installs it into the module:

  settings/definitions.cnd            — replaced (previous file kept as .orig once)
  settings/resources/<m>_en.properties— every type + every field + `.ui.tooltip`
  settings/resources/<m>_fr.properties  companion key (rule 18: no exceptions)
  settings/locales/{en,fr}.json       — created empty-in-sync if missing (rule 12)

No LLM, no hand edits: re-runnable, byte-stable for a given manifest.

Usage: merge_cnd.py <project> [--module-dir DIR] [--ns NS] [--mixns MIXNS]
"""
import argparse
import json
import os
import re
import sys

# Deterministic FR labels/tooltips for the recurring field vocabulary. Unknown
# fields fall back to the EN label (editors refine later) — the KEY PAIR is the
# rule, identical values are acceptable.
FIELD_FR = {
    "title": "Titre", "text": "Texte", "body": "Contenu",
    "image": "Image", "images": "Images", "imageAltText": "Texte alternatif",
    "j:linkType": "Lien", "ctaLabel": "Libellé du bouton",
    "query": "Requête JCR", "maxItems": "Nombre maximum d'éléments",
    "subNodeView": "Vue des éléments", "columns": "Colonnes", "gap": "Espacement",
    "html": "HTML source",
}
TOOLTIP_EN = {
    "title": "Main heading displayed by this component.",
    "text": "Short text displayed by this component.",
    "body": "Rich text content. Editors can format it (bold, lists, links).",
    "image": "Image shown by this component. Pick a file from the media library.",
    "images": "Images shown by this component. Pick files from the media library.",
    "imageAltText": "Alternative text describing the image (accessibility, SEO).",
    "j:linkType": "Choose where this links: an internal page, an external URL, or none.",
    "ctaLabel": "Label text for the call-to-action button.",
    "query": "JCR-SQL2 query selecting the content to list.",
    "maxItems": "Maximum number of items displayed.",
    "subNodeView": "View used to render each listed item.",
    "columns": "Number of columns in the grid row.",
    "gap": "Spacing between grid columns.",
    "html": "Verbatim source markup rendered as-is (migration passthrough).",
}
TOOLTIP_FR = {
    "title": "Titre principal affiché par ce composant.",
    "text": "Texte court affiché par ce composant.",
    "body": "Contenu riche. Les contributeurs peuvent le mettre en forme.",
    "image": "Image affichée par ce composant. Choisir un fichier de la médiathèque.",
    "images": "Images affichées par ce composant. Choisir des fichiers de la médiathèque.",
    "imageAltText": "Texte alternatif décrivant l'image (accessibilité, SEO).",
    "j:linkType": "Choisir la cible du lien : page interne, URL externe, ou aucun.",
    "ctaLabel": "Libellé du bouton d'appel à l'action.",
    "query": "Requête JCR-SQL2 sélectionnant le contenu à lister.",
    "maxItems": "Nombre maximum d'éléments affichés.",
    "subNodeView": "Vue utilisée pour chaque élément listé.",
    "columns": "Nombre de colonnes de la rangée.",
    "gap": "Espacement entre les colonnes.",
    "html": "Markup source restitué tel quel (passthrough de migration).",
}


def label(name, lang="en"):
    n = name.split(":")[-1]
    m = re.match(r"^(body|image)(\d*)$", n)
    if m:  # P2.5 contribution slots — numbered, human labels
        base = ("Texte" if lang == "fr" else "Text") if m.group(1) == "body" \
            else "Image"
        return base + (f" ({m.group(2)})" if m.group(2) else "")
    if n == "linkLabel":
        return "Libellé du lien" if lang == "fr" else "Link label"
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", n).replace("-", " ").replace("_", " ")
    return n.strip().title()


def key_of(node_type):
    return node_type.replace(":", "_")


def builtin_types(ns):
    return [
        {"nodeType": f"{ns}:jcrQuery", "name": "JCR Query",
         "fields": [{"name": "query"}, {"name": "maxItems"}, {"name": "subNodeView"}]},
        {"nodeType": f"{ns}:gridRow", "name": "Grid Row",
         "fields": [{"name": "columns"}, {"name": "gap"}]},
        {"nodeType": f"{ns}:rawHtml", "name": "Raw HTML (passthrough)",
         "fields": [{"name": "html"}]},
    ]


def bundle_lines(types, lang):
    out = []
    for t in types:
        k = key_of(t["nodeType"])
        name = t.get("name") or label(t["nodeType"])
        out.append(f"# ─── {name} ───")
        out.append(f"{k}={name}")
        fields = list(t.get("fields") or [])
        if t.get("layoutProperty"):
            fields.append({"name": t["layoutProperty"].get("name", "layout")})
        for f in fields:
            fn = f["name"]
            if lang == "fr":
                flabel = FIELD_FR.get(fn, label(fn, "fr"))
                tip = TOOLTIP_FR.get(fn, f"Valeur « {flabel} » du composant {name}.")
            else:
                flabel = label(fn) if fn != "j:linkType" else "Link"
                tip = TOOLTIP_EN.get(fn, f"{flabel} value for the {name} component.")
            out.append(f"{k}.{fn}={flabel}")
            out.append(f"{k}.{fn}.ui.tooltip={tip}")
        out.append("")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--module-dir")
    ap.add_argument("--ns")
    ap.add_argument("--mixns")
    args = ap.parse_args()

    proj = f"projects/{args.project}"
    module = args.module_dir or proj
    wo = f"{proj}/workflow-output"
    cnd_src = f"{wo}/definitions.cnd"
    manifest_p = f"{wo}/component-manifest.json"
    for p in (cnd_src, manifest_p):
        if not os.path.isfile(p):
            sys.exit(f"FAIL: {p} missing (run the cnd step first)")
    if not os.path.isdir(f"{module}/settings"):
        sys.exit(f"FAIL: {module}/settings missing (scaffold the module first)")

    cnd = open(cnd_src).read()
    m = json.load(open(manifest_p))
    ns = args.ns or (m.get("passthroughType", "ns:x").split(":")[0])

    # sanity: full namespace header MUST lead the file (module fails to install
    # with a generic IOException otherwise — scaffold skill hard rule)
    first = next((l for l in cnd.splitlines() if l.strip()), "")
    if not re.match(rf"^<\w+\s*=", first):
        sys.exit("FAIL: cnd_emit output does not start with a namespace header")
    if f"<{ns} " not in cnd and f"<{ns}=" not in cnd:
        sys.exit(f"FAIL: namespace '{ns}' not declared in {cnd_src}")

    dst = f"{module}/settings/definitions.cnd"
    # backup OUTSIDE settings/ — anything under settings/ ships in the bundle
    bak = f"{wo}/definitions.cnd.scaffold-orig"
    if os.path.isfile(dst) and open(dst).read() != cnd and not os.path.isfile(bak):
        os.rename(dst, bak)
    with open(dst, "w") as f:
        f.write(cnd)

    # the scaffold's placeholder mixin icon (<module-sans-hyphens>mix_component.png)
    # must follow the real mix namespace or editors see a blank icon
    mixns = args.mixns or f"{ns}mix"
    icon_dir = f"{module}/settings/content-types-icons"
    if os.path.isdir(icon_dir):
        for fn in os.listdir(icon_dir):
            if fn.endswith("mix_component.png") and fn != f"{mixns}_component.png":
                os.rename(os.path.join(icon_dir, fn),
                          os.path.join(icon_dir, f"{mixns}_component.png"))

    # resource bundles — every type, every field, every tooltip (rule 18)
    types = []
    types += builtin_types(ns)
    for c in (m.get("crossCutting") or []):
        types.append(c)
    for c in (m.get("components") or []):
        types.append(c)
        if c.get("childType"):
            types.append(c["childType"])
    # P2.5-D: contribution slot mixins (acqmix:contrib*) now carry the editor-
    # facing props — parse them from the generated CND (hidden props skipped)
    slot_names = {"body": "Text", "linkLabel": "Link label"}
    for blk in re.finditer(
            rf"^\[({re.escape(mixns)}:contrib\w+)\] mixin\n((?:  - .*\n?)*)", cnd, re.M):
        nt, blines = blk.group(1), blk.group(2)
        fields = []
        for pl in blines.splitlines():
            mm = re.match(r"\s*- ([\w:]+) \(", pl)
            if not mm or " hidden" in pl:
                continue
            fields.append({"name": mm.group(1)})
        if not fields:
            continue
        short = nt.split(":")[-1]
        num = re.search(r"(\d+)$", short)
        disp = ("Link" if "Link" in short else
                "Image" + (f" ({num.group(1)})" if num else "") if "Image" in short else
                "Text" + (f" ({num.group(1)})" if num else ""))
        types.append({"nodeType": nt, "name": disp, "fields": fields})
    module_name = os.path.basename(os.path.abspath(module))
    os.makedirs(f"{module}/settings/resources", exist_ok=True)
    for lang in ("en", "fr"):
        path = f"{module}/settings/resources/{module_name}_{lang}.properties"
        with open(path, "w") as f:
            f.write("\n".join(bundle_lines(types, lang)) + "\n")

    # locales kept in sync (rule 12) — create empty pair if absent
    os.makedirs(f"{module}/settings/locales", exist_ok=True)
    for lang in ("en", "fr"):
        p = f"{module}/settings/locales/{lang}.json"
        if not os.path.isfile(p):
            with open(p, "w") as f:
                f.write("{}\n")

    n_fields = sum(len(t.get("fields") or []) for t in types)
    print(f"[merge_cnd] {dst} installed ({len(cnd.splitlines())} lines); "
          f"{len(types)} types, {n_fields} fields -> resources/{module_name}_{{en,fr}}.properties")
    # rule-18 self-check: every field key has its tooltip companion
    for lang in ("en", "fr"):
        path = f"{module}/settings/resources/{module_name}_{lang}.properties"
        keys = [l.split("=")[0] for l in open(path) if "=" in l and not l.startswith("#")]
        fields = [k for k in keys if "." in k and not k.endswith(".ui.tooltip")]
        missing = [k for k in fields if f"{k}.ui.tooltip" not in keys]
        if missing:
            sys.exit(f"FAIL: {lang} bundle missing tooltips: {missing[:5]}")
    print("[merge_cnd] rule-18 tooltip check PASS (en+fr in sync)")


if __name__ == "__main__":
    main()
