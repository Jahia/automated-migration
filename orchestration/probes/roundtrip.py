#!/usr/bin/env python3
"""roundtrip.py — G2 dynamic contribution gate (CONTRIBUTION-PLAN P2.5).

Proves that editing a lifted property ACTUALLY changes the live render — the
inverse of a dead prop. Deterministic sample (no randomness): every 3rd page
(sorted), up to 3 skeleton props per page. For each (node, prop):

  1. read the original value (default workspace, en)
  2. write a sentinel, publish, flush output caches, fetch the LIVE page ->
     sentinel MUST appear
  3. restore the original, publish, flush, fetch -> sentinel MUST be gone

Any failure leaves the site restored (step 3 always runs). Exit 0 = PASS.

Usage: roundtrip.py <project> <site> [--pages 6] [--props 3]
"""
import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from load_content import Loader  # noqa: E402

SENTINEL = "QA-ROUNDTRIP-SENTINEL"


_MCP = {"m": None}  # set in main() — creds come from mcp_client's .env.local
# parsing (`source` does NOT export vars; os.environ is empty in python)


def flush_caches():
    m = _MCP["m"]
    host = m.host
    req = urllib.request.Request(
        f"{host}/modules/tools/cache.jsp",
        data=b"action=flushOutputCaches", method="POST",
        headers={"Origin": host,
                 "Content-Type": "application/x-www-form-urlencoded"})
    import base64
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(m.user.encode()).decode())
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print(f"  WARN: cache flush failed: {e}", file=sys.stderr)


def fetch_live(page_base):
    host = _MCP["m"].host
    url = f"{host}{page_base}.html"
    try:
        return urllib.request.urlopen(url, timeout=45).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  WARN: live fetch {url}: {e}", file=sys.stderr)
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("site")
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--props", type=int, default=3)
    a = ap.parse_args()

    ld = Loader(a.project, a.site)
    _MCP["m"] = ld.m
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
                        samples.append((page_base, npath, "jcr:title", v, "title"))
                    elif k.startswith("body"):
                        samples.append((page_base, npath, k, v, "body"))
                    else:
                        continue
                    per_page += 1

    print(f"roundtrip: {len(samples)} sampled prop(s) across {len(sample_pages)} page(s)")

    def wait_live(page_base, pred, timeout=45):
        """Jahia publication is ASYNC — poll (flush + fetch) until the live
        render satisfies pred. The contract under test is 'an edit becomes
        visible', not 'instantly visible'."""
        import time
        deadline = time.time() + timeout
        while True:
            flush_caches()
            live = fetch_live(page_base)
            if pred(live):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(2)

    failures = []
    for i, (page_base, npath, prop, orig, kind) in enumerate(samples):
        tag = f"{SENTINEL}-{i}"
        sval = f"<p>{tag}</p>" if kind == "body" else tag
        label = f"{npath.split('/main/')[-1]}::{prop}"
        seen = False
        try:
            ld.m.update(npath, {prop: sval}, locale="en")
            ld.m.publish(npath)
            seen = wait_live(page_base, lambda h: tag in h)
            if not seen:
                failures.append((label, "sentinel NOT visible in live render (45s)"))
        except Exception as e:
            failures.append((label, f"mutation failed: {e}"))
        finally:
            try:  # ALWAYS restore
                ld.m.update(npath, {prop: orig}, locale="en")
                ld.m.publish(npath)
            except Exception as e:
                failures.append((label, f"RESTORE FAILED: {e}"))
        if seen and not wait_live(page_base, lambda h: tag not in h):
            failures.append((label, "sentinel STILL visible after restore (45s)"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label}", flush=True)

    # ── G2+ (phase C): media weakref swap + j:url sentinel ──
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

    for i, (page_base, npath, m) in enumerate(media_samples):
        orig_entry = dam.get(m["file"])
        target = next(((f, e) for f, e in dam_entries if f != m["file"]), None)
        label = f"{npath.split('/main/')[-1]}::{m['name']}"
        if not (orig_entry and target):
            continue
        tf, te = target
        try:
            ld.m.set_weakref(npath, m["name"], te["path"], locale="en")
            ld.m.publish(npath)
            seen = wait_live(page_base, lambda h: tf in h)
            if not seen:
                failures.append((label, f"swapped image {tf} NOT visible in live (45s)"))
        except Exception as e:
            failures.append((label, f"media mutation failed: {e}"))
            seen = False
        finally:
            try:
                ld.m.set_weakref(npath, m["name"], orig_entry["path"], locale="en")
                ld.m.publish(npath)
            except Exception as e:
                failures.append((label, f"MEDIA RESTORE FAILED: {e}"))
        if seen and not wait_live(page_base, lambda h: tf not in h):
            failures.append((label, "swapped image STILL visible after restore"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label} (media swap)", flush=True)

    for i, (page_base, npath, orig_href) in enumerate(link_samples):
        tag = f"https://qa-roundtrip.example/ping-{i}"
        label = f"{npath.split('/main/')[-1]}::j:url"
        try:
            ld.m.update(npath, {"j:url": tag}, locale="en")
            ld.m.publish(npath)
            seen = wait_live(page_base, lambda h: tag in h)
            if not seen:
                failures.append((label, "j:url sentinel NOT visible in live (45s)"))
        except Exception as e:
            failures.append((label, f"link mutation failed: {e}"))
            seen = False
        finally:
            try:
                ld.m.update(npath, {"j:url": orig_href}, locale="en")
                ld.m.publish(npath)
            except Exception as e:
                failures.append((label, f"LINK RESTORE FAILED: {e}"))
        if seen and not wait_live(page_base, lambda h: tag not in h):
            failures.append((label, "j:url sentinel STILL visible after restore"))
        status = "✓" if not any(f[0] == label for f in failures) else "✗"
        print(f"  {status} {label} (link)", flush=True)

    n_tests = len(samples) + len(media_samples) + len(link_samples)
    flush_caches()
    print(f"\nroundtrip: {n_tests - len(set(f[0] for f in failures))}/{n_tests} "
          f"props round-trip cleanly ({len(media_samples)} media, {len(link_samples)} links)")
    for f in failures[:10]:
        print(f"  ✗ {f[0]}: {f[1]}")
    print(("PASS" if not failures else "FAIL") + ": G2 round-trip gate")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
