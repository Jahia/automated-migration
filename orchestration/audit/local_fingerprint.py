#!/usr/bin/env python3
"""Fingerprint each LOCAL Jahia-rendered page for the fidelity audit.
Fetches http://$JAHIA_HOST/<lang>/sites/<site>/home/<path>.html (anonymous live render),
isolates <main>, and records: body text length, content-block count, h2 headings, and
image counts split into real-DAM / module-fallback / empty. Reference fingerprints are
captured separately via the browser (Cloudflare blocks non-browser fetches) and merged
by audit_compare.py.
Usage: python3 orchestration/audit/local_fingerprint.py [project] [siteKey] [lang]  > local.json
"""
import sys, re, json, html, urllib.request
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
SITE = sys.argv[2] if len(sys.argv) > 2 else PROJECT
LANG = sys.argv[3] if len(sys.argv) > 3 else "fr"
host = "http://localhost:8080"
for line in open(f"projects/{PROJECT}/.env"):
    if line.startswith("JAHIA_HOST="): host = line.strip().split("=", 1)[1]

paths = []
for line in open(f"orchestration/sitemaps/{PROJECT}.txt"):
    s = line.strip()
    if s and not s.startswith("#"):
        paths.append(s)

def fetch(url):
    try:
        return urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "ignore")
    except Exception as e:
        return f"__ERR__{e}"

def fingerprint(doc):
    m = re.search(r"<main\b[^>]*>(.*?)</main>", doc, re.S | re.I)
    main = m.group(1) if m else ""
    imgs = re.findall(r"<img\b[^>]*>", main, re.I)
    real = fallback = empty = 0
    for tag in imgs:
        src = re.search(r'src\s*=\s*"([^"]*)"', tag)
        s = src.group(1) if src else ""
        if not s: empty += 1
        elif "/files/" in s: real += 1
        elif "static/assets" in s or "static/" in s: fallback += 1
        else: real += 1
    h2 = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<h2\b[^>]*>(.*?)</h2>", main, re.S | re.I)]
    text = html.unescape(re.sub(r"<[^>]+>", " ", main))
    text = re.sub(r"\s+", " ", text).strip()
    blocks = len(re.findall(r'class="[^"]*(block|section|card|hero|grid)', main, re.I))
    return {"text_len": len(text), "imgs": len(imgs), "img_real": real,
            "img_fallback": fallback, "img_empty": empty, "h2": h2[:12], "blocks": blocks}

out = {}
for p in paths:
    url = f"{host}/{LANG}/sites/{SITE}/home/{p}.html" if p != "home" else f"{host}/{LANG}/sites/{SITE}/home.html"
    doc = fetch(url)
    if doc.startswith("__ERR__"):
        out[p] = {"error": doc[7:120]}
    else:
        out[p] = fingerprint(doc)
print(json.dumps(out, ensure_ascii=False))
