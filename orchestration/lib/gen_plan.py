#!/usr/bin/env python3
"""gen_plan.py — source-agnostic migration plan generator.

Generates orchestration plans (epics > stories > steps) from the PROJECT'S OWN
ARTIFACTS — nothing project- or CMS-specific is hardcoded here:

  * orchestration/sitemaps/<project>.txt                    -> sections + page slices
  * projects/<project>/workflow-output/component-manifest.json -> per-component stories,
                                                               namespace derivation
  * orchestration/content/<project>.mainresource.json (optional) -> mainResource steps
  * orchestration/lib/contract.py                           -> consumes/expected_outputs
                                                               + contract.sh probes

Decomposition rules (the story-granularity review, 2026-07):
  1. ONE STORY = ONE STEP = one contained outcome. The engine passes context
     forward only as approved-story summaries; steps inside a story are blind to
     each other. Story granularity IS context granularity.
  2. Work-quantum caps: <= --pages-per-step pages per content step (default 3);
     ONE component per component step.
  3. Deterministic work (extract / media import / mainResource load / startNode
     wiring / gate batteries) is emitted as task_type "script": the engine runs
     the commands directly — no LLM session, no improvisation.
  4. Every step carries ONLY its own criteria — no copy-paste boilerplate.
  5. Contract wiring from contract.py: inputs.consumes + expected_outputs +
     a contract.sh probe whenever the step has a declared contract.

Usage:
  python3 orchestration/lib/gen_plan.py <project> --kind content|build [options]

Options:
  --site <key>          site key                  (default: <project>)
  --lang <lang>         content language          (default: en)
  --langs <csv>         languages for fidelity     (default: --lang)
  --namespace <ns>      CND namespace             (default: derived from manifest)
  --mix-namespace <ns>  mixin namespace           (default: <namespace>mix)
  --pages-per-step <n>  max pages per content step (default: 3)
  --home-page <name>    site home page node name  (default: home — Jahia constant)
  --source-url <url>    reference site URL        (required for --kind build)
  --model <id>          plan model field          (default: none — engine default)
  --out <path>          output file (default: orchestration/plans/<project>-<kind>.gen.plan.json)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract  # single source of truth for step artifact contracts

SKILLS = ".agents/skills"
PROBES = "orchestration/probes"
LIB = "orchestration/lib"


# ── config resolution (derive, never hardcode) ─────────────────────────────────
def load_json(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default


def derive_namespace(manifest: dict) -> str | None:
    """Most common nodeType prefix in the manifest — the project's namespace."""
    prefixes = Counter()
    for c in manifest.get("components", []):
        nt = c.get("nodeType") or ""
        if ":" in nt:
            prefixes[nt.split(":", 1)[0]] += 1
    return prefixes.most_common(1)[0][0] if prefixes else None


def read_sitemap(path: str) -> list[str]:
    """Bare page paths from the sitemap file (comments/blanks stripped)."""
    pages = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            pages.append(line)
    return pages


def group_sections(pages: list[str], home_page: str) -> "OrderedDict[str, list[str]]":
    """Group sitemap pages by first path segment, preserving sitemap order.
    The home page forms its own group."""
    groups: OrderedDict[str, list[str]] = OrderedDict()
    for p in pages:
        key = home_page if p == home_page else p.split("/", 1)[0]
        groups.setdefault(key, []).append(p)
    return groups


