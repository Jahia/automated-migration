#!/usr/bin/env python3
"""load_content.py — DETERMINISTIC content load via MCP (no guessed GraphQL).

The capstone of the ETL pipeline. Reads the deterministically-extracted content
(content/<project>.content-data.json) + the imported media map
(images/<project>.imported.json) and creates the JCR nodes through the Jahia MCP
tools (lib/mcp_client.py), wiring each image weakreference AT CREATE TIME. Replaces
both LLM-improvised content and the legacy GraphQL set_*_refs.py rewiring.

Mapping strategy (deterministic, no hardcoded per-field tables):
  * type   : SXA instance type -> lsp:<type> via the manifest sxaSource map.
  * props  : introspect the target type's real properties (MCP content.type), then
             fill mandatory text props first, then optional text props, in the order
             the fields were extracted (heading <- first field, etc.). Images go on
             the WeakReference prop, resolved file -> imported jcrPath. Links -> ctaLabel
             (+ j:linkType/j:url best-effort).
  * place  : areaType=absolute components (nav/footer/topBar) -> /home/<area>;
             everything else -> the page's main area.
Then publishes (fr+en).

Usage:
  python3 orchestration/lib/load_content.py <project> <site> [--page home] [--limit N] [--dry]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP

TEXTY = {"String", "Text"}
SKIP_PROP = {"jcr:title"}  # set via title/heading mapping, not raw


def load_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def build_type_map(manifest):
    """SXA instance type (lowercased) -> lsp:nodeType."""
    m = {}
    for c in manifest.get("components", []):
        nt = c.get("nodeType")
        for sxa in (c.get("sxaSource") or []):
            m[sxa.lower()] = nt
    return m


def area_for(nodetype, manifest, site):
    """absolute components -> /home/<area>; else the page's main area (filled by caller)."""
    for c in manifest.get("components", []):
        if c.get("nodeType") == nodetype and c.get("areaType") == "absolute":
            short = nodetype.split(":")[-1]
            name = {"mainNav": "nav", "footer": "footer", "topBar": "topBar"}.get(short, short)
            return f"/sites/{site}/home/{name}"
    return None  # page area


class Loader:
    def __init__(self, project, site):
        self.m = MCP(project)
        self.site = site
        self.manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
        self.content = load_json(f"orchestration/content/{project}.content-data.json", {"pages": {}})
        self.imported = load_json(f"orchestration/images/{project}.imported.json", {})
        self.type_map = build_type_map(self.manifest)
        self._props = {}  # nodeType -> {"text":[names], "weakref":[names], "names":set}

    def props_of(self, nodetype):
        if nodetype in self._props:
            return self._props[nodetype]
        text, weak, names = [], [], set()
        try:
            d = self.m.call("content.type", {"nodeType": nodetype})
            t = d["types"][0]
            for p in (t.get("mandatoryProperties", []) + t.get("optionalProperties", [])):
                n = p.get("name"); names.add(n)
                if n in SKIP_PROP or n.startswith("j:"):
                    continue
                if p.get("type") == "WeakReference":
                    weak.append(n)
                elif p.get("type") in TEXTY:
                    text.append(n)
        except Exception as e:
            print(f"    ! content.type {nodetype} failed: {e}", file=sys.stderr)
        self._props[nodetype] = {"text": text, "weakref": weak, "names": names}
        return self._props[nodetype]

    def imported_path(self, page, filename):
        for x in self.imported.get(page, []):
            if x.get("file") == filename and x.get("jcrPath"):
                return x["jcrPath"]
        # fall back: any page (the same asset may be imported under home)
        for pg in self.imported.values():
            for x in pg:
                if x.get("file") == filename and x.get("jcrPath"):
                    return x["jcrPath"]
        return None

    def map_props(self, page, inst, pdef):
        out = {}
        # images -> weakref props (resolve file -> imported jcrPath)
        imgs = [(self.imported_path(page, im["file"]), im.get("alt", "")) for im in inst.get("images", [])]
        imgs = [(p, a) for p, a in imgs if p]
        for i, wname in enumerate(pdef["weakref"]):
            if i < len(imgs):
                out[wname] = imgs[i][0]
        if imgs and "imageAltText" in pdef["names"]:
            out["imageAltText"] = imgs[0][1] or "image"
        # text fields -> text props in order (heading first, etc.)
        vals = [v.strip() for v in inst.get("fields", {}).values() if v and v.strip()]
        for name, val in zip(pdef["text"], vals):
            out[name] = val[:5000]
        # link -> ctaLabel + external url (best-effort)
        links = inst.get("links", [])
        if links and "ctaLabel" in pdef["names"] and "ctaLabel" not in out:
            out["ctaLabel"] = links[0].get("text", "")[:120]
        if links and "j:linkType" in pdef["names"]:
            href = links[0].get("href", "")
            if href.startswith("http"):
                out["j:linkType"] = "external"
        return out

    def load_page(self, page, limit=None, dry=False):
        pdata = self.content.get("pages", {}).get(page)
        if not pdata:
            print(f"  no content-data for page '{page}'"); return (0, 0)
        instances = pdata.get("instances", [])
        page_base = f"/sites/{self.site}/home" if page == "home" else f"/sites/{self.site}/home/{page}"
        main_area = f"{page_base}/main"
        created = published = 0
        for idx, inst in enumerate(instances):
            if limit and created >= limit:
                break
            nt = self.type_map.get(inst["type"].lower())
            if not nt:
                continue  # unmapped helper (carousel/navigation containers handled elsewhere)
            pdef = self.props_of(nt)
            if not pdef["names"]:
                continue
            props = self.map_props(page, inst, pdef)
            if not props:
                continue  # nothing real to set
            parent = area_for(nt, self.manifest, self.site) or main_area
            name = f"{nt.split(':')[-1]}-{page}-{idx}"
            if dry:
                print(f"  [dry] {parent}/{name} <- {nt}  props={list(props)}  "
                      f"img={'yes' if any(k in pdef['weakref'] for k in props) else 'no'}")
                created += 1
                continue
            try:
                r = self.m.create(parent, nt, props, name=name, locale="fr")
                path = r.get("path") if isinstance(r, dict) else None
                created += 1
                if path:
                    self.m.publish(path)
                    published += 1
                    print(f"  + {path}  ({props.get('heading', list(props.values())[0])[:48]})")
            except Exception as e:
                print(f"  ! create {name} ({nt}) failed: {e}", file=sys.stderr)
        return (created, published)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: load_content.py <project> <site> [--page home] [--limit N] [--dry]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    page = args[args.index("--page") + 1] if "--page" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    dry = "--dry" in args
    ld = Loader(project, site)
    if not ld.type_map:
        sys.exit("load_content: empty SXA->lsp type map (manifest missing sxaSource)")
    pages = [page] if page else list(ld.content.get("pages", {}).keys())
    tot_c = tot_p = 0
    for pg in pages:
        print(f"== page {pg} ==")
        c, p = ld.load_page(pg, limit=limit, dry=dry)
        tot_c += c; tot_p += p
    print(f"\nload_content: created {tot_c}, published {tot_p} node(s){' [dry]' if dry else ''}")


if __name__ == "__main__":
    main()
