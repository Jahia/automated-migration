#!/usr/bin/env python3
"""manual_server — serve the manual zoning inspector + persist decisions (Phase 1).

Usage:  python3 orchestration/lib/manual_server.py <project> [port]     (default port 8899)

Serves projects/<project>/workflow-output/local-mirror/ statically (so <slug>.manual.html
and its assets resolve SAME-ORIGIN — no CORS) AND a tiny JSON API that persists Julian's
manual zoning decisions to projects/<project>/workflow-output/manual-decisions.json:

  GET  /api/decisions[?page=<slug>]  -> {"decisions":[...]}       (all, or filtered to a page)
  POST /api/decide  {decision}       -> upsert (dedup by id)      -> {"decisions":[...for page]}
  POST /api/delete  {"id":...}       -> remove one                -> {"decisions":[...all]}
  POST /api/clear   {"page":...}     -> remove all for one page   -> {"decisions":[]}

A decision = {id, page, action(component|area|absoluteArea), name?, area?, selector, key?, desc}.
`id` is deterministic (page|selector.value) so re-deciding the SAME element updates in place.
These decisions are OVERRIDES the deterministic engine will consume LATER (Phase 2 ->
scope-rules / segmentation-plan); this server only persists them. Read-only if unreachable
(the inspector still works without persistence).
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def decisions_path(project):
    return os.path.join(REPO, "projects", project, "workflow-output", "manual-decisions.json")


def load_decisions(project):
    p = decisions_path(project)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8")).get("decisions", [])
        except Exception:
            return []
    return []


def save_decisions(project, decisions):
    p = decisions_path(project)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"project": project, "decisions": decisions},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def make_handler(project, root):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/decisions":
                page = (parse_qs(u.query).get("page") or [None])[0]
                ds = load_decisions(project)
                if page:
                    ds = [d for d in ds if d.get("page") == page]
                return self._json({"decisions": ds})
            return super().do_GET()

        def do_POST(self):
            u = urlparse(self.path)
            try:
                b = self._read_body()
            except Exception as e:
                return self._json({"error": f"bad body: {e}"}, 400)
            ds = load_decisions(project)
            if u.path == "/api/decide":
                d = b.get("decision") or b
                if not d.get("id"):
                    d["id"] = f"{d.get('page', '')}|{(d.get('selector') or {}).get('value', '')}"
                ds = [x for x in ds if x.get("id") != d["id"]] + [d]
                save_decisions(project, ds)
                return self._json({"decisions": [x for x in ds if x.get("page") == d.get("page")]})
            if u.path == "/api/delete":
                ds = [x for x in ds if x.get("id") != b.get("id")]
                save_decisions(project, ds)
                return self._json({"decisions": ds})
            if u.path == "/api/clear":
                page = b.get("page")
                ds = [x for x in ds if x.get("page") != page]
                save_decisions(project, ds)
                return self._json({"decisions": []})
            return self._json({"error": "unknown endpoint"}, 404)

        def log_message(self, *a):
            pass  # quiet
    return Handler


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: manual_server.py <project> [port]")
    project = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8899
    root = os.path.join(REPO, "projects", project, "workflow-output", "local-mirror")
    if not os.path.isdir(root):
        sys.exit(f"no mirror dir: {root}")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(project, root))
    print(f"manual zoning server  http://127.0.0.1:{port}/<slug>.manual.html   (project={project})")
    print(f"decisions -> {decisions_path(project)}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
