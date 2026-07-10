#!/usr/bin/env python3
"""load_main_resources.py — DETERMINISTIC jmix:mainResource loader (ETL phase 2.5).

THE ORDERING FIX. mainResource content (news articles, agenda items) are NOT
pages: they are content nodes that must be created INSIDE a jnt:contentFolder
*after* media import — so that when the listing pages are built, their
lsp:jcrQuery.startNode can reference the folder and the ISDESCENDANTNODE query
resolves to real content.

Pipeline position:
    step_extract (media import + content extract)
        -> load_main_resources.py   <-- HERE: articles -> /sites/<s>/contents/<folder>
            -> page content steps    (listing pages wire jcrQuery.startNode -> folder)

Reads (files on disk, no guessing):
  * projects/<p>/workflow-output/component-manifest.json  (needsMainResource types)
  * orchestration/content/<p>.content-load.json           (extracted content units)
  * orchestration/content/<p>.mainresource.json           (folder/type/url config)
  * orchestration/images/<p>.imported.json                (DAM asset map for hero images)
  * projects/<p>/.reference/cache/_crawl/**                (URL tree -> classify units)

Writes (via lib/mcp_client.py — the ONE sanctioned write path):
  * /sites/<site>/contents/<folder>  (jnt:contentFolder, idempotent)
  * one mainResource node per captured detail page, hero image weakref wired
  * publishes each (fr + en)
  * orchestration/content/<p>.mainresource-load.json  (folder paths + listingPages
    -> folderPath map, consumed by the page steps + startnode.sh gate)

Usage:
  python3 orchestration/lib/load_main_resources.py <project> <site> [--dry] [--limit N]
"""
import json, os, re, subprocess, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP

REF_ORIGIN = "https://www.lesalondelaphoto.com"  # capture heroPath is origin-relative


def load_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def slug_of(path):
    return path.rstrip("/").split("/")[-1]


def parse_date(s):
    """DD/MM/YYYY -> ISO 8601 (Jahia date prop). Returns None if unparseable."""
    if not s:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}T00:00:00.000"


