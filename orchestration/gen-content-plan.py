#!/usr/bin/env python3
"""Generate a focused content-completion plan with the content epic decomposed
into PER-SECTION steps (the components-all lesson applied to pages: a monolithic
content step can't reliably create 40+ pages in one agent turn). Reuses the
already-done foundation/scaffold/model/components artifacts (they persist in
Jahia + on disk); re-runs only connect (sanity) + decomposed content + fidelity.

Usage: gen-content-plan.py <base_plan.json> <sitemap.txt> <out_plan.json>
"""
import json, re, sys
base_plan, sitemap, out = sys.argv[1:4]
P = json.load(open(base_plan))
proj = "projects/" + P["goal"].split("project: ")[1].split(",")[0].strip()
# pull canonical inputs off the base plan's analyze step
inp = {}
for e in P["epics"]:
    for s in e["stories"]:
        for st in s["steps"]:
            inp.setdefault("project", st["inputs"].get("project"))
            if st["id"] == "step_content":
                inp.update({k: st["inputs"].get(k) for k in ("siteKey","language","project","project_path")})
project = inp["project"]; site = inp["siteKey"]; lang = inp["language"]; ppath = inp["project_path"]

pages = [re.sub(r"#.*","",l).strip() for l in open(sitemap)]
pages = [p for p in pages if p]
from collections import OrderedDict
sections = OrderedDict()
for p in pages:
    top = "home" if p == "home" else p.split("/")[0]
    sections.setdefault(top, []).append(p)

def content_step(sec, sec_pages, prev):
    slice_csv = ",".join(sec_pages)
    return {
        "id": f"step_content_{sec.replace('-','_')}",
        "title": f"Content: {sec} ({len(sec_pages)} pages)",
        "task_type": "build", "agent": "code",
        "depends_on": [prev] if prev else [],
        "inputs": {"project": project, "project_path": ppath, "siteKey": site,
                   "language": lang, "pages": slice_csv, "transport": "jahia-mcp",
                   "skill": ".agents/skills/09-create-content/SKILL.md"},
        "acceptance_criteria": [
            f"Create + publish ONLY this section's pages ({slice_csv}). Use the Jahia MCP server; IDEMPOTENT — reuse existing pages, never recreate. Fill each page's main area with components mirroring the reference (content-data.json / .reference captured truth); images = DAM weakreferences (no url strings).",
            "For the home/shell section, also populate the nav + footer AbsoluteArea regions with child content (AbsoluteArea-needs-children) so they render in the edit frame.",
            f"PROBE: bash orchestration/probes/content.sh {ppath} {site} {lang} {slice_csv}",
            f"PROBE: bash orchestration/probes/render-all.sh {ppath} {site} {lang} {slice_csv}",
            f"PROBE: bash orchestration/probes/no-url-images.sh {ppath} {site} {inp.get('namespace','lsp')}",
        ],
        "max_attempts": 3,
    }

# build per-section content steps as a dependency chain (one section per turn)
content_steps = []
prev = None
# home first (shell), then the rest
order = ["home"] + [s for s in sections if s != "home"]
for sec in order:
    st = content_step(sec, sections[sec], prev)
    content_steps.append(st); prev = st["id"]

allpages = ",".join(pages)
review_step = {
    "id": "step_review", "title": "Content review (Gate: HALT)", "task_type": "review",
    "agent": "code", "depends_on": [prev],
    "inputs": {"project": project, "project_path": ppath, "siteKey": site, "language": lang,
               "report": f"{ppath}/workflow-output/review/REVIEW.md",
               "skill": ".agents/skills/10-review/SKILL.md", "agentDef": ".claude/agents/jahia-reviewer.md"},
    "acceptance_criteria": [
        "Use the jahia-reviewer agent: run ALL gate probes over the WHOLE sitemap + write REVIEW.md.",
        f"PROBE: bash orchestration/probes/content.sh {ppath} {site} {lang} @{sitemap}",
        f"PROBE: bash orchestration/probes/publish-parity.sh {ppath} {site} {lang}",
        f"PROBE: bash orchestration/probes/edit-frame.sh {ppath} {site} {lang} home",
        f"PROBE: bash orchestration/probes/site-review.sh {ppath} {site} {lang} @{sitemap}",
        f"PROBE: bash orchestration/probes/artifact.sh {ppath}/workflow-output/review/REVIEW.md",
        "Gate: present findings, return status halt.",
    ], "max_attempts": 3,
}

