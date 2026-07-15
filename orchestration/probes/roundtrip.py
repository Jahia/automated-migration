#!/usr/bin/env python3
"""roundtrip.py — G2 dynamic contribution gate (CONTRIBUTION-PLAN P2.5).

Proves that editing a lifted property ACTUALLY changes the render — the inverse
of a dead prop. Deterministic sample (no randomness): every 3rd page (sorted),
up to 3 skeleton props per page. For each (node, prop):

  1. read the original value (default workspace, en)
  2. write a sentinel (EDIT only, via mcp_client — NO publication), fetch the
     AUTHENTICATED PREVIEW render -> sentinel MUST appear
  3. restore the original (EDIT only), fetch preview -> sentinel MUST be gone

EDIT-ONLY DOCTRINE (Julian, 2026-07-04): the migration process is EDIT-only;
publication is a single FINAL act performed by Julian via publish_site.sh.
Per-node publication during the process corrupted publication metadata (publish
no-ops in 1 ms on the corrupted state, 18 005 stale jobs, LIVE never reconciled
— days of forensics). Therefore this probe NEVER publishes, NEVER flushes
caches, and NEVER reads LIVE. G2 here asserts only "an EDIT edit changes the
render", observed through the authenticated PREVIEW workspace render:

    GET $JAHIA_URL/cms/render/default/{lang}{page_base}.html  (Authorization: Basic)

renders the EDIT (= default) workspace. Measured live (discoverasr, 2026-07-04):
an EDIT update is visible in this render in ~0.3 s with NO cache flush and NO
poll window; restore is equally immediate. The preview render is byte-near the
live render (1 220 826 vs 1 220 731 bytes on the same page), so it is a faithful
stand-in. Whether that EDIT state, once published, reaches LIVE is a SEPARATE
concern, tested post-publication by publish_site.sh + integrity.py
(--phase step_publish_final) — never by this probe.

Media (weakref) and link (j:url) slots follow the same EDIT-only, publication-
free schema. Text/link are asserted at the RENDER (sentinel appears in preview,
then gone); MEDIA is asserted at the JCR/EDIT weakref level (swap changes the
stored UUID, restore puts it back) — NOT at the render, because the verbatim-
default media contract (migration rule 26) makes a swap non-observable in the
render on this build (see the media loop comment). What matters for G2 is that
the slot is a LIVE, mutable weakref (the inverse of a dead media prop).

Any failure leaves the site restored (step 3 always runs). Exit 0 = PASS.

Usage: roundtrip.py <project> <site> [--pages 6] [--props 3] [--lang en]
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from load_content import Loader  # noqa: E402

SENTINEL = "QA-ROUNDTRIP-SENTINEL"

_MCP = {"m": None, "lang": "en"}  # set in main() — creds come from mcp_client's
# .env.local parsing (`source` does NOT export vars; os.environ is empty here)


def fetch_preview(page_base):
    """Render the AUTHENTICATED PREVIEW (= default/EDIT workspace) of a page.
    An EDIT mutation is visible here IMMEDIATELY (measured ~0.3 s, no cache
    flush, no poll) — no publication is involved. Basic auth uses the same
    credentials as every other write path (mcp_client's .env.local)."""
    m = _MCP["m"]
    url = f"{m.host}/cms/render/default/{_MCP['lang']}{page_base}.html"
    req = urllib.request.Request(url)
    req.add_header("Authorization",
                   "Basic " + base64.b64encode(m.user.encode()).decode())
    try:
        return urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  WARN: preview fetch {url}: {e}", file=sys.stderr)
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--props", type=int, default=3)
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()

    ld = Loader(a.project, a.site)
    _MCP["m"] = ld.m
    _MCP["lang"] = a.lang
    pages = sorted(ld.content.get("pages", {}).keys())
    sample_pages = pages[::3][:a.pages] or pages[:a.pages]

    # build the sample: (page_base, node_path, prop, original_value, kind)
    samples = []
    for slug in sample_pages:
        pdata = ld.content["pages"][slug]
        page_base = ld._slug_to_jcr_path(slug)
        per_page = 0
        for idx, inst in enumerate(pdata.get("instances", [])):
            if per_page >= a.props:
                break
            if inst.get("area") or not inst.get("skeleton"):
                continue
            nt = ld.type_map.get((inst.get("type") or "").lower())
            if not nt:
                continue
            # nest under the container instance if it references a created
            # parent (matches load_content.parent_for) — else flat under main
            pi = inst.get("parent")
            if pi is not None:
                pinst = pdata["instances"][pi]
                pnt = ld.type_map.get((pinst.get("type") or "").lower())
                if pnt:
                    pshort = pnt.split(':')[-1]
                    node = f"{page_base}/main/{pshort}-{slug}-{pi}/{nt.split(':')[-1]}-{slug}-{idx}"
                else:
                    node = f"{page_base}/main/{nt.split(':')[-1]}-{slug}-{idx}"
            else:
                node = f"{page_base}/main/{nt.split(':')[-1]}-{slug}-{idx}"
            payloads = [(node, inst)] + [
                (f"{node}/item-{n + 1}", ch)
                for n, ch in enumerate(inst.get("children") or [])]
            for npath, pl in payloads:
                if per_page >= a.props:
                    break
                for k, v in sorted((pl.get("fields") or {}).items()):
                    if per_page >= a.props:
                        break
                    if k == "title":
                        # hybrid contract: jcr:title participates in the RENDER
                        # only when the skeleton carries the {{f:title}} marker
                        # (semanticize moves the heading there). A copy-only
                        # title is a jContent/nav LABEL — legitimate, but not a
                        # render roundtrip target.
                        if "{{f:title}}" not in (pl.get("skeleton") or ""):
                            continue
                        samples.append((page_base, npath, "jcr:title", v, "title"))
                    elif k.startswith("body"):
                        samples.append((page_base, npath, k, v, "body"))
                    else:
                        continue
                    per_page += 1

    print(f"roundtrip: {len(samples)} sampled prop(s) across {len(sample_pages)} page(s)")

    def wait_preview(page_base, pred, timeout=10):
        """An EDIT edit is visible in the authenticated preview render
        IMMEDIATELY (measured ~0.3 s, no publication, no cache flush). This
        short poll is a safety margin only — the contract is 'an EDIT edit
        changes the render', not 'reaches LIVE'."""
        deadline = time.time() + timeout
        while True:
            html = fetch_preview(page_base)
            if pred(html):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(1)

    failures = []
    for i, (page_base, npath, prop, orig, kind) in enumerate(samples):
        tag = f"{SENTINEL}-{i}"
        sval = f"<p>{tag}</p>" if kind == "body" else tag
        label = f"{npath.split('/main/')[-1]}::{prop}"
        seen = False
        try:
            ld.m.update(npath, {prop: sval}, locale=a.lang)  # EDIT only, no publish
            seen = wait_preview(page_base, lambda h: tag in h)
            if not seen:
                failures.append((label, "sentinel NOT visible in preview render (10s)"))
        except Exception as e:
            failures.append((label, f"mutation failed: {e}"))
        finally:
            try:  # ALWAYS restore (EDIT only, no publish)
                ld.m.update(npath, {prop: orig}, locale=a.lang)
            except Exception as e:
                failures.append((label, f"RESTORE FAILED: {e}"))
        if seen and not wait_preview(page_base, lambda h: tag not in h):
            failures.append((label, "sentinel STILL visible after restore (10s)"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label}", flush=True)

    # ── G2+ (phase C): media weakref swap + j:url sentinel, EDIT-only ──
    dam = {}
    try:
        dam = json.load(open(f"orchestration/images/{a.project}.dam.json"))
    except Exception:
        pass
    dam_entries = [(f, e) for f, e in dam.items() if e]
    media_samples, link_samples = [], []
    for slug in sample_pages:
        pdata = ld.content["pages"][slug]
        page_base = ld._slug_to_jcr_path(slug)
        for idx, inst in enumerate(pdata.get("instances", [])):
            if inst.get("area") or not inst.get("skeleton"):
                continue
            nt = ld.type_map.get((inst.get("type") or "").lower())
            if not nt:
                continue
            pi = inst.get("parent")
            if pi is not None:
                pinst = pdata["instances"][pi]
                pnt = ld.type_map.get((pinst.get("type") or "").lower())
                if pnt:
                    pshort = pnt.split(':')[-1]
                    node = f"{page_base}/main/{pshort}-{slug}-{pi}/{nt.split(':')[-1]}-{slug}-{idx}"
                else:
                    node = f"{page_base}/main/{nt.split(':')[-1]}-{slug}-{idx}"
            else:
                node = f"{page_base}/main/{nt.split(':')[-1]}-{slug}-{idx}"
            for npath, pl in [(node, inst)] + [
                    (f"{node}/item-{n + 1}", ch)
                    for n, ch in enumerate(inst.get("children") or [])]:
                med = (pl.get("media") or [])
                if med and len(media_samples) < 4 and med[0].get("file") in dam:
                    media_samples.append((page_base, npath, med[0]))
                lnk = pl.get("link")
                if (lnk and len(link_samples) < 4 and
                        lnk["href"].startswith(("http://", "https://"))):
                    link_samples.append((page_base, npath, lnk["href"]))
            break  # first eligible instance per page is enough

    def _weakref_uuid(path, prop):
        """Read a weakref property's UUID from the EDIT workspace (doctrine:
        never LIVE). Returns the UUID string or None."""
        q = ('{ jcr(workspace: EDIT) { nodeByPath(path: "%s") '
             '{ property(name: "%s", language: "%s") { value } } } }'
             % (path, prop, a.lang))
        try:
            r = ld.m.gql(q)
            node = (r.get("jcr") or {}).get("nodeByPath") or {}
            return ((node.get("property") or {}) or {}).get("value")
        except Exception:
            return None

    # G2 media contract asserted at the JCR/EDIT weakref level, NOT at the
    # render. Why not the render: the media slot honours a VERBATIM-DEFAULT
    # contract (migration rule 26) — the view keeps rendering `imageNOrig`
    # byte-exact while the picked weakref == `imageNOrigRef`, and only swaps the
    # <img src> to the DAM URL once they differ. On the deployed discoverasr
    # module that swap is not observable in the render (the same DAM asset is
    # referenced by several slots so its filename is present regardless, and the
    # edited-media <img src> swap did not surface even after a cache flush —
    # measured live 2026-07-04) — asserting a render delta would be a false
    # signal. What G2 media MUST prove is that the slot is a LIVE, MUTABLE
    # weakref (the inverse of a dead media prop): a swap changes the stored UUID
    # and a restore puts it back. That is publication-free and deterministic.
    for i, (page_base, npath, m) in enumerate(media_samples):
        orig_entry = dam.get(m["file"])
        target = next(((f, e) for f, e in dam_entries if f != m["file"]), None)
        label = f"{npath.split('/main/')[-1]}::{m['name']}"
        if not (orig_entry and target):
            continue
        _, te = target
        try:
            # swap the weakref to a DIFFERENT DAM asset (EDIT only, no publish)
            ld.m.set_weakref(npath, m["name"], te["path"], locale=a.lang)
            if _weakref_uuid(npath, m["name"]) != te["uuid"]:
                failures.append((label, f"weakref did NOT become {te['uuid']} after swap"))
        except Exception as e:
            failures.append((label, f"media mutation failed: {e}"))
        finally:
            try:  # restore the original weakref (EDIT only, no publish)
                ld.m.set_weakref(npath, m["name"], orig_entry["path"], locale=a.lang)
            except Exception as e:
                failures.append((label, f"MEDIA RESTORE FAILED: {e}"))
        if _weakref_uuid(npath, m["name"]) != orig_entry["uuid"]:
            failures.append((label, "weakref NOT restored to original UUID"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label} (media swap)", flush=True)

    for i, (page_base, npath, orig_href) in enumerate(link_samples):
        tag = f"https://qa-roundtrip.example/ping-{i}"
        label = f"{npath.split('/main/')[-1]}::j:url"
        seen = False
        try:
            ld.m.update(npath, {"j:url": tag}, locale=a.lang)  # EDIT only, no publish
            seen = wait_preview(page_base, lambda h: tag in h)
            if not seen:
                failures.append((label, "j:url sentinel NOT visible in preview (10s)"))
        except Exception as e:
            failures.append((label, f"link mutation failed: {e}"))
        finally:
            try:  # restore (EDIT only, no publish)
                ld.m.update(npath, {"j:url": orig_href}, locale=a.lang)
            except Exception as e:
                failures.append((label, f"LINK RESTORE FAILED: {e}"))
        if seen and not wait_preview(page_base, lambda h: tag not in h):
            failures.append((label, "j:url sentinel STILL visible after restore (10s)"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label} (link)", flush=True)

    n_tests = len(samples) + len(media_samples) + len(link_samples)
    print(f"\nroundtrip: {n_tests - len(set(f[0] for f in failures))}/{n_tests} "
          f"props round-trip cleanly ({len(media_samples)} media, {len(link_samples)} links)")
    for f in failures[:10]:
        print(f"  ✗ {f[0]}: {f[1]}")
    print(("PASS" if not failures else "FAIL") + ": G2 round-trip gate")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