class MainResourceLoader:
    def __init__(self, project, site):
        self.project = project
        self.site = site
        self.m = MCP(project)
        self.manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
        self.content = load_json(f"orchestration/content/{project}.content-load.json", {"pages": {}})
        self.imported = load_json(f"orchestration/images/{project}.imported.json", {})
        self.cfg = load_json(f"orchestration/content/{project}.mainresource.json", {})
        self.mr_types = {c.get("nodeType") for c in self.manifest.get("components", [])
                         if c.get("needsMainResource")}
        self.url_map = self._build_url_map()

    # ── URL classification ────────────────────────────────────────────────────
    def _build_url_map(self):
        """leaf-slug (lowercased) -> source URL path (relative, no /fr-FR)."""
        out = {}
        base = f"projects/{self.project}/.reference/cache/_crawl"
        for root, _dirs, files in os.walk(base):
            for f in files:
                if not f.endswith(".html"):
                    continue
                full = os.path.join(root, f)
                # .../<host>/fr-FR/<a>/<b>/<slug>.html  -> <a>/<b>/<slug>
                mrel = re.search(r"/(?:fr-FR|fr|en)/(.+)\.html$", full)
                if not mrel:
                    continue
                rel = mrel.group(1)
                out.setdefault(slug_of(rel).lower(), rel)
        return out

    def classify(self, page_key):
        """Return (folder_name, folder_cfg) if page_key is a mainResource unit, else (None, None)."""
        url = self.url_map.get(page_key.lower())
        if not url:
            return None, None
        for fname, fcfg in self.cfg.get("folders", {}).items():
            for pref in fcfg.get("urlPrefixes", []):
                # must be a leaf UNDER the prefix, not the listing page itself
                if url.lower().startswith(pref.lower() + "/") and url.lower() != pref.lower():
                    return fname, fcfg
        return None, None

    # ── hero image resolution ───────────────────────────────────────────────
    def imported_path(self, page, filename):
        for x in self.imported.get(page, []):
            if x.get("file") == filename and x.get("jcrPath"):
                return x["jcrPath"]
        for pg in self.imported.values():
            for x in pg:
                if x.get("file") == filename and x.get("jcrPath"):
                    return x["jcrPath"]
        return None

    # ── article-core extraction (strip chrome) ───────────────────────────────
    def extract_core(self, page_key, page, fcfg):
        """Pull the mainResource core from a detail page's messy instance list."""
        chrome = set(self.cfg.get("chromeTypes", []))
        title_t = self.cfg.get("titleType", "title")
        body_ts = set(self.cfg.get("bodyTypes", []))
        insts = page.get("instances", [])

        title_inst = next((i for i in insts if i.get("type") == title_t and (i.get("fields") or {})), None)
        fields = (title_inst or {}).get("fields", {}) if title_inst else {}

        fm = fcfg.get("fieldMap", {})
        core = {}
        # jcr:title (via mix:title)
        title_val = fields.get(fm.get("title", "titre"), "")
        core["jcr:title"] = re.sub(r"\s*\|\s*", " ", title_val).strip()[:255] or slug_of(page_key)
        # date prop (publishDate | date)
        for prop in ("publishDate", "date"):
            if prop in fm:
                iso = parse_date(fields.get(fm[prop], ""))
                if iso:
                    core[prop] = iso
        # summary / location (short text)
        for prop in ("summary", "location"):
            if prop in fm and fields.get(fm[prop]):
                core[prop] = fields.get(fm[prop]).strip()[:2000]

        # body richtext — concatenate content/rich-text blocks in document order
        parts = []
        for inst in insts:
            if inst.get("type") not in body_ts:
                continue
            f = inst.get("fields") or {}
            t = (f.get("title") or "").strip()
            desc = (f.get("description") or f.get("content") or "").strip()
            if t and t.lower() != core["jcr:title"].lower():
                parts.append(f"<h2>{t}</h2>")
            if desc:
                # already-HTML fragments pass through; plain text gets a <p>
                parts.append(desc if "<" in desc else f"<p>{desc}</p>")
        core["body"] = "\n".join(parts) if parts else f"<p>{core['jcr:title']}</p>"

        # hero image (title instance's first image -> DAM jcrPath)
        hero = None
        if title_inst and title_inst.get("images"):
            im = title_inst["images"][0]
            jp = self.imported_path(page_key, im.get("file", ""))
            if jp:
                hero = (jp, im.get("alt", ""))
        return core, hero

    # ── MCP helpers ───────────────────────────────────────────────────────────
    def node_exists(self, path):
        try:
            self.m.get(path)
            return True
        except Exception:
            return False

    def ensure_folder(self, folder_name):
        base = self.cfg.get("contentsBase", "contents")
        contents_path = f"/sites/{self.site}/{base}"
        folder_path = f"{contents_path}/{folder_name}"
        if self.node_exists(folder_path):
            return folder_path
        # ensure the contents base exists first
        if not self.node_exists(contents_path):
            try:
                self.m.create(f"/sites/{self.site}", "jnt:contentFolder",
                              {"jcr:title": base}, name=base)
            except Exception as e:
                print(f"    ! ensure contents base {contents_path}: {e}", file=sys.stderr)
        try:
            self.m.create(contents_path, "jnt:contentFolder",
                          {"jcr:title": folder_name}, name=folder_name)
            self.m.publish(contents_path)
        except Exception as e:
            print(f"    ! ensure folder {folder_path}: {e}", file=sys.stderr)
        return folder_path

    # ── browser-capture source (WAF-blocked, client-rendered listings) ────────
    def import_hero(self, hero_path, folder_name, dry=False):
        """Import a reference hero image into the DAM via the SERVER-SIDE
        jahia-image-proxy (WAF-independent). hero_path is origin-relative."""
        if not hero_path:
            return None
        fn = hero_path.split("/")[-1].split("?")[0] or "hero.jpg"
        dest = f"/sites/{self.site}/files/migrated-media/{folder_name}"
        src = hero_path if hero_path.startswith("http") else REF_ORIGIN + hero_path
        if dry:
            return f"{dest}/{fn}"
        url = (f"{self.m.host}/modules/jahia-image-proxy/import-image"
               f"?sourceUrl={urllib.parse.quote(src, safe='')}"
               f"&destPath={urllib.parse.quote(dest, safe='')}"
               f"&filename={urllib.parse.quote(fn, safe='')}")
        try:
            out = subprocess.run(["curl", "-s", "-u", self.m.user, url],
                                 capture_output=True, text=True, timeout=60).stdout
            d = json.loads(out)
            return d.get("jcrPath") if d.get("success") else None
        except Exception as e:
            print(f"    ! hero import {src}: {e}", file=sys.stderr)
            return None

    def load_from_capture(self, dry=False):
        """Load articles from a browser-capture file (orchestration/content/
        <project>.articles-capture.json), keyed by folder name. Each record:
        {slug, title, date, summary, body, heroPath}. Publishes each. Returns
        (created, published, [article dicts])."""
        cap = load_json(f"orchestration/content/{self.project}.articles-capture.json")
        if not cap:
            return 0, 0, []
        created = published = 0
        arts = []
        for folder_name, records in cap.items():
            if folder_name.startswith("_") or not isinstance(records, list):
                continue
            fcfg = self.cfg.get("folders", {}).get(folder_name, {})
            nt = fcfg.get("type", "lsp:newsArticle")
            folder_path = folder_name and (self.ensure_folder(folder_name) if not dry
                                           else f"/sites/{self.site}/{self.cfg.get('contentsBase','contents')}/{folder_name}")
            for rec in records:
                slug = rec.get("slug") or re.sub(r"[^a-z0-9\-]", "-", (rec.get("title") or "art").lower())[:60]
                props = {"jcr:title": (rec.get("title") or slug).strip()[:255]}
                iso = parse_date(rec.get("date", ""))
                if iso:
                    props["publishDate" if nt == "lsp:newsArticle" else "date"] = iso
                if rec.get("summary"):
                    props["summary" if nt == "lsp:newsArticle" else "location"] = rec["summary"].strip()[:2000]
                body = (rec.get("body") or "").strip()
                if body and "<" not in body:
                    body = "\n".join(f"<p>{ln}</p>" for ln in body.split("\n") if ln.strip())
                props["body"] = body or f"<p>{props['jcr:title']}</p>"
                hero = self.import_hero(rec.get("heroPath", ""), folder_name, dry=dry)
                if hero:
                    props["image"] = hero
                    props["imageAltText"] = (rec.get("title") or "image")[:255]
                node_path = f"{folder_path}/{slug}"
                if dry:
                    print(f"  [dry] {node_path} <- {nt}  title={props['jcr:title'][:44]!r} hero={'y' if hero else '-'} body={len(props['body'])}")
                    arts.append({"path": node_path, "type": nt, "folder": folder_name, "source": slug})
                    created += 1
                    continue
                try:
                    if self.node_exists(node_path):
                        self.m.update(node_path, props); action = "~"
                    else:
                        self.m.create(folder_path, nt, props, name=slug); action = "+"
                    self.m.publish(node_path)
                    created += 1; published += 1
                    arts.append({"path": node_path, "type": nt, "folder": folder_name, "source": slug})
                    print(f"  {action} {node_path}  ({props['jcr:title'][:40]})  hero={'y' if hero else '-'}")
                except Exception as e:
                    print(f"  ! {nt} {slug}: {e}", file=sys.stderr)
        return created, published, arts

    # ── main ────────────────────────────────────────────────────────────────
    def run(self, dry=False, limit=None):
        if not self.mr_types:
            sys.exit("load_main_resources: manifest declares no needsMainResource types")
        # discover units
        units = []  # (page_key, folder_name, fcfg)
        for page_key in self.content.get("pages", {}):
            fname, fcfg = self.classify(page_key)
            if fname:
                units.append((page_key, fname, fcfg))
        result = {"folders": {}, "listingPages": {}, "articles": []}
        # map every listing page -> its folder path (for startNode wiring + gate)
        folder_paths = {}
        for fname, fcfg in self.cfg.get("folders", {}).items():
            fp = f"/sites/{self.site}/{self.cfg.get('contentsBase','contents')}/{fname}"
            folder_paths[fname] = fp
            result["folders"][fname] = {"path": fp, "type": fcfg.get("type")}
            for lp in fcfg.get("listingPages", []):
                result["listingPages"][lp] = fp

        # Browser-capture source (fresh, client-rendered listings) takes precedence
        # over stale SXA content-load extraction for any folder it covers.
        cap = load_json(f"orchestration/content/{self.project}.articles-capture.json") or {}
        captured_folders = {k for k in cap if not k.startswith("_") and isinstance(cap[k], list)}
        created = published = 0
        cap_created, cap_published, cap_arts = self.load_from_capture(dry=dry)
        created += cap_created; published += cap_published
        result["articles"].extend(cap_arts)
        if captured_folders:
            print(f"== capture covered folders {sorted(captured_folders)}: {cap_created} article(s) ==")

        # SXA-extracted units, minus folders already covered by the capture
        units = [(pk, fn, fc) for (pk, fn, fc) in units if fn not in captured_folders]
        if not units and not captured_folders:
            print("load_main_resources: no mainResource units matched (check urlPrefixes / crawl cache)")
        print(f"== {len(units)} SXA mainResource unit(s) across {len(result['folders'])} folder(s) ==")

        for page_key, fname, fcfg in units:
            if limit and created >= limit:
                break
            nt = fcfg.get("type")
            page = self.content["pages"][page_key]
            core, hero = self.extract_core(page_key, page, fcfg)
            props = {k: v for k, v in core.items() if v}
            if hero:
                props["image"] = hero[0]
                props["imageAltText"] = hero[1] or core.get("jcr:title", "image")
            folder_path = None if dry else self.ensure_folder(fname)
            folder_path = folder_path or folder_paths[fname]
            name = re.sub(r"[^a-z0-9\-]", "-", page_key.lower())[:60]
            node_path = f"{folder_path}/{name}"
            if dry:
                print(f"  [dry] {node_path}  <- {nt}")
                print(f"        title={core.get('jcr:title')!r} date={core.get('publishDate') or core.get('date')} "
                      f"hero={'yes' if hero else 'NONE'} body_len={len(core.get('body',''))}")
                result["articles"].append({"path": node_path, "type": nt, "folder": fname, "source": page_key})
                created += 1
                continue
            try:
                if self.node_exists(node_path):
                    self.m.update(node_path, props)
                    action = "~"
                else:
                    self.m.create(folder_path, nt, props, name=name)
                    action = "+"
                self.m.publish(node_path)
                created += 1
                published += 1
                result["articles"].append({"path": node_path, "type": nt, "folder": fname, "source": page_key})
                print(f"  {action} {node_path}  ({core.get('jcr:title','')[:44]})  hero={'y' if hero else '-'}")
            except Exception as e:
                print(f"  ! {nt} {name}: {e}", file=sys.stderr)

        outp = f"orchestration/content/{self.project}.mainresource-load.json"
        if not dry:
            json.dump(result, open(outp, "w"), indent=2, ensure_ascii=False)
            print(f"\nwrote {outp}")
        print(f"load_main_resources: created/updated {created}, published {published}"
              f"{' [dry]' if dry else ''}")
        print("listing startNode targets:")
        for lp, fp in result["listingPages"].items():
            print(f"  {lp:36s} -> {fp}")
        return result


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: load_main_resources.py <project> <site> [--dry] [--limit N]")
    project, site = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    dry = "--dry" in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    MainResourceLoader(project, site).run(dry=dry, limit=limit)


if __name__ == "__main__":
    main()
