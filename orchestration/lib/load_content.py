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

RECONCILE (A2, incident resume — "ne pas recommencer à partir de 0"): with
--clean the loader no longer razes every page. It computes a per-page VERDICT
from three sources — the load ledger (what we THINK was done), EDIT reality and
LIVE reality — and only rebuilds what needs it:
  ALIGNED         → skip entirely (zero writes)
  LIVE_DIVERGENT  → republish the main area only (no re-creation)
  REBUILD         → verified purge + full reload (the previous behavior)
The ledger is trusted only when corroborated by JCR reality (observed live
2026-07-04: the assumed state LIES — a silently-aborted purge left 925 stale
LIVE uuids while every artifact looked green; only Jahia is the source of
truth). --force-rebuild restores the old unconditional raze; --dry --clean
prints the verdicts without a single write (the "what is already done" report).

Usage:
  python3 orchestration/lib/load_content.py <project> <site> [--page home] [--limit N] \
      [--clean] [--force-rebuild] [--dry] [--locale en] [--chrome-from home|auto]
"""
import hashlib, json, os, sys
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
        ns = (self.manifest.get("passthroughType") or "ns:x").split(":")[0]
        self.mixns = f"{ns}mix"  # module mixin namespace (gen_plan convention)
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
        # A2: per-page load ledger (trace of the already-done) + verdict tallies.
        # Bootstrap: absent ledger → verdicts computed from JCR reality alone,
        # then backfilled. Runtime artifact, never written in --dry.
        self._ledger_path = f"projects/{project}/workflow-output/load-ledger.json"
        self.ledger = load_json(self._ledger_path, {})
        self.reconcile = {"ALIGNED": [], "LIVE_DIVERGENT": [], "REBUILD": []}

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
            self.m._urlopen_retry(req, timeout=120)  # transient-reset safe
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
        """Weakref wiring (after mixins + props): media DAM copies and the
        internal link's j:linknode (its jmix:internalLink mixin and j:url were
        handled by apply_payload)."""
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
                self.wire_stats["linkExternal"] += 1
            elif kind == "internal":
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
        exists = False
        try:
            d = self.m.call("content.type", {"nodeType": nodetype})
            t = d["types"][0]
            exists = True  # P2.5-D: minimal skeleton types may declare ZERO
            # visible props (everything rides per-node mixins) — existence of
            # the type, not its prop count, is the deploy gate
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
        self._props[nodetype] = {"text": text, "weakref": weak, "names": names,
                                 "exists": exists}
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
        """P2.5-D EXPLICIT contract for skeleton nodes (parent or item).
        The TYPE declares only the hidden `skeleton`; every editor-facing field
        rides a slot MIXIN added per node (so the edit form shows exactly what
        the node carries — no unjustified empty body2/body3, observed live):
          title    -> mix:title (jcr:title)
          bodyN    -> {mixns}:contribBody[N]
          imageN   -> {mixns}:contribImage[N] (+Orig/+OrigRef hidden)
          link     -> {mixns}:contribLink (j:linkType, linkLabel, linkOrig)
                      + jmix:externalLink/internalLink for j:url/j:linknode
        Returns (create_props, mixins, post_props): create carries skeleton
        only; mixin props are settable AFTER addMixins."""
        mixns = self.mixns
        f = payload.get("fields", {})
        create_props = {"skeleton": (payload.get("skeleton") or "")[:200_000]}
        mixins, post = [], {}
        if f.get("title"):
            mixins.append("mix:title")
            post["jcr:title"] = f["title"][:250]
        for k, v in f.items():
            if not k.startswith("body") or not v:
                continue
            n = k[len("body"):]
            mixins.append(f"{mixns}:contribBody{n}")
            post[k] = v[:200_000]
        for m in payload.get("media") or []:
            nm = m["name"]
            n = nm[len("image"):]
            mixins.append(f"{mixns}:contribImage{n}")
            post[nm + "Orig"] = m["orig"][:200_000]
            dam = self.upload_dam(m.get("file"))
            if dam:
                post[nm + "OrigRef"] = dam["uuid"]
                m["_dam"] = dam
        lnk = payload.get("link")
        if lnk:
            mixins.append(f"{mixns}:contribLink")
            post["linkOrig"] = lnk["href"][:1000]
            kind, target = self.resolve_link(lnk["href"])
            lnk["_kind"], lnk["_target"] = kind, target
            if kind == "external":
                mixins.append("jmix:externalLink")
                post["j:linkType"] = "external"
                post["j:url"] = lnk["href"][:1000]
            elif kind == "internal":
                mixins.append("jmix:internalLink")
                post["j:linkType"] = "internal"
            if f.get("linkLabel"):
                post["linkLabel"] = f["linkLabel"][:250]
        return create_props, mixins, post

    def apply_payload(self, path, mixins, post, payload, nodetype):
        """Post-create wiring: addMixins (one GraphQL call), set the mixin-
        carried props, then the weakrefs (media DAM copies, j:linknode). Any
        failure here is LOST CONTENT — recorded in prop_misses (loud exit)."""
        try:
            if mixins:
                ml = ", ".join(f'"{x}"' for x in dict.fromkeys(mixins))
                self.m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                           '{ addMixins(mixins: [%s]) } } }' % (path, ml))
            if post:
                self.m.update(path, post, locale=self.locale)
        except Exception as e:
            self.prop_misses.append((nodetype, "mixins/props"))
            print(f"    !! payload wiring on {path}: {str(e)[:160]}", file=sys.stderr)
            return
        self.wire_payload(path, payload)

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

    def _live_child_count(self, area_path):
        """Read-only count of the area's LIVE children via GraphQL (workspace
        LIVE). Returns:
          * an int  — the area exists in LIVE with that many direct children;
          * None    — the area node is ABSENT in LIVE (a PURGED state: verified
                      live, GraphQL answers a missing path with a
                      PathNotFoundException, which self.m.gql() raises — so we
                      MUST recognise that message as "purged", not as a fault,
                      or the poller would never see success on a fully-unpublished
                      area and clean_area would falsely raise on a clean purge);
          * -1      — a GENUINE transient read fault (connection reset/timeout):
                      unknown state, so the poller keeps retrying rather than
                      declaring success on a failed read.
        Never raises."""
        q = ('{ jcr(workspace: LIVE) { nodeByPath(path: "%s") '
             '{ children { nodes { name } } } } }' % area_path)
        try:
            d = self.m.gql(q)
        except Exception as e:
            # PathNotFoundException == the area is gone from LIVE == purged.
            # gql() also returns null-data alongside this error, but it raises
            # on `errors` first, so we key off the message here.
            if "PathNotFound" in str(e) or "path not found" in str(e).lower():
                return None
            return -1  # transient/unknown — treat as "not yet proven empty"
        node = (d.get("jcr") or {}).get("nodeByPath") if isinstance(d, dict) else None
        if node is None:
            return None  # area absent in LIVE == fully purged
        return len(((node.get("children") or {}).get("nodes")) or [])

    def clean_area(self, area_path):
        """Delete existing content children of an area so the load is idempotent
        (leftovers would DOUBLE page content on reload; observed live: Δheight
        80-180%). GraphQL EDIT-workspace deleteNode is SYNCHRONOUS and works
        regardless of publication state — the MCP delete guard refuses published
        nodes, and the mark-for-deletion + publish flow proved unreliable for
        skeleton nodes (jmix:markedForDeletion survivors) with an ASYNC deletion
        publication that raced the reload's create ('already exists' collisions,
        observed live P2.5). After clearing, an UNPUBLISH purges the LIVE
        copies (a publish cannot be trusted to — see the purge block below);
        the reload that follows republishes everything (rule 2).
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
        if not n:
            return n
        # VERIFIED LIVE purge by UNPUBLISH (was v1: one publish in try/except
        # pass — silent abort left 925 stale LIVE uuids, G2 red 3 gates later;
        # was v2: verified publish+poll — STILL WRONG). Measured live on the
        # divergent discoverasr areas: the EDIT-side publication metadata is
        # CORRUPTED — aggregatedPublicationInfo claims PUBLISHED while LIVE is
        # stale/absent — so publication.publish (even includeSubTree:true)
        # NO-OPS in 1 ms: a SUCCESSFUL scheduler job that publishes NOTHING
        # (durationMs:1, 18 005 jobs on the counter). Publishing harder can
        # never purge. publication.unpublish ignores that state, removes the
        # LIVE subtree instantly (<1 s measured) and RESETS the metadata so the
        # reload's publishes actually run. We still POLL LIVE and FAIL LOUD if
        # the purge cannot be proven — a poisoned LIVE state must never be
        # silently carried forward.
        import time
        for attempt in range(3):  # up to 3 unpublish+poll cycles
            try:
                self.m.unpublish(area_path)
            except Exception as e:
                print(f"    ! clean unpublish {area_path} (attempt {attempt + 1}): "
                      f"{str(e)[:140]}", file=sys.stderr)
            deadline = time.time() + 120  # measured <1 s; generous under load
            live = self._live_child_count(area_path)
            while live not in (0, None) and time.time() < deadline:
                time.sleep(3)
                live = self._live_child_count(area_path)
            if live in (0, None):
                return n  # LIVE proven empty — purge landed
            print(f"    ! clean: {area_path} still has {live} LIVE child(ren) "
                  f"after unpublish attempt {attempt + 1}/3 — re-unpublishing",
                  file=sys.stderr)
        # Exhausted retries with LIVE still populated: fail HARD rather than
        # leave a poisoned state that only surfaces at G2, three gates later.
        survivors = self._live_child_count(area_path)
        raise RuntimeError(
            f"clean_area: LIVE purge of {area_path} FAILED — "
            f"{survivors if survivors and survivors > 0 else 'unknown count of'} "
            f"stale LIVE child(ren) survive after 3 verified unpublish attempts. "
            f"Refusing to proceed (stale LIVE UUIDs would make every subsequent "
            f"edit+publish a silent no-op; observed live: G2 roundtrip red).")

    # ── A2 reconcile: page-granular incident resume ("what is already done") ──
    @staticmethod
    def _plan_hash(pdata):
        """sha256 of the page's CANONICAL plan slice (sort_keys + compact
        separators over content['pages'][slug]) — a changed plan invalidates
        the ledger entry and forces a REBUILD of that page only."""
        blob = json.dumps(pdata, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _area_children(self, area_path, workspace):
        """{name: uuid} of the area's DIRECT children in a workspace (read-only
        GraphQL), or None when the area node is absent there (GraphQL answers a
        missing path with PathNotFoundException — verified live). Unlike
        _live_child_count this RAISES on genuine transport faults: a verdict
        must never be computed from a failed read (it would mis-classify a
        loaded page as REBUILD and raze real content)."""
        q = ('{ jcr(workspace: %s) { nodeByPath(path: "%s") '
             '{ children { nodes { name uuid } } } } }' % (workspace, area_path))
        try:
            d = self.m.gql(q)
        except Exception as e:
            if "PathNotFound" in str(e) or "path not found" in str(e).lower():
                return None
            raise
        node = (d.get("jcr") or {}).get("nodeByPath") if isinstance(d, dict) else None
        if node is None:
            return None
        return {n["name"]: n.get("uuid")
                for n in ((node.get("children") or {}).get("nodes")) or []}

    def _expected_main_children(self, page, instances, main_area):
        """The top-level node NAMES load_page WOULD create in the page's main
        area — the SAME iteration surface and skip conditions as the create
        loop (area-flagged chrome, unmapped types, absolute-area singletons,
        undeployed types, empty non-container leaves, nesting under a created
        container), computed WITHOUT any write. promoted/skeleton instances
        always carry a non-empty payload (the skeleton prop) so they are always
        created — we deliberately do NOT call promoted_props here (it uploads
        to the DAM, a write). Deterministic names ({shortType}-{slug}-{idx})
        are what make page-granular reconciliation possible at all."""
        names = []
        would_create = set()  # instance idx that get created (any parent)
        for idx, inst in enumerate(instances):
            if inst.get("area"):
                continue
            nt = self.type_map.get(inst["type"].lower())
            if not nt:
                continue
            abs_area = area_for(nt, self.manifest, self.site)
            if abs_area and abs_area != main_area:
                continue
            pdef = self.props_of(nt)
            if not pdef.get("exists"):
                continue
            if not (inst.get("promoted") or inst.get("skeleton")):
                is_container = any(c.get("nodeType") == nt and c.get("isContainer")
                                   for c in self.manifest.get("components", []))
                if not self.map_props(page, inst, pdef) and not is_container:
                    continue  # empty leaf — load_page skips it too
            would_create.add(idx)
            pi = inst.get("parent")
            if pi is not None and pi in would_create:
                continue  # nests under its container — not a main-area child
            names.append(f"{nt.split(':')[-1]}-{page}-{idx}")
        return names

    def _reconcile_verdict(self, page, pdata, main_area):
        """A2 verdict — confront the ledger, EDIT reality and LIVE reality.
        The ledger is only TRUSTED when corroborated by JCR reality (lesson of
        2026-07-04: assumed state lies; only Jahia is the source of truth).
          ALIGNED         plan-hash match (or bootstrap: no ledger entry) +
                          EDIT structurally complete + LIVE aligned (name+uuid)
                          → nothing to do, zero writes.
          LIVE_DIVERGENT  EDIT complete but LIVE misaligned/empty → republish
                          only; publication pushes the EDIT state to LIVE,
                          including the REMOVAL of old-uuid LIVE nodes.
          REBUILD         plan changed (hash mismatch) OR EDIT incomplete —
                          missing AND surplus children both count (surplus =
                          render-doubling risk) → verified purge + reload.
        Returns (verdict, info dict for the report)."""
        entry = self.ledger.get(page)
        plan_hash = self._plan_hash(pdata)
        hash_ok = bool(entry) and entry.get("planHash") == plan_hash
        expected = self._expected_main_children(page, pdata.get("instances", []), main_area)
        edit = self._area_children(main_area, "EDIT") or {}
        info = {"expected": len(expected), "edit": len(edit),
                "hashOk": hash_ok, "bootstrap": entry is None}
        if entry and not hash_ok:
            info["reason"] = "plan hash changed since last load"
            return "REBUILD", info
        missing = sorted(set(expected) - set(edit))
        surplus = sorted(set(edit) - set(expected))
        if missing or surplus:
            info["reason"] = (f"EDIT incomplete: {len(missing)} missing, "
                              f"{len(surplus)} surplus top-level node(s)")
            info["missing"], info["surplus"] = missing[:5], surplus[:5]
            return "REBUILD", info
        live = self._area_children(main_area, "LIVE") or {}
        info["live"] = len(live)
        stale = sorted(n for n, u in edit.items() if live.get(n) != u)
        extra_live = sorted(set(live) - set(edit))
        if stale or extra_live:
            info["stale"] = len(stale) + len(extra_live)
            info["reason"] = (f"{len(stale)} EDIT child(ren) not in LIVE by (name,uuid)"
                              + (f", {len(extra_live)} stale LIVE extra(s)" if extra_live else ""))
            return "LIVE_DIVERGENT", info
        info["reason"] = "EDIT complete + LIVE aligned"
        return "ALIGNED", info

    def _publish_until_aligned(self, area_path):
        """LIVE_DIVERGENT repair — UNPUBLISH-FIRST, then publish, then poll.
        Proven live on en_adoor-apartment (84/84 aligned, 0 mismatch). What the
        failed variants measured on these areas:
          * publish alone — parent, includeSubTree, or per-child — NO-OPS in
            1 ms: the EDIT-side publication metadata is corrupted (aggregated
            publication info claims PUBLISHED while LIVE is stale/absent), so
            the SUCCESSFUL scheduler job publishes NOTHING (durationMs:1,
            18 005 jobs on the counter). Publishing harder never repairs.
          * publication.unpublish purges LIVE instantly (<1 s) and RESETS that
            metadata; the publish that follows then REALLY runs
            (publishedNodeCount:85, finished:true)...
          * ...but LIVE propagation TRICKLES past the return: 1 child visible
            at t+180 s, 84/84 aligned at t+200 s. Hence the ~300 s alignment
            budget, and the poll only concludes on FULL (name,uuid) equality —
            never on a first partial count.
        Languages: the publish/unpublish defaults (fr+en) — the same set every
        other loader publication uses, so both sides cover identical variants.
        Up to 3 unpublish→publish→poll cycles, then fail LOUD — a state we
        cannot prove repaired must never be carried forward."""
        import time
        edit = self._area_children(area_path, "EDIT") or {}
        for attempt in range(3):
            # 1. unpublish: instant LIVE purge + publication-metadata reset
            try:
                self.m.unpublish(area_path)
            except Exception as e:
                print(f"    ! unpublish {area_path} (attempt {attempt + 1}): "
                      f"{str(e)[:140]}", file=sys.stderr)
            deadline = time.time() + 60  # measured <1 s; margin under load
            live_n = self._live_child_count(area_path)
            while live_n not in (0, None) and time.time() < deadline:
                time.sleep(2)
                live_n = self._live_child_count(area_path)
            if live_n not in (0, None):
                # purge unproven — still attempt the publish (alignment equality
                # below is the real gate), but say so
                print(f"    ! repair: {area_path} LIVE not proven purged by "
                      f"unpublish (attempt {attempt + 1}/3) — publishing anyway",
                      file=sys.stderr)
            # 2. publish: actually runs now that the metadata was reset
            try:
                self.m.publish(area_path)
            except Exception as e:
                print(f"    ! republish {area_path} (attempt {attempt + 1}): "
                      f"{str(e)[:140]}", file=sys.stderr)
            # 3. poll until FULL (name,uuid) equality — propagation trickles
            #    past finished:true (measured: 84/84 only at t+200 s)
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    live = self._area_children(area_path, "LIVE") or {}
                except Exception:
                    live = None  # transient read fault — keep polling
                if live == edit:
                    return
                time.sleep(3)
            print(f"    ! republish: {area_path} LIVE still misaligned after "
                  f"attempt {attempt + 1}/3 — restarting unpublish+publish",
                  file=sys.stderr)
        raise RuntimeError(
            f"reconcile: LIVE repair of {area_path} FAILED — LIVE children "
            f"still misaligned with EDIT (name,uuid) after 3 verified "
            f"unpublish+publish attempts (NB: the area may be left unpublished "
            f"in LIVE). Refusing to proceed (stale LIVE identity makes every "
            f"edit+publish a silent no-op; observed live: G2 roundtrip red).")

    def _ledger_write(self, page, plan_hash, verdict, created=0, published=0):
        """Persist the per-page load trace after each treated page, so an
        interrupted run resumes page-granular. Never called in --dry."""
        import time
        self.ledger[page] = {"planHash": plan_hash,
                             "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "created": created, "published": published,
                             "verdict": verdict}
        os.makedirs(os.path.dirname(self._ledger_path), exist_ok=True)
        json.dump(self.ledger, open(self._ledger_path, "w"), indent=1)

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

    def load_page(self, page, limit=None, dry=False, clean=False, force=False):
        pdata = self.content.get("pages", {}).get(page)
        if not pdata:
            print(f"  no content-load data for page '{page}'"); return (0, 0)
        instances = pdata.get("instances", [])
        page_base = self._slug_to_jcr_path(page)
        main_area = f"{page_base}/main"
        plan_hash = self._plan_hash(pdata)
        if clean and not force:
            # A2 reconcile: --clean IS the reconciling mode now. Its documented
            # intent is "idempotent load without doubling content" — the
            # reconciliation satisfies it strictly better than the old raze-all
            # (skip what is proven done, republish what only diverged in LIVE,
            # rebuild only what actually changed/broke). The in-flight run's
            # plan already executes --clean and benefits without regeneration.
            # --force-rebuild keeps the old unconditional raze reachable.
            verdict, info = self._reconcile_verdict(page, pdata, main_area)
            self.reconcile[verdict].append((page, info))
            if verdict == "ALIGNED":
                why = "plan hash match" if info["hashOk"] else "bootstrap"
                print(f"  = {page}: ALIGNED — skip ({why}; EDIT {info['edit']} "
                      f"node(s) complete, LIVE aligned)")
                if not dry:
                    old = self.ledger.get(page) or {}
                    self._ledger_write(page, plan_hash, "ALIGNED",
                                       created=old.get("created", info["edit"]),
                                       published=old.get("published", info["edit"]))
                return (0, 0)
            if verdict == "LIVE_DIVERGENT":
                if dry:
                    print(f"  ~ {page}: LIVE_DIVERGENT — would republish "
                          f"{main_area} ({info['reason']}); no re-creation")
                    return (0, 0)
                print(f"  ~ {page}: LIVE_DIVERGENT — republishing {main_area} "
                      f"({info['reason']})")
                self._publish_until_aligned(main_area)
                self._ledger_write(page, plan_hash, "LIVE_DIVERGENT",
                                   created=0, published=1)
                return (0, 1)
            # REBUILD → fall through to the verified purge + full reload below
            print(f"  x {page}: REBUILD — {info['reason']}")
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
            if not pdef.get("exists"):
                continue
            mixins, post = [], {}
            if inst.get("promoted") or inst.get("skeleton"):
                # typed skeleton instance OR lifted anonymous raw block (P2.5)
                props, mixins, post = self.promoted_props(inst, pdef, nt)
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
                print(f"  [dry] {parent}/{name} <- {nt} {nest} props={list(props) + list(post)}"
                      + (f" mixins={mixins}" if mixins else "")
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
                        # retry-able: the async-deletion race ("already exists" —
                        # the old node vanishes when its publication job lands)
                        # AND transient MCP failures under sustained write load
                        # ("failed unexpectedly", observed ~1-3% of creates)
                        if attempt < 3 and ("already exists" in str(ce)
                                            or "failed unexpectedly" in str(ce)):
                            time.sleep(2 * (attempt + 1))
                            continue
                        raise
                if path:
                    created_path[idx] = path
                    created += 1
                    if inst.get("promoted") or inst.get("skeleton"):
                        # P2.5-D: per-node slot mixins, mixin props, weakrefs
                        self.apply_payload(path, mixins, post, inst, nt)
                    # publish AFTER the item children exist (below) — publishing
                    # a parent while its subtree is still being created aborts
                    # the publication job (observed live: 2 big articles whose
                    # EDIT nodes never reached LIVE)
                    label = post.get("jcr:title") or props.get("heading") or nt
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
                        cprops, cmix, cpost = self.promoted_props(ch, cpdef, cnt)
                        try:
                            import time
                            rc = None
                            for attempt in range(4):
                                try:
                                    rc = self.m.create(path, cnt, cprops,
                                                       name=f"item-{n + 1}", locale=self.locale)
                                    break
                                except Exception as ce:
                                    if attempt < 3 and ("already exists" in str(ce)
                                                        or "failed unexpectedly" in str(ce)):
                                        time.sleep(2 * (attempt + 1))
                                        continue
                                    raise
                            cpath = rc.get("path") if isinstance(rc, dict) else None
                            if cpath:
                                created += 1
                                self.apply_payload(cpath, cmix, cpost, ch, cnt)
                                self.m.publish(cpath)
                                published += 1
                        except Exception as e:
                            print(f"  ! item-{n + 1} ({cnt}) under {name} failed: {e}",
                                  file=sys.stderr)
            if path:  # parent LAST — its subtree is complete and stable now
                try:
                    self.m.publish(path)
                    published += 1
                except Exception as e:
                    print(f"  ! publish {name}: {str(e)[:120]}", file=sys.stderr)
        if not dry and instances:
            try:  # belt-and-braces: the area publication sweeps any straggler
                self.m.publish(main_area)
            except Exception:
                pass
        if clean and not dry:
            # A2: record the completed (re)load so the next run can skip it.
            # Only in reconcile/force mode — plain append mode stays unchanged.
            self._ledger_write(page, plan_hash, "REBUILD", created, published)
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
                 "[--clean] [--force-rebuild] [--dry] [--locale en] [--chrome-from home|auto]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    page = args[args.index("--page") + 1] if "--page" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    locale = args[args.index("--locale") + 1] if "--locale" in args else "en"
    chrome_from = args[args.index("--chrome-from") + 1] if "--chrome-from" in args else None
    dry = "--dry" in args
    force = "--force-rebuild" in args  # A2: the old unconditional raze-all
    clean = "--clean" in args or force
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
        c, p = ld.load_page(pg, limit=limit, dry=dry, clean=clean, force=force)
        tot_c += c; tot_p += p
    if clean and not force:
        # A2 report: what was already done vs what needed action, per page
        r = ld.reconcile
        print(f"\nreconcile: {len(r['ALIGNED'])} aligned (skipped) / "
              f"{len(r['LIVE_DIVERGENT'])} republished / "
              f"{len(r['REBUILD'])} rebuilt{' [dry]' if dry else ''}")
        for verdict in ("LIVE_DIVERGENT", "REBUILD"):
            for pg, info in r[verdict]:
                print(f"  - {verdict} {pg}: {info.get('reason', '')}")
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
