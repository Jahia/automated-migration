#!/usr/bin/env python3
"""gen_plan.py — parameterized v2 FULL-LOOP plan generator (QUALITY-PLAN P1.4).

The committed v1 plans are single-site-hardcoded; `acquia-analyze.plan.json`
stops at the analyze phase. This grafts the v2 analyze epic (crawl → mirror
gate → semantic → group/partition gate → cnd → content extract/partition gate →
fidelity gate) onto the v1 downstream template (scaffold → assets → CND merge →
components → templates → deploy → site → content → publish parity → ground
truth), fully parameterized. Deterministic steps carry `Run:` lines; every
deploy/content/publish/scaffold step carries engine-enforced PROBEs (P0.3 lint).

Secrets: plans never embed credentials — probes read $JAHIA_URL/$JAHIA_USER/
$JAHIA_PASS from .env.local via probes/_lib.sh (P0.2).

Usage:
  gen_plan.py --project acquia-drupal --url https://www.acquia.com \
              --ns acq --site acquia [--module NAME] [--title T]
              [--max-pages 18] [--threshold 95] [--out PATH]
"""
import argparse
import json


def step(id, title, task_type, criteria, deps=None, inputs=None, agent="code",
         outputs=None, max_attempts=3):
    s = {"id": id, "title": title, "task_type": task_type, "agent": agent,
         "depends_on": deps or [], "inputs": inputs or {},
         "acceptance_criteria": criteria, "max_attempts": max_attempts}
    if outputs:
        s["expected_outputs"] = outputs
    return s


