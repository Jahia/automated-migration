#!/usr/bin/env python3
"""mirror-selfcontained.py — the scoped mirror must not phone home.

The local mirror is the byte source of truth: every gate, the compose probe and
the pixel diffs read it, and a human reviews it to judge the migration. So a
mirror page that still fetches from a third party is a defect twice over — the
review shows behaviour the migrated site will never have, and the reviewer chases
ghosts. Measured: Cloudflare's injected RUM beacon and a chatbase chatbot script
survived localization with rewritten relative srcs, so opening the mirror fired
`POST /cdn-cgi/rum -> 404` and `GET /api/get-chatbot-styles -> 404` and drew a live
chat bubble over the hero — reported as "local mirror shows block by cloudflare"
(2026-08-03). The junk was real; the block was not.

FAILS on any remote-fetching reference (script/link[stylesheet|preconnect|
prefetch|dns-prefetch]/img/iframe/source with an absolute http(s) URL) in a scoped
mirror page, EXCEPT hosts explicitly allow-listed as kept embeds in scope-rules.json:

    {"keptEmbeds": ["widget.weezevent.com", "www.youtube.com", …]}

Metadata-only references (link[rel=canonical|alternate], og:*/twitter:* meta) never
fetch and are ignored. Every kept embed must be a DECISION on the record, so the
allow-list lives in scope-rules.json next to the exclusions, not in this probe.

Usage: mirror-selfcontained.py <project_path>
"""
import json
import os
import re
import sys
from collections import Counter

# tags/attrs that cause a network fetch when the page loads
FETCH_RE = re.compile(
    r"""<(script|link|img|iframe|source|video|audio|embed)\b([^>]*?)>""", re.I | re.S)
URL_RE = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""", re.I)
REL_RE = re.compile(r"""rel\s*=\s*["']([^"']+)["']""", re.I)
# link rels that only declare metadata (no fetch)
META_RELS = {"canonical", "alternate", "manifest", "author", "license", "next",
             "prev", "search", "me", "shortlink"}
# link rels that DO open a connection / fetch
FETCH_RELS = {"stylesheet", "preconnect", "dns-prefetch", "preload", "prefetch",
              "icon", "shortcut icon", "apple-touch-icon", "modulepreload"}
# INLINE loaders: a script with no src that BUILDS one at runtime still phones home
# (the GTM bootstrap does exactly this: j.src='https://www.googletagmanager.com/gtm.js').
# An attribute-only scan reports the mirror clean while the browser fetches anyway, so
# inline script bodies are scanned for a URL assigned to .src or handed to fetch/XHR.
INLINE_SCRIPT_RE = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.I | re.S)
INLINE_FETCH_RE = re.compile(
    r"""(?:\.src\s*=\s*|fetch\s*\(\s*|\.open\s*\([^,]+,\s*|importScripts\s*\(\s*)"""
    r"""["'`]?\s*(?:['"`]\s*\+\s*)?(https?://[^"'`\s)]+)""", re.I)


def main():
    pp = sys.argv[1].rstrip("/")
    mirror = f"{pp}/workflow-output/local-mirror"
    if not os.path.isdir(mirror):
        sys.exit(f"FAIL mirror-selfcontained: no mirror at {mirror}")
    try:
        rules = json.load(open(f"{pp}/workflow-output/scope-rules.json"))
    except (OSError, ValueError):
        rules = {}
    kept = {h.lower() for h in (rules.get("keptEmbeds") or [])}
    # a target recorded as accepted (e.g. an asset the SOURCE itself 404s) is a decision
    # on the record, not an un-declared fetch — match on the URL path, not the host
    accepted_paths = [str(t.get("path", "")).strip("/").lower()
                      for t in (rules.get("acceptedTargets") or []) if t.get("path")]

    offenders = Counter()
    where = {}
    pages = sorted(f for f in os.listdir(mirror) if f.endswith(".html"))
    for fn in pages:
        html = open(os.path.join(mirror, fn), encoding="utf-8", errors="replace").read()
        for m in FETCH_RE.finditer(html):
            tag, attrs = m.group(1).lower(), m.group(2)
            u = URL_RE.search(attrs)
            if not u:
                continue
            if tag == "link":
                rel = (REL_RE.search(attrs).group(1).lower()
                       if REL_RE.search(attrs) else "")
                rels = set(rel.split())
                if not (rels & FETCH_RELS) or (rels & META_RELS):
                    continue
            full = u.group(1).lower()
            host = re.sub(r"^https?://", "", full).split("/")[0].lower()
            if host in kept:
                continue
            if any(ap and ap in full for ap in accepted_paths):
                continue
            key = f"{tag} -> {host}"
            offenders[key] += 1
            where.setdefault(key, fn)
        for body in INLINE_SCRIPT_RE.findall(html):
            for url in INLINE_FETCH_RE.findall(body):
                host = re.sub(r"^https?://", "", url).split("/")[0].lower()
                if host in kept:
                    continue
                key = f"inline-script -> {host}"
                offenders[key] += 1
                where.setdefault(key, fn)

    if offenders:
        print(f"FAIL mirror-selfcontained [{mirror}] — {len(pages)} page(s)")
        print(f"  {sum(offenders.values())} remote fetch(es) across "
              f"{len(offenders)} host/tag pair(s); allow-listed: "
              f"{', '.join(sorted(kept)) or '(none)'}")
        for key, n in offenders.most_common(12):
            print(f"  - x{n:<4} {key}   (e.g. {where[key]})")
        print("  Fix: scope-exclude the tracker/widget, or record it as a kept embed "
              "in scope-rules.json \"keptEmbeds\".")
        sys.exit(1)
    print(f"PASS mirror-selfcontained: {len(pages)} page(s), no un-declared remote "
          f"fetch; kept embeds: {', '.join(sorted(kept)) or '(none)'}")


if __name__ == "__main__":
    main()
