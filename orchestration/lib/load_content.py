#!/usr/bin/env python3
"""load_content.py — DETERMINISTIC content load via MCP (no guessed GraphQL).

The capstone of the ETL pipeline. Reads the deterministically-extracted content
(content/<project>.content-load.json) + the imported media map
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
    """Instance type (lowercased) -> ns:nodeType.
    v2 manifests carry an explicit instanceTypeMap (role -> nodeType, incl.
    cross-cutting and nested-part child types); v1 manifests carry per-component
    sxaSource lists; coversRoles is the derivation fallback for older v2 files."""
    m = {}
    for k, v in (manifest.get("instanceTypeMap") or {}).items():
        m[k.lower()] = v
    for c in manifest.get("components", []):
        nt = c.get("nodeType")
        for sxa in (c.get("sxaSource") or []):
            m.setdefault(sxa.lower(), nt)
        for role in (c.get("coversRoles") or []):
            m.setdefault(role.lower(), nt)
    for c in manifest.get("crossCutting", []):
        if c.get("coversRole") and c.get("nodeType"):
            m.setdefault(c["coversRole"].lower(), c["nodeType"])
    return m


def area_for(nodetype, manifest, site):
    """absolute components -> /home/<area>; else the page's main area (filled by caller)."""
    for c in manifest.get("components", []):
        if c.get("nodeType") == nodetype and c.get("areaType") == "absolute":
            short = nodetype.split(":")[-1]
            name = {"mainNav": "nav", "footer": "footer", "topBar": "topBar"}.get(short, short)
            return f"/sites/{site}/home/{name}"
    # v2: cross-cutting chrome (header/footer/nav) lives in absolute areas — it is
    # populated once, never dropped into a page's main area (migration rule 16)
    for c in manifest.get("crossCutting", []):
        if c.get("nodeType") == nodetype:
            return f"/sites/{site}/home/{c.get('area') or nodetype.split(':')[-1]}"
    return None  # page area


