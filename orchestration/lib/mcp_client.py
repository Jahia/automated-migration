#!/usr/bin/env python3
"""mcp_client.py — the ONE sanctioned write path to Jahia (no guessed GraphQL).

Every content write in the harness goes through the Jahia MCP server's purpose-built
tools via this client. Hand-written GraphQL mutations are guesses that corrupt the
JCR (wrong shapes, missing mixins, the i18n link write-bug). This wraps the JSON-RPC
2.0 `tools/call` protocol and the content tools the loader/rewirer need.

Usable as a library (import) or CLI:
  python3 orchestration/lib/mcp_client.py <project> tools          # list tools
  python3 orchestration/lib/mcp_client.py <project> call <tool> '<json-args>'
"""
import base64, json, os, sys, urllib.request


class MCP:
    def __init__(self, project):
        self.user, self.host, self.token = self._env(project)

    @staticmethod
    def _env(project):
        u, h, tok = "root:root", "http://localhost:8080", ""
        envp = f"projects/{project}/.env"
        if os.path.exists(envp):
            for line in open(envp):
                line = line.strip()
                if line.startswith("JAHIA_USER="): u = line.split("=", 1)[1]
                elif line.startswith("JAHIA_HOST="): h = line.split("=", 1)[1]
                elif line.startswith("JAHIA_MCP_TOKEN="): tok = line.split("=", 1)[1]
        return u, h.rstrip("/"), tok

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = "APIToken " + self.token
        else:
            h["Authorization"] = "Basic " + base64.b64encode(self.user.encode()).decode()
        return h

    def call(self, tool, arguments):
        """Invoke an MCP tool. Returns the parsed result payload (dict) or raises."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": tool, "arguments": arguments}}).encode()
        req = urllib.request.Request(self.host + "/modules/mcp", body, self._headers())
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
        if "error" in resp:
            raise RuntimeError(f"MCP {tool} error: {resp['error']}")
        result = resp.get("result", {})
        # MCP returns content as a list of {type,text}; text is usually JSON
        content = result.get("content")
        if isinstance(content, list) and content and content[0].get("text") is not None:
            txt = content[0]["text"]
            try:
                return json.loads(txt)
            except Exception:
                return {"_text": txt}
        return result

    def tools(self):
        req = urllib.request.Request(self.host + "/modules/mcp", headers=self._headers())
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return [t if isinstance(t, str) else t.get("name") for t in d.get("tools", [])]

    # ── high-level helpers the loader / rewirer use ───────────────────────────
    def get(self, path):
        return self.call("content.get", {"path": path})

    def create(self, parent_path, node_type, properties, name=None, locale="fr"):
        args = {"parentPath": parent_path, "nodeType": node_type,
                "properties": properties, "locale": locale}
        if name:
            args["name"] = name
        return self.call("content.create", args)

    def update(self, path, properties, locale="fr"):
        return self.call("content.update", {"path": path, "properties": properties, "locale": locale})

    def set_weakref(self, path, prop, target_path, locale="fr"):
        """Wire an image/link weakreference to an imported DAM node (by absolute path)."""
        return self.update(path, {prop: target_path}, locale=locale)

    def publish(self, path):
        return self.call("publication.publish", {"path": path})

    def search(self, query):
        return self.call("content.search", {"query": query})


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: mcp_client.py <project> tools | call <tool> '<json-args>'")
    project, cmd = sys.argv[1], sys.argv[2]
    m = MCP(project)
    if cmd == "tools":
        ts = m.tools()
        print(f"{len(ts)} tools:", ", ".join(sorted(ts)))
    elif cmd == "call":
        tool = sys.argv[3]
        args = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        print(json.dumps(m.call(tool, args), indent=2, ensure_ascii=False))
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