def chunk(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ── plan assembly primitives ───────────────────────────────────────────────────
class PlanBuilder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.epics = []

    def epic(self, eid, title, goal, criteria, max_rounds=2, auto_approve=False):
        e = {"id": eid, "title": title, "goal": goal,
             "review_config": {"max_review_rounds": max_rounds,
                               "auto_approve_on_max_rounds": auto_approve,
                               "review_criteria": criteria},
             "stories": []}
        self.epics.append(e)
        return e

    def story_step(self, epic, step_id, title, task_type, criteria,
                   skill=None, inputs=None, script=None, max_attempts=3,
                   description="", agent="code"):
        """ONE STORY = ONE STEP. Story ordering is a linear chain within the epic
        (context flows forward as approved-story summaries)."""
        cfg = self.cfg
        ins = {"project": cfg["project"], "project_path": cfg["project_path"]}
        if inputs:
            ins.update(inputs)
        if skill:
            ins["skill"] = skill
        if script:
            ins["script"] = script

        # contract wiring: consumes + expected_outputs + contract.sh probe
        spec = contract.for_step(step_id, cfg["project"])
        crit = list(criteria)
        if spec["consumes"]:
            ins["consumes"] = spec["consumes"]
        if spec["produces"] or spec["consumes"]:
            probe = f"PROBE: bash {PROBES}/contract.sh {cfg['project_path']} {step_id}"
            if probe not in crit:
                crit.append(probe)
        step = {"id": step_id, "title": title, "task_type": task_type,
                "agent": agent, "depends_on": [], "inputs": ins,
                "acceptance_criteria": crit, "max_attempts": max_attempts}
        if spec["produces"]:
            step["expected_outputs"] = {f"artifact_{i+1}": p for i, p in enumerate(spec["produces"])}

        story_id = "story_" + step_id.removeprefix("step_")
        prev = epic["stories"][-1]["id"] if epic["stories"] else None
        story = {"id": story_id, "title": title,
                 "description": description or title,
                 "depends_on": [prev] if prev else [],
                 "steps": [step]}
        epic["stories"].append(story)
        return story

    def plan(self, goal, readme):
        p = {"_README": readme, "goal": goal, "repo_dir": self.cfg["repo_dir"],
             "epics": self.epics}
        if self.cfg.get("model"):
            p["model"] = self.cfg["model"]
        return p


# ── content plan ───────────────────────────────────────────────────────────────
def content_plan(cfg) -> dict:
    b = PlanBuilder(cfg)
    P, S, L = cfg["project"], cfg["site"], cfg["lang"]
    PP = cfg["project_path"]
    sitemap_ref = f"@{cfg['sitemap']}"

    # epic 1 — foundation
    e1 = b.epic("epic_foundation", "Verify Jahia + module/site",
                "Confirm Jahia is reachable and the module/site are deployed.",
                ["server reachable"], max_rounds=1, auto_approve=True)
    b.story_step(e1, "step_connect", "Verify Jahia connection (Gate 0)", "verify",
                 [f"PROBE: bash {PROBES}/connect.sh {PP}"],
                 skill=f"{SKILLS}/00-migration-start/SKILL.md", max_attempts=2)

    # epic 2 — content, one contained story per outcome
    e2 = b.epic("epic_content", "Create + publish content (per slice)",
                "Populate every page from the captured reference, one small slice "
                "per story; deterministic loaders for mainResource content.",
                ["every page's live rendering matches the captured reference",
                 "listings resolve real content", "no fabricated content"],
                max_rounds=3)

    # calibrate the pixel gate FIRST: measure the noise floor (two renders of the
    # same reference) so the threshold is provably achievable before any agent
    # burns attempts on it. Writes noiseFloorPct (+ raises maxDiffPct if needed)
    # into the project pixel-config.
    b.story_step(
        e2, "step_pixel_calibrate", "Calibrate pixel gate (noise floor)", "script",
        [],
        script=f"bash {PROBES}/pixel-calibrate.sh {PP} {S}",
        max_attempts=2)

    if cfg["has_mainresource"]:
        b.story_step(
            e2, "step_content_mainresources",
            "mainResource content -> contentFolders (BEFORE pages)", "script",
            [f"PROBE: bash {PROBES}/mainresource.sh {P} {S} {L}"],
            script=f"python3 {LIB}/load_main_resources.py {P} {S}",
            max_attempts=2,
            description="Deterministic loader: create + publish all jmix:mainResource "
                        "content into jnt:contentFolders (heroes wired from imported media).")

    # shell story (shared regions on the home page) then per-section slices
    b.story_step(
        e2, f"step_content_shell", "Shell regions: nav / footer / topBar", "build",
        [
            "Populate ONLY the shared shell regions (the AbsoluteArea containers on the "
            "home page: navigation, footer, top bar) with child content mirroring the "
            "captured reference. AbsoluteAreas need child nodes to render in the edit "
            "frame. IDEMPOTENT — reuse existing nodes; do not touch any page main area.",
            f"PROBE: bash {PROBES}/render-all.sh {PP} {S} {L} {cfg['home_page']}",
        ],
        skill=f"{SKILLS}/09b-populate-shell/SKILL.md",
        inputs={"siteKey": S, "language": L, "pages": cfg["home_page"],
                "transport": "jahia-mcp",
                # engine-only session budget (hidden from prompt): shell work
                # includes nav tree + footer content + a deploy cycle
                "_deadline_s": 1800})

    for section, pages in cfg["sections"].items():
        slices = chunk(pages, cfg["pages_per_step"])
        for i, sl in enumerate(slices):
            suffix = slug(section) if len(slices) == 1 else f"{slug(section)}_{i+1}"
            pages_csv = ",".join(sl)
            b.story_step(
                e2, f"step_content_{suffix}",
                f"Content: {section} ({i+1}/{len(slices)}, {len(sl)} page(s))", "build",
                [
                    f"Create + publish ONLY these page(s): {pages_csv}. IDEMPOTENT — reuse "
                    "existing pages and nodes, never recreate or delete published content. "
                    "Fill each page's main area with components mirroring the captured "
                    "reference (content-load.json + the .reference captured truth). Every "
                    "image is a DAM weakreference — never a URL string. Never create "
                    "jmix:mainResource nodes inline in a page main area (they live in "
                    "contentFolders; listings reference them via their query component).",
                    "PIXEL PARITY IS THE EXIT CRITERION: a page is done only when the pixel "
                    "gate passes. On failure, follow the skill's pixel iteration protocol: "
                    f"cat {PP}/workflow-output/pixel/<page-slug>/report.json — it translates "
                    "the pixel diff into DOM landmarks per region (REF vs LOCAL). Fix the "
                    "FIRST divergence (heightHint first), one region at a time; content fixes "
                    "via MCP, rendering fixes in the component view (redeploy + render-all "
                    "before re-measuring). Re-run the gate each iteration; every iteration "
                    "must reduce diffPct. Do NOT weaken the threshold or skip the probe.",
                    f"PROBE: bash {PROBES}/content.sh {PP} {S} {L} {pages_csv}",
                    f"PROBE: bash {PROBES}/render-all.sh {PP} {S} {L} {pages_csv}",
                    f"PROBE: bash {PROBES}/pixel.sh {PP} {S} {L} {pages_csv}",
                ],
                skill=f"{SKILLS}/09a-populate-page/SKILL.md",
                inputs={"siteKey": S, "language": L, "pages": pages_csv,
                        "transport": "jahia-mcp",
                        # engine-only session budget (hidden from prompt),
                        # scaled by slice size: pixel iteration is
                        # build+deploy+probe per cycle (~2-3 min each)
                        "_deadline_s": 1800 + 900 * len(sl)})

    if cfg["has_mainresource"]:
        b.story_step(
            e2, "step_wire_startnodes",
            "Wire listing queries -> contentFolders + remove inline debris (AFTER pages)",
            "script",
            [f"PROBE: bash {PROBES}/startnode.sh {P} {S} {L}",
             f"PROBE: bash {PROBES}/mainresource.sh {P} {S} {L}"],
            script=f"python3 {LIB}/wire_startnodes.py {P} {S}",
            max_attempts=2)

    # epic 3 — quality: deterministic gate battery, then the human-facing report
    e3 = b.epic("epic_quality", "Quality gates + review report",
                "Run the full gate battery over the whole sitemap, then author the "
                "review report from the gate results.",
                ["all gates green over the full sitemap", "review report written"],
                max_rounds=3)
    gate_probes = [
        f"PROBE: bash {PROBES}/content.sh {PP} {S} {L} {sitemap_ref}",
        f"PROBE: bash {PROBES}/pixel.sh {PP} {S} {L} {sitemap_ref}",
        f"PROBE: bash {PROBES}/publish-parity.sh {PP} {S} {L}",
        f"PROBE: bash {PROBES}/edit-frame.sh {PP} {S} {L} {cfg['home_page']}",
        f"PROBE: bash {PROBES}/site-review.sh {PP} {S} {L} {sitemap_ref}",
        f"PROBE: bash {PROBES}/content-fidelity.sh {PP} {S} {cfg['langs']}",
    ]
    if cfg.get("namespace"):
        gate_probes.append(f"PROBE: bash {PROBES}/no-url-images.sh {PP} {S} {cfg['namespace']}")
    b.story_step(e3, "step_gates", "Full-sitemap gate battery", "script",
                 gate_probes, max_attempts=2,
                 description="Deterministic: every content gate over the whole sitemap. "
                             "Failures name the page + defect for the next story.")
    report = f"{PP}/workflow-output/review/REVIEW.md"
    b.story_step(
        e3, "step_review_report", "Author review report (Gate: HALT)", "review",
        [
            f"Author {report} from the gate battery results of the previous story: "
            "per-gate outcome, per-page defects, risks, and what a human should check.",
            f"PROBE: bash {PROBES}/artifact.sh {report}",
            "Gate: present findings, return status halt.",
        ],
        skill=f"{SKILLS}/10-review/SKILL.md",
        inputs={"siteKey": S, "language": L, "report": report},
        agent="reason")  # judgment-heavy: routed to the stronger model

    # epic 4 — fidelity + go-live
    e4 = b.epic("epic_golive", "Visual fidelity + vanity URLs",
                "Per-page fidelity vs the captured reference; redirect map.",
                ["fidelity green on every page", "redirect map generated"],
                max_rounds=2, auto_approve=True)
    b.story_step(e4, "step_visual_diff", "Per-page fidelity vs reference", "script",
                 [f"PROBE: bash {PROBES}/fidelity-all.sh {PP} {S} {L} {sitemap_ref}"],
                 max_attempts=2)
    redirects = f"{PP}/workflow-output/vanity/redirects.map"
    b.story_step(e4, "step_vanity", "Vanity-URL redirect map", "build",
                 [f"PROBE: bash {PROBES}/artifact.sh {redirects}"],
                 skill=f"{SKILLS}/13-vanity-urls/SKILL.md",
                 inputs={"sitemap": cfg["sitemap"], "redirects": redirects})

    return b.plan(
        f"Populate + publish all content for {P} (site {S}, {L}) from the captured "
        "reference — one contained story per slice — then gate, review, and go-live.",
        f"GENERATED by orchestration/lib/gen_plan.py — do not hand-edit; regenerate. "
        f"cmd: python3 orchestration/lib/gen_plan.py {P} --kind content"
        f"{' (mainResource steps included)' if cfg['has_mainresource'] else ''}. "
        "1 story = 1 step; <= " + str(cfg["pages_per_step"]) + " pages per content step; "
        "deterministic steps are task_type=script (no LLM session).")


# ── build plan ─────────────────────────────────────────────────────────────────
def build_plan(cfg) -> dict:
    b = PlanBuilder(cfg)
    P, S, L = cfg["project"], cfg["site"], cfg["lang"]
    PP = cfg["project_path"]
    ns, mix = cfg["namespace"], cfg["mix_namespace"]

    # epic 1 — foundation: connect, analyze (LLM), extract (deterministic)
    e1 = b.epic("epic_foundation", "Connect + analyze + extract",
                "Verify Jahia, analyze the captured reference into the component "
                "manifest, then deterministically extract media + content.",
                ["manifest covers every source component", "extraction from real captured DOM"])
    b.story_step(e1, "step_connect", "Verify Jahia connection (Gate 0)", "verify",
                 [f"PROBE: bash {PROBES}/connect.sh {PP}"],
                 skill=f"{SKILLS}/00-migration-start/SKILL.md", max_attempts=2)
    b.story_step(
        e1, "step_analyze", "Analyze reference -> component manifest (Gate 1: HALT)", "build",
        [
            f"Use the namespace provided in inputs ({ns} / {mix}) for EVERY nodeType in "
            "component-manifest.json — do NOT invent a different prefix.",
            "Content with its own navigable URL (news/blog articles, press releases, events, "
            "products) are jmix:mainResource detail content types: needsMainResource:true.",
            "BROWSER-FIRST CAPTURE (anti-hallucination): if the site is JS-rendered or behind "
            f"a WAF, capture per {SKILLS}/capture-reference/SKILL.md — never improvise from "
            "the static shell alone.",
            "If the source declares its components in the DOM (e.g. Sitecore SXA .component/"
            "field-* markers), extract them deterministically — do not eyeball-discover.",
            "Write ALL 4 outputs: analysis.md, component-manifest.json, content-data.json, "
            "asset-inventory.json.",
            f"PROBE: bash {PROBES}/analyze.sh {PP}",
            "Gate 1: present section map + field splits, return status halt.",
        ],
        skill=f"{SKILLS}/01-analyze-website/SKILL.md",
        inputs={"siteUrl": cfg["source_url"], "namespace": ns, "mixNamespace": mix})
    b.story_step(
        e1, "step_extract", "Deterministic ETL: media manifest + content-load", "script",
        [f"PROBE: bash {PROBES}/extract.sh {PP} {S}"],
        script=[f"python3 {LIB}/source_detect.py {P}",
                f"python3 {LIB}/extract_media.py {P} {S}",
                f"python3 {LIB}/extract_content.py {P} {S}"],
        max_attempts=2)

    # epic 2 — scaffold + assets
    e2 = b.epic("epic_scaffold", "Scaffold module + import assets",
                "Create the JS module and the tokenized theme.",
                ["module builds", "theme tokenized to :root vars"])
    b.story_step(e2, "step_scaffold", "Scaffold JS module (Gate 2: HALT)", "build",
                 [f"PROBE: bash {PROBES}/build.sh {PP}",
                  "Gate 2: present structure + namespace, return status halt."],
                 skill=f"{SKILLS}/02-scaffold-module/SKILL.md",
                 inputs={"moduleName": P, "namespace": ns, "mixNamespace": mix})
    b.story_step(e2, "step_assets", "Import + tokenize theme assets", "build",
                 [f"PROBE: bash {PROBES}/assets.sh {PP}",
                  f"CSS tokenized into :root theme vars + site-theme mixin + Layout override "
                  f"wiring: PROBE: bash {PROBES}/css-tokens.sh {PP}"],
                 skill=f"{SKILLS}/03-import-assets/SKILL.md")

    # epic 3 — content model + structural components
    e3 = b.epic("epic_model", "Content types + structural components",
                "CND for every manifest component; navigation/query/grid structural trio.",
                ["every manifest component declared", "CND gates green"])
    b.story_step(
        e3, "step_content_types", "Define all content types (CND)", "build",
        [
            "Use the CND authoring skill references for non-trivial modeling; weakreferences "
            "need a TYPE constraint (e.g. `< jmix:image`), not just a picker.",
            f"PROBE: bash {PROBES}/cnd.sh {PP} {ns}",
            f"PROBE: bash {PROBES}/cnd-patterns.sh {PP} {ns}",
            f"PROBE: bash {PROBES}/cnd-review.sh {PP}",
            f"No two types may share a property shape (consolidate into one type + views): "
            f"PROBE: bash {PROBES}/dup-shapes.sh {PP} {ns}",
            f"Write the per-project reuse baseline: PROBE: bash {PROBES}/inventory.sh {PP} {ns} "
            f"--write {PP}/component-baseline.txt",
        ],
        skill=f"{SKILLS}/04-define-content-types/SKILL.md",
        inputs={"namespace": ns})
    b.story_step(e3, "step_navigation", "Navigation component (page-tree menu)", "build",
                 [f"PROBE: bash {PROBES}/component.sh {PP} Navigation"],
                 skill=f"{SKILLS}/05-implement-navigation/SKILL.md")
    b.story_step(e3, "step_jcr_query", "JCRQuery listing component", "build",
                 [f"PROBE: bash {PROBES}/component.sh {PP} JCRQuery"],
                 skill=f"{SKILLS}/06-implement-jcr-query/SKILL.md")
    b.story_step(e3, "step_grid_row", "GridRow layout component", "build",
                 [f"PROBE: bash {PROBES}/component.sh {PP} GridRow"],
                 skill=f"{SKILLS}/06-implement-jcr-query/SKILL.md")

    # epic 4 — components: ONE STORY PER MANIFEST COMPONENT, then the module gate
    e4 = b.epic("epic_components", "Implement components (one per story)",
                "Each manifest component implemented + validated as its own story; "
                "module-wide gate at the end.",
                ["every component complete (no stubs)", "module builds + i18n complete"],
                max_rounds=3)
    for comp in cfg["components"]:
        nt = comp["nodeType"]
        local = nt.split(":", 1)[1] if ":" in nt else nt
        b.story_step(
            e4, f"step_component_{slug(local)}",
            f"Component: {nt}", "build",
            [
                f"Implement ONLY the component for nodeType {nt} exactly as specified in "
                "the manifest entry (fields, container/children, area type, mainResource "
                "flag) and its captured HTML fragment. IDEMPOTENT — if it already exists "
                "and passes its probe, verify and finish; do not churn other components.",
                f"PROBE: bash {PROBES}/component-one.sh {PP} {ns} {nt}",
            ],
            skill=f"{SKILLS}/07-implement-components/SKILL.md",
            inputs={"component": nt})
    b.story_step(
        e4, "step_components_gate", "Module-wide component gate", "script",
        [f"PROBE: bash {PROBES}/components-all.sh {PP} {ns}",
         f"PROBE: bash {PROBES}/css-hooks.sh {PP} {ns}"],
        script=f"python3 {LIB}/scaffold_cm_views.py {PP}",
        max_attempts=2,
        description="Deterministic: scaffold any missing cm (jContent preview) views, then "
                    "the full per-component completeness gate + one module build.")

    # epic 5 — templates + deploy
    e5 = b.epic("epic_deploy", "Page templates + deploy",
                "Templates by page role; deploy the module.",
                ["templates govern areas", "bundle active + shell renders"])
    b.story_step(e5, "step_templates", "Page templates (by role)", "build",
                 [f"PROBE: bash {PROBES}/templates.sh {PP}",
                  f"2-3 page templates by ROLE (home/section/detail); restrict each Area with "
                  f"allowedNodeTypes: PROBE: bash {PROBES}/template-govern.sh {PP}"],
                 skill=f"{SKILLS}/08-page-templates/SKILL.md")
    b.story_step(e5, "step_deploy", "Build + deploy module (Gate 3: HALT)", "build",
                 [f"PROBE: bash {PROBES}/deploy.sh {PP}",
                  f"Render-gate the deployed shell: PROBE: bash {PROBES}/render-all.sh {PP} {S} "
                  f"{L} /{cfg['home_page']}",
                  "Gate 3: present deployed shell screenshot, return status halt."],
                 skill=f"{SKILLS}/support-deploy/SKILL.md")

    # epic 6 — media import (deterministic)
    e6 = b.epic("epic_media", "Import media to DAM",
                "Deterministic import of every extracted image.",
                ["every manifest image imported"])
    b.story_step(e6, "step_media", "Import media manifest -> DAM", "script",
                 [f"PROBE: bash {PROBES}/media.sh {PP} {S}"],
                 script=f"python3 orchestration/images/import.py {P}",
                 max_attempts=2)

    plan = b.plan(
        f"Migrate {cfg['source_url'] or 'the captured reference'} to Jahia module+site "
        f"{P} — build phase (module, components, templates, media). Run the generated "
        "content plan afterwards.",
        f"GENERATED by orchestration/lib/gen_plan.py — do not hand-edit; regenerate. "
        f"cmd: python3 orchestration/lib/gen_plan.py {P} --kind build --source-url "
        f"{cfg['source_url']}. 1 story = 1 step; 1 component per story; deterministic "
        "steps are task_type=script.")
    return plan


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--kind", choices=["content", "build"], required=True)
    ap.add_argument("--site")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--langs")
    ap.add_argument("--namespace")
    ap.add_argument("--mix-namespace")
    ap.add_argument("--pages-per-step", type=int, default=3)
    ap.add_argument("--home-page", default="home")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--out")
    a = ap.parse_args()

    project = a.project
    repo_dir = os.getcwd()
    project_path = f"projects/{project}"
    manifest = load_json(f"{project_path}/workflow-output/component-manifest.json", {})
    sitemap = f"orchestration/sitemaps/{project}.txt"
    mainresource_cfg = f"orchestration/content/{project}.mainresource.json"

    ns = a.namespace or derive_namespace(manifest)
    cfg = {
        "project": project,
        "project_path": project_path,
        "repo_dir": repo_dir,
        "site": a.site or project,
        "lang": a.lang,
        "langs": a.langs or a.lang,
        "namespace": ns,
        "mix_namespace": a.mix_namespace or (f"{ns}mix" if ns else None),
        "pages_per_step": a.pages_per_step,
        "home_page": a.home_page,
        "source_url": a.source_url,
        "model": a.model,
        "sitemap": sitemap,
        "has_mainresource": os.path.exists(mainresource_cfg),
        "components": manifest.get("components", []),
    }

    if a.kind == "content":
        if not os.path.exists(sitemap):
            sys.exit(f"gen_plan: sitemap not found: {sitemap}")
        pages = read_sitemap(sitemap)
        if not pages:
            sys.exit(f"gen_plan: sitemap is empty: {sitemap}")
        cfg["sections"] = group_sections(pages, a.home_page)
        plan = content_plan(cfg)
    else:
        if not a.source_url:
            sys.exit("gen_plan: --source-url is required for --kind build")
        if not cfg["components"]:
            sys.exit(f"gen_plan: no components in {project_path}/workflow-output/"
                     "component-manifest.json — run analyze first (build plans need the "
                     "manifest to enumerate per-component stories)")
        if not ns:
            sys.exit("gen_plan: could not derive --namespace from the manifest; pass it explicitly")
        plan = build_plan(cfg)

    out = a.out or f"orchestration/plans/{project}-{a.kind}.gen.plan.json"
    json.dump(plan, open(out, "w"), indent=2, ensure_ascii=False)

    n_stories = sum(len(e["stories"]) for e in plan["epics"])
    n_script = sum(1 for e in plan["epics"] for s in e["stories"]
                   for st in s["steps"] if st["task_type"] == "script")
    print(f"gen_plan: wrote {out}")
    print(f"  epics={len(plan['epics'])} stories={n_stories} (1 step each) "
          f"script-steps={n_script} pages-per-step<={a.pages_per_step}")
    for e in plan["epics"]:
        print(f"  {e['id']:22s} {len(e['stories'])} stories")


if __name__ == "__main__":
    main()