class Loader:
    def __init__(self, project, site):
        self.m = MCP(project)
        self.site = site
        self.project = project
        self.manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
        self.content = load_json(f"orchestration/content/{project}.content-load.json", {"pages": {}})
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

    # weakref property names that are image/asset references (not node refs like startNode, excludeNodes)
    IMAGE_WEAKREF_PROPS = {"image", "backgroundImage", "logo", "photo", "icon"}

    def map_props(self, page, inst, pdef):
        out = {}
        # images -> weakref props (resolve file -> imported jcrPath)
        # Only wire images to image-specific weakrefs, not query/structural refs (startNode, filter, etc.)
        imgs = [(self.imported_path(page, im["file"]), im.get("alt", "")) for im in inst.get("images", [])]
        imgs = [(p, a) for p, a in imgs if p]
        img_weakrefs = [w for w in pdef["weakref"] if w in self.IMAGE_WEAKREF_PROPS]
        for i, wname in enumerate(img_weakrefs):
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

    def clean_area(self, area_path):
        """Delete existing content children of an area so the load is idempotent.
        Skips published nodes (live content is preserved)."""
        try:
            d = self.m.call("content.list", {"parentPath": area_path, "locale": "fr"})
        except Exception:
            return 0
        kids = d.get("children", d.get("nodes", [])) if isinstance(d, dict) else []
        n = 0
        for k in kids:
            p = k.get("path") if isinstance(k, dict) else None
            if not p:
                continue
            try:
                self.m.call("content.delete", {"path": p})
                n += 1
            except Exception:
                # published or locked — skip, don't mark for deletion
                pass
        return n

    def _slug_to_jcr_path(self, slug):
        """Map a flat content-load slug to the hierarchical JCR page path.
        Uses the sitemap (orchestration/sitemaps/<project>.txt) to resolve hierarchy.
        Falls back to /home/<slug> if not found."""
        if slug == "home":
            return f"/sites/{self.site}/home"
        # Build lookup from sitemap: leaf slug -> full relative path
        if not hasattr(self, "_slug_map"):
            self._slug_map = {}
            sm_file = f"orchestration/sitemaps/{self.project}.txt"
            try:
                for line in open(sm_file):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    leaf = line.split("/")[-1]
                    # Map both the leaf slug and the full path
                    self._slug_map[leaf] = line
                    self._slug_map[line] = line
            except FileNotFoundError:
                pass
        # Case-insensitive lookup
        slug_lower = slug.lower()
        for k, v in self._slug_map.items():
            if k.lower() == slug_lower:
                return f"/sites/{self.site}/home/{v}"
        # Fallback: flat path
        return f"/sites/{self.site}/home/{slug}"

    def load_page(self, page, limit=None, dry=False, clean=False):
        pdata = self.content.get("pages", {}).get(page)
        if not pdata:
            print(f"  no content-load data for page '{page}'"); return (0, 0)
        instances = pdata.get("instances", [])
        page_base = self._slug_to_jcr_path(page)
        main_area = f"{page_base}/main"
        if clean and not dry:
            # Only clean the page's main area; absolute areas (nav/footer/topBar)
            # are singleton containers whose children should persist across loads.
            removed = self.clean_area(main_area)
            if removed:
                print(f"  cleaned {removed} existing node(s) from {page} areas")
        created = published = 0
        created_path = {}  # instance index -> created JCR path (so children nest under their container)

        def parent_for(idx, inst, nt):
            # nest under the container instance if it was created; else the area
            pi = inst.get("parent")
            if pi is not None and pi in created_path:
                return created_path[pi]
            return area_for(nt, self.manifest, self.site) or main_area

        # process in document order so a container is created before its children
        for idx, inst in enumerate(instances):
            if limit and created >= limit:
                break
            nt = self.type_map.get(inst["type"].lower())
            if not nt:
                continue  # unmapped helper
            
            # Absolute area singletons (topBar, mainNav, footer) are global site
            # chrome populated separately; the loader creates page-area content only.
            abs_area = area_for(nt, self.manifest, self.site)
            if abs_area and abs_area != main_area:
                continue

            pdef = self.props_of(nt)
            if not pdef["names"]:
                continue
            props = self.map_props(page, inst, pdef)
            is_container = any(c.get("nodeType") == nt and c.get("isContainer")
                               for c in self.manifest.get("components", []))
            # skip empty leaves, but ALWAYS create containers (they hold children)
            if not props and not is_container:
                continue
            parent = parent_for(idx, inst, nt)
            name = f"{nt.split(':')[-1]}-{page}-{idx}"
            if dry:
                nest = "(nested)" if inst.get("parent") in created_path else ""
                print(f"  [dry] {parent}/{name} <- {nt} {nest} props={list(props)}")
                created_path[idx] = f"{parent}/{name}"
                created += 1
                continue
            try:
                r = self.m.create(parent, nt, props, name=name, locale="fr")
                path = r.get("path") if isinstance(r, dict) else None
                if path:
                    created_path[idx] = path
                    created += 1
                    self.m.publish(path)
                    published += 1
                    label = props.get("heading") or (list(props.values())[0] if props else nt)
                    print(f"  + {path}  ({str(label)[:48]})")
            except Exception as e:
                print(f"  ! create {name} ({nt}) failed: {e}", file=sys.stderr)
        return (created, published)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: load_content.py <project> <site> [--page home] [--limit N] [--clean] [--dry]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    page = args[args.index("--page") + 1] if "--page" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    dry = "--dry" in args
    clean = "--clean" in args
    ld = Loader(project, site)
    if not ld.type_map:
        sys.exit("load_content: empty instance->nodeType map "
                 "(manifest has neither instanceTypeMap/coversRoles (v2) nor sxaSource (v1))")
    pages = [page] if page else list(ld.content.get("pages", {}).keys())
    tot_c = tot_p = 0
    for pg in pages:
        print(f"== page {pg} ==")
        c, p = ld.load_page(pg, limit=limit, dry=dry, clean=clean)
        tot_c += c; tot_p += p
    print(f"\nload_content: created {tot_c}, published {tot_p} node(s){' [dry]' if dry else ''}")


if __name__ == "__main__":
    main()
