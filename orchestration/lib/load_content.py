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
    def __init__(self, project, site, locale="en"):
        self.m = MCP(project)
        self.site = site
        self.project = project
        self.locale = locale
        self.manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
        self.content = load_json(f"orchestration/content/{project}.content-load.json", {"pages": {}})
        self.imported = load_json(f"orchestration/images/{project}.imported.json", {})
        self.type_map = build_type_map(self.manifest)
        # container nodeType -> its item child nodeType (P2.5 decomposition)
        self.child_type = {c["nodeType"]: c["childType"]["nodeType"]
                           for c in self.manifest.get("components", []) or []
                           if c.get("isContainer") and isinstance(c.get("childType"), dict)
                           and c["childType"].get("nodeType")}
        self._props = {}  # nodeType -> {"text":[names], "weakref":[names], "names":set}
        self.prop_misses = []  # (nodeType, prop) — lifted value with no CND home = LOST TEXT
        # P2.5-C: DAM dedupe map (one jnt:file per unique mirror asset), committed
        self._dam_path = f"orchestration/images/{project}.dam.json"
        self._dam = load_json(self._dam_path, {})
        self.wire_stats = {"mediaWired": 0, "mediaFailed": 0,
                           "linkExternal": 0, "linkInternal": 0, "linkUnresolved": 0}

    def upload_dam(self, fname):
        """Mirror asset -> /sites/<site>/files via media.upload.create/PUT/
        finalize, published, deduped by file name (mirror names are content
        hashes). Returns {"path", "uuid"} or None (missing/failed — the view
        then renders the original markup verbatim; nothing breaks)."""
        if not fname:
            return None
        if fname in self._dam:
            return self._dam[fname] or None
        src = f"projects/{self.project}/workflow-output/local-mirror/assets/{fname}"
        if not os.path.isfile(src):
            print(f"    ! dam: mirror asset missing: {fname}", file=sys.stderr)
            return None
        import mimetypes
        import urllib.request
        data = open(src, "rb").read()
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        try:
            r = self.m.call("media.upload.create",
                            {"siteKey": self.site, "fileName": fname,
                             "sizeBytes": len(data), "mimeType": mime})
            h = self.m._headers()
            h["Origin"] = self.m.host
            h["Content-Type"] = mime
            req = urllib.request.Request(r["uploadUrl"], data=data, method="PUT", headers=h)
            urllib.request.urlopen(req, timeout=120).read()
            fin = self.m.call("media.upload.finalize", {"token": r["token"]})
            entry = {"path": fin["path"], "uuid": fin["identifier"]}
            self.m.publish(entry["path"])  # weakref targets must resolve in LIVE
        except Exception as e:
            print(f"    ! dam upload {fname}: {str(e)[:160]}", file=sys.stderr)
            return None
        self._dam[fname] = entry
        os.makedirs(os.path.dirname(self._dam_path), exist_ok=True)
        json.dump(self._dam, open(self._dam_path, "w"), indent=1)
        return entry

    def resolve_link(self, href):
        """P2.5-C3 link routing: external -> ('external', None); internal that
        maps to a MIGRATED page -> ('internal', page_path); anything else ->
        (None, None) — left verbatim via the linkOrig fallback, counted."""
        h = (href or "").strip()
        if h.startswith(("http://", "https://", "//", "mailto:", "tel:")):
            return "external", None
        if h.startswith("/"):
            slug = h.split("?")[0].split("#")[0].strip("/").replace("/", "_")
            if not slug:
                slug = "home"
            if slug in self.content.get("pages", {}):
                return "internal", self._slug_to_jcr_path(slug)
        return None, None

    def wire_payload(self, path, payload):
        """Post-create wiring (needs the node path): media weakrefs to the DAM
        copies; the contributor link's mixin + target (rule 9: j:url/j:linknode
        are mixin-injected — GraphQL addMixins, the proven flow)."""
        for m in payload.get("media") or []:
            dam = m.pop("_dam", None)
            if not dam:
                continue
            try:
                self.m.set_weakref(path, m["name"], dam["path"], locale=self.locale)
                self.wire_stats["mediaWired"] += 1
            except Exception as e:
                self.wire_stats["mediaFailed"] += 1
                print(f"    ! weakref {m['name']} on {path}: {str(e)[:120]}", file=sys.stderr)
        lnk = payload.get("link")
        if not lnk:
            return
        kind, target = lnk.pop("_kind", None), lnk.pop("_target", None)
        try:
            if kind == "external":
                self.m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                           '{ addMixins(mixins: ["jmix:externalLink"]) } } }' % path)
                self.m.update(path, {"j:url": lnk["href"][:1000]}, locale=self.locale)
                self.wire_stats["linkExternal"] += 1
            elif kind == "internal":
                self.m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                           '{ addMixins(mixins: ["jmix:internalLink"]) } } }' % path)
                self.m.set_weakref(path, "j:linknode", target, locale=self.locale)
                self.wire_stats["linkInternal"] += 1
            else:
                self.wire_stats["linkUnresolved"] += 1
        except Exception as e:
            self.wire_stats["linkUnresolved"] += 1
            print(f"    ! link wiring on {path}: {str(e)[:140]}", file=sys.stderr)

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

    def promoted_props(self, payload, pdef, nodetype):
        """P2.5 EXPLICIT contract for skeleton nodes (parent or item) — no
        introspection zip: `skeleton` (hidden prop, settable though absent from
        content.type), title -> jcr:title (mix:title), body/bodyN -> richtext,
        linkLabel, media hidden companions (imageNOrig / imageNOrigRef) and the
        link's j:linkType + linkOrig (P2.5-C). A lifted value whose prop is
        missing from the deployed type is LOST CONTENT (it was lifted OUT of
        the skeleton) — recorded loudly; ground truth would catch pixel loss."""
        f = payload.get("fields", {})
        props = {"skeleton": (payload.get("skeleton") or "")[:200_000]}
        if f.get("title"):
            props["jcr:title"] = f["title"][:250]
        if f.get("linkLabel"):
            if "linkLabel" in pdef["names"]:
                props["linkLabel"] = f["linkLabel"][:250]
            else:
                self.prop_misses.append((nodetype, "linkLabel"))
        for k, v in f.items():
            if not k.startswith("body") or not v:
                continue
            if k in pdef["names"]:
                props[k] = v[:200_000]
            else:
                self.prop_misses.append((nodetype, k))
                print(f"    !! {nodetype} lacks prop '{k}' — lifted text LOST",
                      file=sys.stderr)
        # media units: Orig ALWAYS (the view's verbatim default); OrigRef +
        # weakref only when the DAM copy exists (wire_payload sets the weakref)
        for m in payload.get("media") or []:
            nm = m["name"]
            if nm not in pdef["names"]:
                self.prop_misses.append((nodetype, nm))
                print(f"    !! {nodetype} lacks prop '{nm}' — media unit would VANISH",
                      file=sys.stderr)
                continue
            props[nm + "Orig"] = m["orig"][:200_000]
            dam = self.upload_dam(m.get("file"))
            if dam:
                props[nm + "OrigRef"] = dam["uuid"]
                m["_dam"] = dam
        lnk = payload.get("link")
        if lnk:
            if "linkOrig" in pdef["names"] or "j:linkType" in pdef["names"]:
                props["linkOrig"] = lnk["href"][:1000]
                kind, target = self.resolve_link(lnk["href"])
                if kind:
                    props["j:linkType"] = kind
                lnk["_kind"], lnk["_target"] = kind, target
            else:
                self.prop_misses.append((nodetype, "linkOrig"))
        return props

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
        # text fields: NAME-exact matches first (v2 fields are named after the
        # manifest props: title, text, html, skeleton...), then order-zip the
        # leftovers (v1 sxa field names -> heading first, etc.)
        fields = {k: v.strip() for k, v in inst.get("fields", {}).items() if v and v.strip()}
        if inst.get("skeleton"):
            fields["skeleton"] = inst["skeleton"]
        LONG = {"html", "skeleton"}  # verbatim markup — never truncate to 5k
        used_props, used_fields = set(), set()
        for name, val in fields.items():
            if name in pdef["text"] or name in pdef["names"]:
                out[name] = val[:200_000] if name in LONG else val[:5000]
                used_props.add(name)
                used_fields.add(name)
        rest_props = [p for p in pdef["text"] if p not in used_props]
        rest_vals = [v for k, v in fields.items() if k not in used_fields]
        for name, val in zip(rest_props, rest_vals):
            out[name] = val[:200_000] if name in LONG else val[:5000]
        # link -> ctaLabel + external url (best-effort)
        links = inst.get("links", [])
        if links and "ctaLabel" in pdef["names"] and "ctaLabel" not in out:
            out["ctaLabel"] = links[0].get("text", "")[:120]
        if links and "j:linkType" in pdef["names"]:
            href = links[0].get("href", "")
            if href.startswith("http"):
                out["j:linkType"] = "external"
        return out

    def ensure_area(self, area_path):
        """Area nodes (page /main, home /header|/nav|/footer) are created LAZILY
        by Jahia at first render — a freshly MCP-created page has none, and
        content.create into it fails with 'Parent path does not exist'. Create
        the jnt:contentList eagerly (exactly what the render engine would do)."""
        try:
            self.m.get(area_path, locale=self.locale)
            return True
        except Exception:
            pass
        parent, name = area_path.rsplit("/", 1)
        try:
            self.m.create(parent, "jnt:contentList", {}, name=name, locale=self.locale)
            return True
        except Exception as e:
            print(f"    ! ensure_area {area_path}: {e}", file=sys.stderr)
            return False

    def clean_area(self, area_path):
        """Delete existing content children of an area so the load is idempotent
        (leftovers would DOUBLE page content on reload; observed live: Δheight
        80-180%). GraphQL EDIT-workspace deleteNode is SYNCHRONOUS and works
        regardless of publication state — the MCP delete guard refuses published
        nodes, and the mark-for-deletion + publish flow proved unreliable for
        skeleton nodes (jmix:markedForDeletion survivors) with an ASYNC deletion
        publication that raced the reload's create ('already exists' collisions,
        observed live P2.5). After clearing, ONE parent publication purges the
        LIVE copies (rule 2: always publish after JCR mutations).
        content.list PAGINATES (~20) — loop until empty or no progress."""
        n = 0
        for _round in range(12):
            try:
                d = self.m.call("content.list", {"parentPath": area_path, "locale": self.locale})
            except Exception:
                return n
            kids = d.get("children", d.get("nodes", [])) if isinstance(d, dict) else []
            if not kids:
                break
            progressed = False
            for k in kids:
                p = k.get("path") if isinstance(k, dict) else None
                if not p:
                    continue
                try:
                    self.m.delete_edit(p)
                    n += 1
                    progressed = True
                except Exception as e:
                    print(f"    ! clean {p}: {str(e)[:160]}", file=sys.stderr)
            if not progressed:
                for k in kids[:3]:
                    print(f"    ! clean leftover: {k.get('path') or k.get('name')}", file=sys.stderr)
                break
        if n:
            try:
                self.m.publish(area_path)
            except Exception:
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
        if not dry:
            self.ensure_area(main_area)
            self.install_shell(page, pdata, page_base)
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
            if inst.get("area"):
                continue  # area-flagged chrome — installed once via load_chrome()
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
            if inst.get("promoted") or inst.get("skeleton"):
                # typed skeleton instance OR lifted anonymous raw block (P2.5)
                props = self.promoted_props(inst, pdef, nt)
            else:
                props = self.map_props(page, inst, pdef)
            is_container = any(c.get("nodeType") == nt and c.get("isContainer")
                               for c in self.manifest.get("components", []))
            # skip empty leaves, but ALWAYS create containers (they hold children)
            if not props and not is_container:
                continue
            parent = parent_for(idx, inst, nt)
            name = f"{nt.split(':')[-1]}-{page}-{idx}"
            kids = inst.get("children") or []
            if dry:
                nest = "(nested)" if inst.get("parent") in created_path else ""
                print(f"  [dry] {parent}/{name} <- {nt} {nest} props={list(props)}"
                      + (f" +{len(kids)} item(s)" if kids else ""))
                created_path[idx] = f"{parent}/{name}"
                created += 1
                continue
            path = None
            try:
                import time
                for attempt in range(4):
                    try:
                        r = self.m.create(parent, nt, props, name=name, locale=self.locale)
                        path = r.get("path") if isinstance(r, dict) else None
                        break
                    except Exception as ce:
                        # async deletion race: the old node vanishes when its
                        # publication job lands — wait and retry, don't fail
                        if "already exists" in str(ce) and attempt < 3:
                            time.sleep(2 * (attempt + 1))
                            continue
                        raise
                if path:
                    created_path[idx] = path
                    created += 1
                    if inst.get("promoted") or inst.get("skeleton"):
                        self.wire_payload(path, inst)  # media weakrefs + link mixins
                    self.m.publish(path)
                    published += 1
                    label = props.get("heading") or (list(props.values())[0] if props else nt)
                    print(f"  + {path}  ({str(label)[:48]})")
            except Exception as e:
                print(f"  ! create {name} ({nt}) failed: {e}", file=sys.stderr)
                continue
            # P2.5: item child nodes — one per {{child:N}} marker, SAME ORDER
            # (the skeleton view splices child i into marker i)
            if kids and path:
                cnt = self.child_type.get(nt)
                if not cnt:
                    print(f"  !! {nt} carries {len(kids)} item(s) but no childType "
                          f"in manifest — markers would render EMPTY", file=sys.stderr)
                    self.prop_misses.append((nt, "childType"))
                else:
                    cpdef = self.props_of(cnt)
                    for n, ch in enumerate(kids):
                        cprops = self.promoted_props(ch, cpdef, cnt)
                        try:
                            rc = self.m.create(path, cnt, cprops,
                                               name=f"item-{n + 1}", locale=self.locale)
                            cpath = rc.get("path") if isinstance(rc, dict) else None
                            if cpath:
                                created += 1
                                self.wire_payload(cpath, ch)
                                self.m.publish(cpath)
                                published += 1
                        except Exception as e:
                            print(f"  ! item-{n + 1} ({cnt}) under {name} failed: {e}",
                                  file=sys.stderr)
        return (created, published)

    def install_shell(self, page, pdata, page_base):
        """Persist the per-page SHELL spec (body attrs + ancestor chain + the
        balanced markup around <main>) as a `shell` child node of the page —
        the basic template composes it around the main Area. This is what makes
        a JS/body-class-dependent source render identically under Jahia."""
        shell = pdata.get("shell")
        if not shell:
            return
        nt = self.type_map.get("rawhtml")
        if not nt:
            return
        payload = {"html": json.dumps(shell, ensure_ascii=False)}
        spath = f"{page_base}/shell"
        try:
            self.m.update(spath, payload, locale=self.locale)
        except Exception:
            try:
                self.m.create(page_base, nt, payload, name="shell", locale=self.locale)
            except Exception as e:
                print(f"  ! shell {page}: {e}", file=sys.stderr)
                return
        try:
            self.m.publish(spath)
        except Exception:
            pass

    def load_chrome(self, from_page, dry=False, clean=False):
        """Install area-flagged chrome instances (header/nav/footer) ONCE from a
        representative page into the absolute areas (migration rule 16)."""
        pdata = self.content.get("pages", {}).get(from_page) or {}
        chrome = [i for i in pdata.get("instances", []) if i.get("area")]
        if not chrome:
            print(f"  no area-flagged chrome on page '{from_page}'")
            return (0, 0)
        created = published = 0
        done_areas = set()
        for inst in chrome:
            area_path = f"/sites/{self.site}/home/{inst['area']}"
            nt = self.type_map.get(inst["type"].lower())
            if not nt:
                continue
            if inst["area"] not in done_areas and not dry:
                self.ensure_area(area_path)
                if clean:
                    removed = self.clean_area(area_path)
                    if removed:
                        print(f"  cleaned {removed} node(s) from {area_path}")
            done_areas.add(inst["area"])
            pdef = self.props_of(nt)
            props = self.map_props(from_page, inst, pdef)
            name = f"{nt.split(':')[-1]}-{inst['area']}"
            if dry:
                print(f"  [dry] {area_path}/{name} <- {nt} props={list(props)}")
                created += 1
                continue
            try:
                r = self.m.create(area_path, nt, props, name=name, locale=self.locale)
                path = r.get("path") if isinstance(r, dict) else None
                if path:
                    created += 1
                    self.m.publish(path)
                    published += 1
                    print(f"  + {path} (chrome:{inst['area']})")
            except Exception as e:
                print(f"  ! chrome {name} failed: {e}", file=sys.stderr)
        return (created, published)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: load_content.py <project> <site> [--page home] [--limit N] "
                 "[--clean] [--dry] [--locale en] [--chrome-from home|auto]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    page = args[args.index("--page") + 1] if "--page" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    locale = args[args.index("--locale") + 1] if "--locale" in args else "en"
    chrome_from = args[args.index("--chrome-from") + 1] if "--chrome-from" in args else None
    dry = "--dry" in args
    clean = "--clean" in args
    ld = Loader(project, site, locale=locale)
    if not ld.type_map:
        sys.exit("load_content: empty instance->nodeType map "
                 "(manifest has neither instanceTypeMap/coversRoles (v2) nor sxaSource (v1))")
    tot_c = tot_p = 0
    if chrome_from:
        if chrome_from == "auto":
            chrome_from = next((s for s, p in ld.content.get("pages", {}).items()
                                if any(i.get("area") for i in p.get("instances", []))), None)
        if chrome_from:
            print(f"== chrome (from {chrome_from}) ==")
            c, p = ld.load_chrome(chrome_from, dry=dry, clean=clean)
            tot_c += c; tot_p += p
    pages = [page] if page else list(ld.content.get("pages", {}).keys())
    for pg in pages:
        print(f"== page {pg} ==")
        c, p = ld.load_page(pg, limit=limit, dry=dry, clean=clean)
        tot_c += c; tot_p += p
    print(f"\nload_content: created {tot_c}, published {tot_p} node(s){' [dry]' if dry else ''}")
    if ld.prop_misses:
        # a lifted value with no CND home = text LOST from the render — this is
        # a build/CND mismatch, never acceptable (G1/G3 will be red)
        uniq = sorted(set(ld.prop_misses))
        print(f"load_content: {len(ld.prop_misses)} LOST-TEXT prop miss(es) across "
              f"{len(uniq)} (type,prop) pair(s): {uniq[:10]}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