def build_plan(p):
    P, URL, NS, MIXNS = p["project"], p["url"], p["ns"], p["mixns"]
    SITE, MODULE, TITLE = p["site"], p["module"], p["title"]
    N, THR = p["max_pages"], p["threshold"]
    PP = f"projects/{P}"
    URI = f"https://jahia.com/{P}/nt/1.0"
    common = {"project": P, "project_path": PP, "namespace": NS,
              "mixNamespace": MIXNS, "siteKey": SITE, "moduleName": MODULE}

    analyze = [
        step("step_connect", "Env + Jahia reachable", "verify",
             [f"PROBE: bash orchestration/probes/connect.sh {PP}"]),
        step("step_crawl", "Crawl the source site", "build",
             [f"Run: python3 orchestration/lib/crawl-site.py {PP} {URL} --max-pages {N} --depth 2 --rate-delay 2 --max-asset-size 1",
              f"PROBE: test -s {PP}/workflow-output/page-inventory.json"],
             deps=["step_connect"]),
        step("step_localize", "Local mirror + offline mirror gate", "build",
             [f"Run: python3 orchestration/lib/localize_site.py {PP} --max-asset-size 15",
              f"PROBE: test -s {PP}/workflow-output/local-mirror/mirror.json",
              f"PROBE[900]: node orchestration/lib/mirror_probe.mjs {PP} 10"],
             deps=["step_crawl"]),
        step("step_semantic", "Deterministic candidates + partitions", "build",
             [f"Run: python3 orchestration/lib/semantic_extract.py {PP}",
              f"PROBE: test -s {PP}/workflow-output/semantic-candidates.json",
              f"PROBE: test -s {PP}/workflow-output/semantic-templates.json"],
             deps=["step_localize"]),
        step("step_group", "LLM grouping (bounded) + partition gate", "build",
             [f"Run: python3 orchestration/lib/group_llm.py {PP} --model deepseek-v4-flash --ns {NS} --out {PP}/workflow-output/grouping.json",
              f"PROBE: python3 orchestration/lib/assemble_manifest.py {PP}/workflow-output/semantic-candidates.json --group {PP}/workflow-output/grouping.json --ns {NS} --out {PP}/workflow-output/component-manifest.json"],
             deps=["step_semantic"]),
        step("step_cnd", "Emit CND + view plan", "build",
             [f"Run: python3 orchestration/lib/cnd_emit.py {PP}/workflow-output/component-manifest.json --ns {NS} --mixns {MIXNS} --project {P} --out-cnd {PP}/workflow-output/definitions.cnd --out-views {PP}/workflow-output/views.json",
              f"PROBE: test -s {PP}/workflow-output/definitions.cnd",
              f"PROBE: grep -q \"{NS} = \" {PP}/workflow-output/definitions.cnd",
              f"PROBE: test -s {PP}/workflow-output/views.json"],
             deps=["step_group"]),
        step("step_content_extract", "Content-load payload + HARD partition gate", "build",
             [f"Run: python3 orchestration/lib/extract_content.py {P}",
              f"PROBE: python3 orchestration/probes/partition.py {P}"],
             deps=["step_cnd"]),
        step("step_fidelity_gate", "Fidelity gate (HALT: human reviews review.html)", "verify",
             [f"PROBE[900]: node orchestration/lib/reconstruct_probe.mjs {PP} 10 {THR}",
              "Gate: present worst pages + semantic share, return status halt."],
             deps=["step_content_extract"]),
    ]

    # fidelity-first profile (P1): the module ships the agnostic fidelity-shell
    # template set (Layout + basic + RawHtml view) — every step deterministic,
    # single-run-able by run_local.py or the orchestrator with no agent
    # improvisation. Semantic component views arrive with P2 promotion.
    module = [
        step("step_namespace_check", "Jackrabbit namespace free/matching", "verify",
             [f"PROBE: bash orchestration/probes/namespace-check.sh {NS} '{URI}'"],
             deps=["step_fidelity_gate"]),
        step("step_scaffold", "Headless scaffold (official templates)", "build",
             [f"Run: bash orchestration/lib/scaffold_module.sh {P} {MODULE}",
              f"PROBE: test -f {PP}/package.json"],
             deps=["step_namespace_check"],
             outputs={"artifact_0": f"{PP}/package.json"}),
        step("step_assets", "Mirror assets -> module static/ + head manifests", "build",
             [f"Run: python3 orchestration/lib/import_assets.py {P}",
              f"PROBE: test -s {PP}/src/templates/css-manifest.json",
              f"PROBE: test -d {PP}/static/assets"],
             deps=["step_scaffold"]),
        step("step_cnd_merge", "Install analyze CND + rule-18 bundles", "build",
             [f"Run: python3 orchestration/lib/merge_cnd.py {P} --ns {NS} --mixns {MIXNS}",
              f"PROBE: bash orchestration/probes/cnd.sh {PP} {NS}",
              f"PROBE: bash orchestration/probes/cnd-patterns.sh {PP} {NS}"],
             deps=["step_scaffold"]),
        step("step_shell_templates", "Agnostic fidelity-shell template set", "build",
             [f"Run: python3 orchestration/lib/install_shell_templates.py {P} --ns {NS}",
              f"PROBE: grep -q 'rawHtml' {PP}/src/components/RawHtml/default.server.tsx"],
             deps=["step_assets", "step_cnd_merge"]),
        step("step_deploy", "Build + deploy to Jahia (deploy gate)", "deploy",
             [f"PROBE[900]: bash orchestration/probes/deploy.sh {PP}",
              f"PROBE: bash orchestration/probes/namespace-check.sh {NS} '{URI}'"],
             deps=["step_shell_templates"]),
    ]

    content = [
        step("step_create_site", "Create the site (provisioning API only)", "build",
             [f"Run: bash orchestration/lib/create_site.sh {SITE} \"{TITLE}\" {MODULE} en,fr",
              f"PROBE: bash orchestration/lib/create_site.sh {SITE} \"{TITLE}\" {MODULE} en,fr"],
             deps=["step_deploy"]),
        step("step_mcp", "MCP write path up", "verify",
             [f"PROBE: bash orchestration/probes/mcp.sh {PP}"],
             deps=["step_create_site"]),
        step("step_pages", "Create pages from the crawl inventory (en+fr, published)", "build",
             [f"Run: python3 orchestration/lib/create_pages.py {P} {SITE} --template basic --locale en",
              f"PROBE: python3 orchestration/lib/mcp_client.py {P} call content.get '{{\"path\":\"/sites/{SITE}/home\",\"locale\":\"en\"}}'"],
             deps=["step_mcp"]),
        step("step_content_load", "Load shells + content via MCP (idempotent clean)", "content",
             [f"Run: python3 orchestration/lib/load_content.py {P} {SITE} --clean --locale en",
              f"PROBE: python3 orchestration/probes/partition.py {P}"],
             deps=["step_pages"]),
        step("step_publish_parity", "default vs live parity", "publish",
             [f"PROBE: bash orchestration/probes/publish-parity.sh {PP} {SITE} en,fr"],
             deps=["step_content_load"]),
        step("step_edit_frame", "Pages editable in jContent", "verify",
             [f"PROBE: bash orchestration/probes/edit-frame.sh {PP} {SITE} en"],
             deps=["step_publish_parity"]),
    ]

    groundtruth = [
        step("step_ground_truth", "GROUND-TRUTH gate: Jahia live vs source mirror (HALT)", "verify",
             [f"PROBE[900]: bash orchestration/probes/groundtruth.sh {P} {SITE} 99",
              "Gate: present groundtruth/review.html per-page fidelity, return status halt."],
             deps=["step_edit_frame"]),
    ]

    def epic(id, title, goal, steps):
        return {"id": id, "title": title, "goal": goal,
                "stories": [{"id": f"story_{id.split('_', 1)[1]}", "title": title,
                             "description": goal, "steps": steps}]}

    return {
        "goal": f"Migrate {URL} to a Jahia JS module (project: {P}, site: {SITE}, ns: {NS}) — v2 full loop, fidelity >=99%/page vs local mirror",
        "repo_dir": p["repo_dir"],
        "model": p["model"],
        "epics": [
            epic("epic_analyze", "Analyze (v2 deterministic + bounded LLM)",
                 "Crawl, mirror-gate, extract candidates + partitions, group, emit CND, extract content, fidelity gate.", analyze),
            epic("epic_module", "Module (scaffold, assets, CND, components, deploy)",
                 "Headless scaffold, asset import, CND merge, components from html-fragments, templates, deploy gate.", module),
            epic("epic_content", "Site + content + publish parity",
                 "Provisioning-API site, MCP content load incl. passthrough, publish parity, editability.", content),
            epic("epic_groundtruth", "Ground truth (Jahia live vs source mirror)",
                 "The P1 exit gate: >=99% render fidelity per page, semantic share reported.", groundtruth),
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--ns", required=True)
    ap.add_argument("--mixns")
    ap.add_argument("--site", required=True)
    ap.add_argument("--module")
    ap.add_argument("--title")
    ap.add_argument("--max-pages", type=int, default=18)
    ap.add_argument("--threshold", type=int, default=95)
    ap.add_argument("--model", default="opencode/deepseek-v4-flash")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--out")
    a = ap.parse_args()
    params = {
        "project": a.project, "url": a.url, "ns": a.ns,
        "mixns": a.mixns or f"{a.ns}mix", "site": a.site,
        "module": a.module or a.project,
        "title": a.title or f"{a.site} (migrated)",
        "max_pages": a.max_pages, "threshold": a.threshold,
        "model": a.model, "repo_dir": a.repo_dir,
    }
    plan = build_plan(params)
    out = a.out or f"orchestration/plans/{a.project}-full.plan.json"
    with open(out, "w") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    n_steps = sum(len(s["steps"]) for e in plan["epics"] for s in e["stories"])
    n_probes = sum(1 for e in plan["epics"] for s in e["stories"] for st in s["steps"]
                   for c in st["acceptance_criteria"] if c.startswith("PROBE"))
    print(f"[gen_plan] {out}: {len(plan['epics'])} epics, {n_steps} steps, {n_probes} probes")


if __name__ == "__main__":
    main()