plan = {
  "_README": f"FOCUSED content-completion run for {project} — content epic DECOMPOSED per section ({len(sections)} sections). Reuses already-deployed module + site + components (persist). Run: ORCH_URL=http://localhost:8001 bash orchestration/run.sh {out} --start",
  "goal": f"Complete + publish all content for {project} (site {site}, {lang}), one section at a time, then review + fidelity. Module/site/components already exist.",
  "repo_dir": P["repo_dir"], "model": P["model"], "github_repo": P.get("github_repo"),
  "epics": [
    {"id":"epic_foundation","title":"Verify Jahia + module/site","goal":"Confirm Jahia reachable and the module/site are deployed.",
     "review_config":{"max_review_rounds":1,"auto_approve_on_max_rounds":True,"review_criteria":["server reachable"]},
     "stories":[{"id":"story_connect","title":"Connect","description":"Verify connectivity.","steps":[
        {"id":"step_connect","title":"Verify Jahia connection (Gate 0)","task_type":"verify","agent":"code",
         "inputs":{"project":project,"project_path":ppath,"skill":".agents/skills/00-migration-start/SKILL.md"},
         "acceptance_criteria":[f"PROBE: bash orchestration/probes/connect.sh {ppath}"],"max_attempts":2}]}]},
    {"id":"epic_content_quality","title":"Create + publish content (per section)","goal":"Create + publish every page's content, one section per step; then review.",
     "review_config":{"max_review_rounds":3,"auto_approve_on_max_rounds":False,
        "review_criteria":["every page live <main> > 400 chars","fidelity per section","axe 0 critical/serious"]},
     "stories":[
        {"id":"story_content_create","title":"Create content per section","description":"One step per sitemap section; idempotent; gated per slice.","depends_on":["story_connect"],"steps":content_steps},
        {"id":"story_review","title":"Review + accessibility","description":"Full-sitemap gates + REVIEW.md.","depends_on":["story_content_create"],"steps":[review_step]},
     ]},
    {"id":"epic_fidelity_golive","title":"Visual diff + vanity URLs","goal":"Per-page fidelity vs the captured reference, + redirect map.",
     "review_config":{"max_review_rounds":2,"auto_approve_on_max_rounds":True,"review_criteria":["fidelity-all green","redirect map generated"]},
     "stories":[{"id":"story_fidelity","title":"Fidelity + vanity","description":"fidelity-all + vanity.","depends_on":["story_review"],"steps":[
        {"id":"step_visual_diff","title":"Visual diff","task_type":"review","agent":"code",
         "inputs":{"project":project,"project_path":ppath,"siteKey":site,"language":lang,"skill":".agents/skills/12-visual-diff/SKILL.md"},
         "acceptance_criteria":[f"PROBE: bash orchestration/probes/fidelity-all.sh {ppath} {site} {lang} @{sitemap}"],"max_attempts":3},
        {"id":"step_vanity","title":"Vanity-URL redirect map","task_type":"build","agent":"code","depends_on":["step_visual_diff"],
         "inputs":{"project":project,"project_path":ppath,"sitemap":sitemap,"redirects":f"{ppath}/workflow-output/vanity/redirects.map","skill":".agents/skills/13-vanity-urls/SKILL.md"},
         "acceptance_criteria":[f"PROBE: bash orchestration/probes/artifact.sh {ppath}/workflow-output/vanity/redirects.map"],"max_attempts":3}]}]},
  ],
}
json.dump(plan, open(out,"w"), ensure_ascii=False, indent=2)
nsteps = sum(len(s["steps"]) for e in plan["epics"] for s in e["stories"])
print(f"wrote {out}: {len(plan['epics'])} epics, {nsteps} steps ({len(content_steps)} per-section content steps)")
