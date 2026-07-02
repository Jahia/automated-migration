#!/usr/bin/env python3
"""group_llm.py — The single bounded LLM step of the analyze phase.

Calls DeepSeek V4 Flash (temperature 0) with the site-AGNOSTIC grouping prompt
(orchestration/lib/grouping-prompt.md) to partition the deterministic content
candidates into Jahia content types. Self-corrects: after each attempt it runs
the partition gate (via assemble_manifest.py) and, if the grouping omits or
invents an id, feeds the exact error back to the model and retries. The model
NEVER names anything — names/fields are computed downstream by assemble.

Deterministic to invoke: same candidates + temp 0 -> stable grouping, and every
output is gate-verified. Designed to be driven by the migration-orchestrator as
a plain `Run:` step with a `PROBE:` gate.

Usage:
  python3 orchestration/lib/group_llm.py <project> [--model deepseek-v4-flash]
      [--ns ns] [--out <grouping.json>] [--retries 4]
API key is read from $DEEPSEEK_API_KEY or ~/.config/opencode/opencode.jsonc.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(HERE, "grouping-prompt.md")


def deepseek_key():
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k
    cfg = os.path.expanduser("~/.config/opencode/opencode.jsonc")
    if os.path.isfile(cfg):
        m = re.search(r'"deepseek".*?"apiKey":\s*"(sk-[^"]+)"', open(cfg).read(), re.DOTALL)
        if m:
            return m.group(1)
    print("FAIL: no DeepSeek API key ($DEEPSEEK_API_KEY or opencode.jsonc)", file=sys.stderr)
    sys.exit(2)


def rules_text():
    """The agnostic RULES from grouping-prompt.md, minus its file-IO framing."""
    if not os.path.isfile(PROMPT_FILE):
        return "Group the content candidates into Jahia content types by data shape."
    t = open(PROMPT_FILE).read()
    # keep from the first "You are a Jahia" to just before the OUTPUT block
    start = t.find("You are a Jahia")
    end = t.find("OUTPUT:")
    body = t[start:end] if start >= 0 and end > start else t
    # drop the two lines that tell the agent to READ a file (we inline the data)
    body = re.sub(r"READ this file first.*?\n(?:  .*\n)*", "", body)
    return body.strip()


def compact_candidates(cand):
    rows = []
    for c in cand.get("components", []):
        rows.append({
            "id": c["candidateId"],
            "role": c["role"],
            "dataShape": c["dataShape"],
            "frequency": c["frequency"],
            "pageCount": c["pageCount"],
            "isContainer": c["isContainer"],
            "childShape": c.get("childShape"),
            "variantTokens": c.get("variantTokens", []),
            "sample": (c.get("sampleText") or "")[:120],
        })
    pages = sorted({p for c in cand.get("components", []) for p in c.get("pages", [])})
    return rows, pages


def build_prompt(cand, error_feedback=None):
    rows, pages = compact_candidates(cand)
    ids = [r["id"] for r in rows]
    schema = ('{"groups":[{"members":["<id>",...],"kind":"component|container|listing",'
              '"needsMainResource":false,"layoutProperty":null,"views":[{"name":"default"}]}],'
              '"templates":[{"kind":"home|section-hub|content|listing|detail","pages":["<slug>",...]}]}')
    parts = [
        rules_text(),
        f"\nThe {len(ids)} content candidate ids you MUST partition (each in exactly one group, "
        f"none omitted, none invented):\n{json.dumps(ids)}",
        f"\nCandidate features:\n{json.dumps(rows, ensure_ascii=False)}",
        f"\nPages to assign to templates:\n{json.dumps(pages)}",
        f"\nReturn ONLY this strict minified JSON object as your entire response (no prose, no "
        f"markdown fence). layoutProperty is null OR {{\"name\":\"...\",\"options\":[...]}}:\n{schema}",
    ]
    if error_feedback:
        parts.append(f"\nYOUR PREVIOUS ANSWER FAILED THE PARTITION GATE: {error_feedback} "
                     f"Fix it: include every id above exactly once and invent none.")
    return "\n".join(parts)


def call_deepseek(prompt, model, key):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise assistant that returns only strict minified JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        # deepseek-v4-flash is a REASONING model: it spends ~13k tokens on
        # reasoning_content before the answer, so a small budget truncates content
        # to empty. Give ample headroom for reasoning + the JSON grouping.
        "max_tokens": 16000,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group() if m else text


def gate(candidates_path, grouping_path, ns):
    """Run the deterministic partition gate; return (ok, message)."""
    out = grouping_path.replace(".json", ".manifest.json")
    r = subprocess.run(
        ["python3", os.path.join(HERE, "assemble_manifest.py"), candidates_path,
         "--group", grouping_path, "--ns", ns, "--out", out],
        capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--ns", default="ns")
    ap.add_argument("--out")
    ap.add_argument("--retries", type=int, default=4)
    args = ap.parse_args()

    cand_path = f"{args.project}/workflow-output/semantic-candidates.json"
    if not os.path.isfile(cand_path):
        print(f"FAIL: {cand_path} not found (run semantic_extract first)", file=sys.stderr)
        sys.exit(2)
    cand = json.load(open(cand_path))
    out_path = args.out or f"{args.project}/workflow-output/grouping.json"
    key = deepseek_key()

    feedback = None
    for attempt in range(1, args.retries + 1):
        prompt = build_prompt(cand, feedback)
        try:
            content = call_deepseek(prompt, args.model, key)
        except Exception as e:
            print(f"  attempt {attempt}: deepseek error: {e}", file=sys.stderr)
            continue
        try:
            grouping = json.loads(extract_json(content))
        except Exception as e:
            feedback = f"your output was not valid JSON ({e})"
            print(f"  attempt {attempt}: invalid JSON, retrying", file=sys.stderr)
            continue
        with open(out_path, "w") as f:
            json.dump(grouping, f, indent=2, ensure_ascii=False)
        ok, msg = gate(cand_path, out_path, args.ns)
        print(f"  attempt {attempt}: {'PASS' if ok else 'FAIL'} — {msg.splitlines()[-1] if msg else ''}")
        if ok:
            print(f"[group_llm] {args.model} produced a gate-clean grouping in {attempt} attempt(s): {out_path}")
            sys.exit(0)
        # extract the specific gate failure line for feedback
        fb = [l for l in msg.splitlines() if "FAIL" in l]
        feedback = " ".join(fb) or msg[-300:]

    print(f"FAIL: no gate-clean grouping after {args.retries} attempts", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
