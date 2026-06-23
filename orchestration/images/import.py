#!/usr/bin/env python3
"""Import reference images into Jahia's DAM via the sial-image-importer servlet.

Reads a per-page image manifest (orchestration/images/<project>.json), imports
each image into <destRoot>/<page>/, and writes <project>.imported.json mapping
each page to its imported JCR node paths. The content step references these
nodes - this replaces the headless agent's inability to fetch the bot-blocked
reference site for image URLs.

Usage:
  python3 orchestration/images/import.py <project>
  (expects orchestration/images/<project>.json; reads JAHIA_USER/JAHIA_HOST from
   projects/<project>/.env, default root:root @ http://localhost:8080)
"""
import json, os, sys, subprocess, urllib.parse

def load_env(project):
    user, host = "root:root", "http://localhost:8080"
    envp = f"projects/{project}/.env"
    if os.path.exists(envp):
        for line in open(envp):
            line = line.strip()
            if line.startswith("JAHIA_USER="): user = line.split("=", 1)[1]
            elif line.startswith("JAHIA_HOST="): host = line.split("=", 1)[1]
    return user, host

def import_one(host, user, source_url, dest_path, filename):
    url = (f"{host}/modules/sial/import-image"
           f"?sourceUrl={urllib.parse.quote(source_url, safe='')}"
           f"&destPath={urllib.parse.quote(dest_path, safe='')}"
           f"&filename={urllib.parse.quote(filename, safe='')}")
    out = subprocess.run(["curl", "-s", "-u", user, url], capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
        return d.get("jcrPath") if d.get("success") else None, out[:200]
    except Exception:
        return None, out[:200]

def main():
    project = sys.argv[1] if len(sys.argv) > 1 else "sial-paris"
    man = json.load(open(f"orchestration/images/{project}.json"))
    user, host = load_env(project)
    base, dest_root = man["base"], man["destRoot"]
    result, ok, fail = {}, 0, 0
    for page, imgs in man["pages"].items():
        result[page] = []
        dest = f"{dest_root}/{page}"
        for img in imgs:
            src = img["src"] if img["src"].startswith("http") else base + img["src"]
            jcr, raw = import_one(host, user, src, dest, img["file"])
            status = "OK" if jcr else "FAIL"
            if jcr: ok += 1
            else: fail += 1
            print(f"  [{status}] {page}/{img['file']}" + ("" if jcr else f"  -> {raw}"))
            result[page].append({"src": src, "role": img.get("role"), "jcrPath": jcr})
    outp = f"orchestration/images/{project}.imported.json"
    json.dump(result, open(outp, "w"), indent=2)
    print(f"\nImported {ok} ok, {fail} failed. Wrote {outp}")

if __name__ == "__main__":
    main()
