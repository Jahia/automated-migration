#!/usr/bin/env python3
"""load_logowall.py — P6.2 PROTOTYPE loader for the decomposed brands-logo wall.

Loads the decomposition record (decompose_logowall.py) into Jahia as REAL
composable nodes, EDIT-ONLY (Julian doctrine: NO publication, NO LIVE). Reuses
the sanctioned write path (mcp_client.MCP) and the proven DAM upload + per-node
addMixins + weakref pattern from load_content.py — applied to the library-native
model (asr:logoWall + asr:logo with asrmix:media / asrmix:cta), not the skeleton
contrib* model.

Node tree created under <page>/main:
  asr:logoWall  "logoWall"
   ├─ master      = asr:logo   (fixed named slot)
   └─ logos-1..N  = asr:logo   (open repeater child nodes)
each asr:logo:
   props   variant, breakClass, imgTitle, imgOrig, imgOrigRef, imageAltText
   link    j:linkType=external + jmix:externalLink + j:url  (the source href)
   image   weakref -> DAM copy of the source svg (asrmix:media, verbatim-default)

Usage: load_logowall.py <project> --site <site> [--page home] [--clean]
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import MCP  # noqa: E402


class LogoWallLoader:
    def __init__(self, project, site, locale="en"):
        self.project = project
        self.site = site
        self.locale = locale
        self.m = MCP(project)
        self._dam_path = f"orchestration/images/{project}.dam.json"
        self._dam = json.load(open(self._dam_path)) if os.path.isfile(self._dam_path) else {}

    # ── DAM upload (deduped by content-hash filename), EDIT-only ──────────────
    def upload_dam(self, fname):
        if not fname:
            return None
        if self._dam.get(fname):
            # verify the cached path still resolves (site may have been recreated)
            if self._resolves(self._dam[fname]["path"]):
                return self._dam[fname]
        src = f"projects/{self.project}/workflow-output/local-mirror/assets/{fname}"
        if not os.path.isfile(src):
            print(f"    ! dam: mirror asset missing: {fname}", file=sys.stderr)
            return None
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
            self.m._urlopen_retry(req, timeout=120)
            fin = self.m.call("media.upload.finalize", {"token": r["token"]})
            entry = {"path": fin["path"], "uuid": fin["identifier"]}
        except Exception as e:
            print(f"    ! dam upload {fname}: {str(e)[:160]}", file=sys.stderr)
            return None
        self._dam[fname] = entry
        json.dump(self._dam, open(self._dam_path, "w"), indent=1)
        return entry

    def _resolves(self, path):
        try:
            d = self.m.gql('{ jcr { nodeByPath(path: "%s") { uuid } } }' % path)
            return bool((d.get("jcr") or {}).get("nodeByPath"))
        except Exception:
            return False

    # ── create one asr:logo (master or repeated child) ───────────────────────
    def create_logo(self, parent_path, name, logo):
        dam = self.upload_dam(logo["file"])
        props = {
            "variant": logo["variant"],
            "breakClass": logo.get("breakClass", ""),
            "imgTitle": logo.get("title", ""),
            "imgOrig": logo["orig"],
            "imageAltText": logo.get("alt", ""),
        }
        if dam:
            props["imgOrigRef"] = dam["uuid"]
        r = self.m.create(parent_path, "asr:logo", props, name=name, locale=self.locale)
        path = r.get("path") if isinstance(r, dict) else None
        if not path:
            raise RuntimeError(f"create asr:logo {name} returned no path")

        # link: the source href is always external (https://www.discoverasr.com/...)
        href = (logo.get("href") or "").strip()
        if href.startswith(("http://", "https://")):
            self.m.gql('mutation { jcr(workspace: EDIT) { mutateNode(pathOrId: "%s") '
                       '{ addMixins(mixins: ["jmix:externalLink"]) } } }' % path)
            self.m.update(path, {"j:linkType": "external", "j:url": href}, locale=self.locale)

        # image weakref -> DAM copy (verbatim-default: weakref==origRef => byte-exact)
        if dam:
            try:
                self.m.set_weakref(path, "image", dam["path"], locale=self.locale)
            except Exception as e:
                print(f"    ! weakref image on {path}: {str(e)[:120]}", file=sys.stderr)
        return path, bool(dam)

    def clean(self, container_path):
        try:
            self.m.delete_edit(container_path)
            print(f"  cleaned existing {container_path}")
        except Exception:
            pass

    def load(self, page, clean=False):
        rec = json.load(open(f"orchestration/content/{self.project}.logowall.decomp.json"))
        page_base = f"/sites/{self.site}/{'home' if page == 'home' else page}"
        main_area = f"{page_base}/main"

        # ensure the page's main area exists (Jahia creates it lazily on render;
        # a freshly-created page has none — create the jnt:contentList eagerly)
        if not self._resolves(main_area):
            self.m.create(page_base, "jnt:contentList", {}, name="main", locale=self.locale)
            print(f"  created area {main_area}")

        container_path = f"{main_area}/logoWall"
        if clean:
            self.clean(container_path)

        # 1) container
        r = self.m.create(main_area, "asr:logoWall",
                          {"logoContainerClass": rec["container"]["logoContainerClass"],
                           "heading": rec["container"].get("heading", "")},
                          name="logoWall", locale=self.locale)
        cpath = r.get("path") if isinstance(r, dict) else None
        if not cpath:
            sys.exit("FAIL: asr:logoWall create returned no path")
        print(f"  + {cpath}  (asr:logoWall)")

        wired = 0
        # 2) master (fixed slot named "master")
        mp, ok = self.create_logo(cpath, "master", rec["master"])
        wired += ok
        print(f"    + {mp}  (master: {rec['master']['file']})")

        # 3) 18 brand logos (open repeater: logos-1..N)
        for i, logo in enumerate(rec["logos"], 1):
            lp, ok = self.create_logo(cpath, f"logos-{i}", logo)
            wired += ok
            brk = f" break={logo['breakClass']}" if logo.get("breakClass") else ""
            print(f"    + {lp}  ({logo['file']}{brk})")

        total = 1 + len(rec["logos"])
        print(f"\n  DONE (EDIT-only, no publication): 1 container + {total} logos "
              f"({wired}/{total} images wired to DAM)")
        return cpath


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--site", required=True)
    ap.add_argument("--page", default="home")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--clean", action="store_true")
    a = ap.parse_args()
    LogoWallLoader(a.project, a.site, a.locale).load(a.page, clean=a.clean)


if __name__ == "__main__":
    main()
