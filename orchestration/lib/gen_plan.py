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


def review_step(id, title, criteria, deps=None, inputs=None):
    """Scheduled decision point (ASSIST-PLAN §3 A6): the engine NEVER sends it
    to an agent — when selected it becomes decision_pending and the run pauses.
    Exempt from the deploy/content PROBE lint (no PROBE lines by design)."""
    s = step(id, title, "verify", criteria, deps=deps, inputs=inputs)
    s["review"] = True
    return s


def build_plan(p):
    P, URL, NS, MIXNS = p["project"], p["url"], p["ns"], p["mixns"]
    SITE, MODULE, TITLE = p["site"], p["module"], p["title"]
    N, THR = p["max_pages"], p["threshold"]
    ARCH = p.get("archetypes", False)
    # archetype (semantic) model: fidelity gates (byte-exact compose / pixel
    # reconstruct / skeleton component-coverage) DEMOTE to advisory — the semantic
    # model deliberately drifts from source pixels; authoring gates (cnd-review)
    # become blocking. `adv` wraps a probe as a non-gating Run: under the arch model.
    def adv(probe):
        if not ARCH:
            return probe
        body = probe.split(":", 1)[1].strip() if ":" in probe else probe
        return f"Run: {body} || true"
    K = p.get("per_cluster", 3)  # legacy knob — per-page doctrine ignores it (--all-pages)
    SEGMENTATION = p.get("segmentation", "vision")
    # CONTENT_LOCALES — the locale(s) the migration actually LOADS content in
    # (load_content --locale). The site is created en,fr so editors CAN add FR
    # later, but a source-faithful migration only loads what the SOURCE has, so
    # publish-parity must assert translation parity across the LOADED locales,
    # not a hardcoded en,fr (an English-only source has no FR content to load —
    # demanding FR there checks the wrong thing). Defaults to the primary "en".
    CLOC = (p.get("content_locales") or "en").strip()
    PRIMARY_LOCALE = CLOC.split(",")[0]
    PP = f"projects/{P}"
    URI = f"https://jahia.com/{P}/nt/1.0"
    common = {"project": P, "project_path": PP, "namespace": NS,
              "mixNamespace": MIXNS, "siteKey": SITE, "moduleName": MODULE}

    # ── segmentation gate (protocol v2, ASSIST-PLAN §7) ──────────────────
    # The REAL segmentation work is an engine-enforced PROBE (segment_probe is
    # incremental, so retries never re-bill vision; a Run: agent step would hit
    # the 600s opencode completion deadline). Strategy patches with
    # arm_swap=false must carry this line VERBATIM (plan lint).
    # PER-PAGE doctrine (2026-07-06): --all-pages segments EVERY inventory page
    # and the gate is every-page-green. Per-cluster sampling left unsampled
    # pages' specific content as ONE anonymous rawHtml blob each (signature
    # matching only types recurring components) — the fragment-soup failure the
    # component_coverage gate now also blocks downstream.
    SEG_PROBE = (f"PROBE[2700]: node orchestration/lib/segment_probe.mjs {PP} "
                 f"--consensus --stability 3 --all-pages")

    # heuristic-arm criteria — the SAME lines gen_plan emits for
    # --segmentation heuristic; reused verbatim by the heuristic_arm swap.
    heuristic_criteria = [
        f"Run: python3 orchestration/lib/group_llm.py {PP} --model deepseek-v4-flash --ns {NS} --out {PP}/workflow-output/grouping.json",
        f"PROBE: python3 orchestration/lib/assemble_manifest.py {PP}/workflow-output/semantic-candidates.json --group {PP}/workflow-output/grouping.json --ns {NS} --out {PP}/workflow-output/component-manifest.json"]

    # Pre-registered strategy library for the segmentation decision point
    # (ASSIST-PLAN §4 B4-B6). consensus3/per-cluster sampling are NOT
    # strategies — they ARE the v2 default probe. Each strategy is single-shot.
    seg_strategies = [
        {"id": "claude_adjudicate",
         "title": "Assistant adjudicates red pages from overlays (GREEN-BY-ADJUDICATION)",
         "when": "on_retries_exhausted", "order": 1, "arm_swap": False, "halt": False,
         "patches": [{"step_id": "step_segment",
                      "inputs": {"project": PP},
                      "acceptance_criteria": [
                          f"Run: node orchestration/lib/adjudicate_ingest.mjs {PP}",
                          SEG_PROBE]}],
         "skip": [],
         "notes": ("The assistant reviews <slug>.segmap.html + <slug>.page.png and writes "
                   f"{PP}/workflow-output/segment/adjudication/<slug>.json (rootIds validated "
                   "against the real block universe — hallucination-impossible). ingest "
                   "converts them to adjudicated segmentations; the SAME probe then re-checks "
                   "cluster majority with adjudicated pages counting green-by-adjudication.")},
        {"id": "ab_test",
         "title": "A/B evidence: heuristic arm vs vision arm on the same frozen mirror",
         "when": "on_retries_exhausted", "order": 2, "arm_swap": False, "halt": False,
         "patches": [{"step_id": "step_segment",
                      "inputs": {"project": PP},
                      "acceptance_criteria": [
                          "Run: echo ab evidence",
                          f"PROBE[2700]: bash orchestration/lib/ab_segment.sh {PP}",
                          SEG_PROBE]}],
         "skip": [],
         "notes": ("Information strategy: runs the heuristic arm into "
                   f"{PP}/workflow-output/ab/heuristic/ (never clobbers the real artifacts) and "
                   f"writes {PP}/workflow-output/segment/ab-report.json. The original gate is "
                   "unchanged and probably still red — the NEXT decision has the A/B report.")},
        {"id": "heuristic_arm",
         "title": "Arm swap: heuristic grouping (group_llm + assemble_manifest)",
         "when": "on_retries_exhausted", "order": 3, "arm_swap": True, "halt": False,
         "patches": [{"step_id": "step_group",
                      "inputs": {"project": PP},
                      "acceptance_criteria": heuristic_criteria}],
         "skip": ["step_segment"],
         "notes": ("Whole pre-registered arm swap (generator-emitted, exempt from the verbatim-"
                   "PROBE lint): step_segment is skipped and step_group becomes the exact "
                   "criteria gen_plan emits for --segmentation heuristic.")},
        {"id": "manual_review",
         "title": "Manual review (Julian): halt with the segmentation bundle",
         "when": "on_retries_exhausted", "order": 4, "arm_swap": False, "halt": True,
         "patches": [], "skip": [],
         "notes": ("Converts the decision into halted (gate_type: segmentation) with the review "
                   "bundle (segmap overlays, consensus diff). Overriding a red segmentation "
                   "gate is Julian's prerogative only — recorded as a waiver.")},
    ]

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
             [f"Run: python3 orchestration/lib/scope_apply.py {PP}",
              f"Run: python3 orchestration/lib/semantic_extract.py {PP}",
              f"PROBE: test -s {PP}/workflow-output/semantic-candidates.json",
              f"PROBE: test -s {PP}/workflow-output/semantic-templates.json"],
             deps=["step_localize"]),
        # component model: VISION segmentation is the shipping default (the P2
        # A/B winner judged by the ground-truth gate); --segmentation heuristic
        # keeps the LLM-grouping arm for comparisons. The vision step keeps the
        # id "step_group" so every downstream dependency is identical.
        # step_segment's Run: is a trivial echo — the REAL work is the engine-
        # enforced PROBE (avoids the 600s opencode completion deadline;
        # segment_probe is incremental so retries never re-bill vision).
        # max_attempts 2 (not 3): the N=3 consensus already absorbs vision
        # nondeterminism, so a red verdict is signal, not noise — one auto-retry
        # (continuing incrementally where the first left off), then the decision
        # ladder takes over instead of re-billing another full vision round.
        *([{**step("step_segment", "Vision segmentation (protocol v2: consensus, ALL pages)", "build",
                   ["Run: echo segmentation is executed by the engine probe",
                    SEG_PROBE],
                   deps=["step_semantic"], max_attempts=2),
            "strategies": seg_strategies},
           step("step_group", ("Vision -> SEMANTIC archetype manifest" if ARCH
                                else "Vision -> manifest + contribution dial"), "build",
                [f"Run: python3 orchestration/lib/segment2manifest.py {P} --ns {NS} --mixns {MIXNS}"
                 + (" --archetypes" if ARCH else ""),
                 f"Run: python3 orchestration/lib/make_overrides.py {P} --module {MODULE}",
                 f"PROBE: test -s {PP}/workflow-output/component-manifest.json",
                 f"PROBE: test -s {PP}/workflow-output/passthrough-overrides.json"],
                deps=["step_segment"])]
          if SEGMENTATION == "vision" else
          [step("step_group", "LLM grouping (bounded) + partition gate", "build",
                heuristic_criteria,
                deps=["step_semantic"])]),
        # Scheduled decision point A6-1: the assistant judges the component
        # model EDITORIALLY (migration rule 21) before any extraction — may
        # emit pattern-keyed scope rules or proceed. Reached ALWAYS.
        review_step("step_model_review", "Model review (scheduled decision point)",
                    [f"Review: {PP}/workflow-output/component-manifest.json (names, grouping altitude, chrome vs content) and {PP}/workflow-output/segment/*.segmap.html overlays.",
                     f"Decide: POST /runs/{{run_id}}/steps/step_model_review/decide with action=proceed, OR rules (exclude / force_passthrough, pattern-keyed CSS selectors — never page URLs) appended to {PP}/workflow-output/scope-rules.json + action=apply_and_rerun.",
                     "Gate: scheduled decision point — the engine pauses (decision_pending); this step is never sent to an agent."],
                    deps=["step_group"]),
        # P5.6: generic, CMS-reusable NAMING of zones/components (metadata only,
        # never site content) — DeepSeek proposes clean names + near-dupe merges
        # and REWRITES the manifest (--apply) BEFORE extraction/CND, so the type
        # names an editor sees are generic and reusable (migration rule 21, moved
        # from a manual review note into a deterministic assisted step). Runs
        # AFTER the model-review gate (the assistant has already judged the model)
        # and BEFORE extraction (which keys off the manifest node types). A run
        # with no LLM key is a no-op passthrough (script exits leaving the
        # manifest untouched only if configured); the PROBE just asserts the
        # manifest still parses + carries components.
        step("step_naming", "Generic zone/component naming (--apply, future-run manifest)", "build",
             [f"Run: python3 orchestration/lib/name_model.py {PP} --apply",
              f"PROBE: python3 -c \"import json,sys; d=json.load(open('{PP}/workflow-output/component-manifest.json')); sys.exit(0 if d.get('components') else 1)\"",
              f"PROBE: test -s {PP}/workflow-output/naming-proposals.json"],
             deps=["step_model_review"]),
        # P2.5: extraction BEFORE the CND — cnd_emit sizes the body..bodyN
        # richtext props per type from the OBSERVED lift (wired-only types:
        # a declared-but-unwired prop is a dead prop, G1 forbids it)
        step("step_content_extract", "Content-load payload + partition/contribution/component gates", "build",
             [f"Run: python3 orchestration/lib/extract_content.py {P}",
              # archetype model: map the skeleton content-load onto the semantic
              # archetype field surface (title/body/image/cta + typed children).
              *([f"Run: python3 orchestration/lib/semanticize_content.py {P} "
                 f"--manifest {PP}/workflow-output/component-manifest.json"] if ARCH else []),
              # archetype-model blocking gate: the content-load is the semantic
              # model AND every page carries instances (skeleton content-load
              # probes are advisory below — skeleton-specific, they crash/mismatch
              # on the semantic shape).
              *([f"PROBE: python3 -c \"import json,sys; d=json.load(open('orchestration/content/{P}.content-load.json')); "
                 f"sys.exit(0 if d.get('model')=='archetype' and all(p.get('instances') for p in d['pages'].values()) else 1)\""]
                if ARCH else []),
              adv(f"PROBE: python3 orchestration/probes/partition.py {P}"),
              adv(f"PROBE: python3 orchestration/probes/contribution.py {P}"),
              # component-model gate (2026-07-06): visible text must live in
              # TYPED components — fragment soup (one big rawHtml blob per
              # page) can never pass again. Advisory under the archetype model
              # (its typed-share notion is skeleton-specific).
              adv(f"PROBE: python3 orchestration/probes/component_coverage.py {P}")],
             deps=["step_naming"]),
        # COMPOSE GATE (ASSIST-PLAN): pre-Jahia qualitative gate — the extracted
        # content must re-compose each page EXACTLY as the Jahia LIVE views will
        # (skeletonRender.ts composeNode semantics) and match the scoped mirror
        # BYTE-FOR-BYTE, with a human-reviewable side-by-side. Byte-exactness is
        # the frozen bar (rule 23); the partition/contribution gates judge the
        # payload's accounting, this replays the LIVE composition end-to-end.
        step("step_compose_gate", "Compose gate (byte-exact vs mirror + side-by-side)", "verify",
             [f"Run: python3 orchestration/lib/compose_probe.py {PP}" + (" || true" if ARCH else ""),
              adv(f"PROBE: bash orchestration/probes/compose.sh {PP}"),
              f"Gate: compose review at {PP}/workflow-output/compose/compose-review.html"],
             deps=["step_content_extract"]),
        step("step_cnd", "Emit CND + view plan (wired-only sizing)", "build",
             [f"Run: python3 orchestration/lib/cnd_emit.py {PP}/workflow-output/component-manifest.json --ns {NS} --mixns {MIXNS} --project {P} --out-cnd {PP}/workflow-output/definitions.cnd --out-views {PP}/workflow-output/views.json --content-load orchestration/content/{P}.content-load.json",
              f"PROBE: test -s {PP}/workflow-output/definitions.cnd",
              f"PROBE: grep -q \"{NS} = \" {PP}/workflow-output/definitions.cnd",
              f"PROBE: test -s {PP}/workflow-output/views.json"],
             deps=["step_content_extract", "step_compose_gate"]),
        step("step_fidelity_gate", "Fidelity gate (HALT: human reviews review.html)", "verify",
             [adv(f"PROBE[900]: node orchestration/lib/reconstruct_probe.mjs {PP} 10 {THR}"),
              "Gate: present worst pages + semantic share, return status halt."],
             deps=["step_cnd"]),
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
              f"PROBE: bash orchestration/probes/cnd-patterns.sh {PP} {NS}",
              # AUTHORING lint (agentic check-cnd via cnd-review.sh): flags
              # rawStringLink / missingI18n / directDroppable / singleHardcodedCta /
              # weakrefNoConstraint on the emitted CND — the exact authoring-model
              # antipatterns. WARN-FIRST (|| true) during P1: it reports violations
              # in the step log without gating, until the semantic emitter (task
              # #24) can pass it. FLIP to `PROBE:` (blocking) once it does.
              # AUTHORING lint: BLOCKING under the archetype model (the semantic
              # CND passes check-cnd 1.00); advisory (warn) under skeleton.
              (f"PROBE: bash orchestration/probes/cnd-review.sh {PP}" if ARCH
               else f"Run: bash orchestration/probes/cnd-review.sh {PP} || true")],
             deps=["step_scaffold"]),
        # P5.6: editor-UI field labels + ui.tooltip keys, EN+FR (rule 18 / i18n.md)
        # — these are AUTHORING-INTERFACE chrome strings, the ONE sanctioned EN/FR
        # generation (never visitor content). Runs AFTER merge_cnd emits the
        # boilerplate bundles and OVERWRITES them with context-aware labels +
        # one-sentence useful tooltips (--apply). Non-manifest keys (JCR Query /
        # Grid Row / Raw HTML / contrib slot mixins) are preserved verbatim. The
        # PROBE re-asserts EN/FR key parity is not broken (i18n-check contract).
        step("step_bundles", "Editor-UI field labels + tooltips (EN/FR, --apply)", "build",
             [f"Run: python3 orchestration/lib/gen_bundles.py {PP} --module {MODULE} --ns {NS} --mixns {MIXNS} --apply",
              f"PROBE: test -s {PP}/settings/resources/{MODULE}_en.properties",
              f"PROBE: test -s {PP}/settings/resources/{MODULE}_fr.properties",
              f"PROBE: python3 -c \"import sys; g=lambda p:{{l.split('=',1)[0].strip() for l in open(p,encoding='utf-8') if l.strip() and not l.startswith('#') and '=' in l}}; en=g('{PP}/settings/resources/{MODULE}_en.properties'); fr=g('{PP}/settings/resources/{MODULE}_fr.properties'); sys.exit(0 if en==fr else 1)\""],
             deps=["step_cnd_merge"]),
        step("step_shell_templates", "Agnostic fidelity-shell template set + skeleton views", "build",
             [f"Run: python3 orchestration/lib/install_shell_templates.py {P} --ns {NS} --manifest {PP}/workflow-output/component-manifest.json",
              f"PROBE: grep -q 'rawHtml' {PP}/src/components/RawHtml/default.server.tsx",
              # TEMPLATE GOVERNANCE (governed Areas: allowedNodeTypes / numberOfItems).
              # WARN-FIRST (|| true) during P1: reports ungoverned Areas without
              # gating, until role-clustered governed templates land (redesign §11.3).
              # FLIP to `PROBE:` once templates are governed.
              f"Run: bash orchestration/probes/template-govern.sh {PP} {NS} || true"],
             deps=["step_assets", "step_cnd_merge", "step_bundles"]),
        step("step_deploy", "Build + deploy to Jahia (deploy gate)", "deploy",
             [f"PROBE[900]: bash orchestration/probes/deploy.sh {PP}",
              f"PROBE: bash orchestration/probes/namespace-check.sh {NS} '{URI}'"],
             deps=["step_shell_templates"]),
    ]

    # Content phase. Beyond each step's own PROBE gate, the ENGINE runs a
    # plan-independent INTEGRITY BELT after step_pages / step_content_load /
    # step_publish_parity pass (verifier.run_integrity_belt →
    # orchestration/probes/integrity.py, phase = step id): it diffs the live
    # Jahia against page-inventory / content-load / dam artifacts, so a weak step
    # probe (content.get on /home alone) can no longer hide a hollow site. The
    # belt reads inputs.site (emitted below), falling back to the project
    # basename for older plans.
    content = [
        step("step_create_site", "Create the site (provisioning API only)", "build",
             [f"Run: bash orchestration/lib/create_site.sh {SITE} \"{TITLE}\" {MODULE} en,fr",
              f"PROBE: bash orchestration/lib/create_site.sh {SITE} \"{TITLE}\" {MODULE} en,fr"],
             deps=["step_deploy"]),
        step("step_mcp", "MCP write path up", "verify",
             [f"PROBE: bash orchestration/probes/mcp.sh {PP}"],
             deps=["step_create_site"]),
        # Probe hardened (M4 live find, Julian): asserting content.get on /home
        # alone passes with an empty home skeleton — the gate must count the
        # ACTUAL page tree against the crawl inventory.
        step("step_pages", "Create pages from the crawl inventory (en+fr, published)", "build",
             [f"Run: python3 orchestration/lib/create_pages.py {P} {SITE} --template basic --locale {PRIMARY_LOCALE}",
              f"PROBE: python3 orchestration/lib/create_pages.py {P} {SITE} --check"],
             deps=["step_mcp"]),
        # navigation doctrine (rule 13 + 2026-07-06): the page tree IS the nav.
        # build_nav_tree restructures the flat crawl tree per the project
        # sitemap (sections, moves, L1 order); no-op when no sitemap exists.
        step("step_nav", "Navigation tree per sitemap (sections, moves, L1 order)", "build",
             [f"Run: python3 orchestration/lib/build_nav_tree.py {P} {SITE} --locale {PRIMARY_LOCALE}",
              f"PROBE: python3 orchestration/lib/create_pages.py {P} {SITE} --check"],
             deps=["step_pages"]),
        step("step_content_load", "Load shells + content via MCP (idempotent clean)", "content",
             [f"Run: python3 orchestration/lib/load_content.py {P} {SITE} --clean --locale {PRIMARY_LOCALE}",
              # blocking under ARCH: the page's main area has content children in
              # LIVE (the engine integrity belt does the deeper page-tree diff).
              *([f"PROBE: python3 orchestration/lib/create_pages.py {P} {SITE} --check"] if ARCH else []),
              # blocking under ARCH: every rendered page (both workspaces) free
              # of source junk — cookie consent, SPA islands, framework attrs,
              # source nav, shell blob nodes (2026-07-15 SingPost audit gap).
              *([f"PROBE: python3 orchestration/probes/clean-render.py {SITE} --model archetype"] if ARCH else []),
              adv(f"PROBE: python3 orchestration/probes/partition.py {P}"),
              adv(f"PROBE: python3 orchestration/probes/contribution.py {P}"),
              adv(f"PROBE: python3 orchestration/probes/component_coverage.py {P}")],
             deps=["step_nav"]),
        step("step_publish_parity", "default vs live parity", "publish",
             # parity across the LOADED content locales (CLOC), not the site's
             # full language set — a source-faithful migration only loads what
             # the source has; FR translation of the migrated copy is a separate,
             # post-migration task, so it must not block publication here.
             [f"PROBE: bash orchestration/probes/publish-parity.sh {PP} {SITE} {CLOC}"],
             deps=["step_content_load"]),
        step("step_edit_frame", "Pages editable in jContent", "verify",
             [f"PROBE: bash orchestration/probes/edit-frame.sh {PP} {SITE} en"],
             deps=["step_publish_parity"]),
        # G6 (P2.5-E): the EDITOR-SURFACE gate — every wired prop is a rw field
        # in forms.editForm AND every item node has an edit frame in Page
        # Builder. JCR + pixels never judge the editor experience; this does.
        step("step_editor_surface", "G6 editor surface (forms + item frames)", "verify",
             [f"PROBE[900]: python3 orchestration/probes/editor-surface.py {P} {SITE}"],
             deps=["step_edit_frame"]),
        # G2 (P2.5): sentinel edits must reach the live render, then restore —
        # runs BEFORE the ground-truth gate so the final GT measures the
        # restored state (roundtrip always restores, pass or fail)
        step("step_roundtrip", "G2 contribution round-trip (sentinel edits)", "verify",
             [f"PROBE[900]: python3 orchestration/probes/roundtrip.py {P} {SITE}"],
             deps=["step_editor_surface"]),
        # P5.6: batch PRE-TRIAGE of failing gate/probe exceptions (run metadata,
        # never site content) — DeepSeek collapses the (potentially dozens of)
        # per-page failures into a few failure CLASSES (pattern vs page-specific)
        # so the exceptions-review decision bundle below is small + structured
        # instead of a wall of raw probe output. Reads the integrity-report's
        # mismatches/low-ratio pages (+ an explicit exceptions report if the run
        # dropped one); writes exceptions-triage.json. A deterministic Run: line
        # (engine-executes-Run), always exit 0 — nothing failing => empty triage.
        step("step_triage", "Pre-triage batch exceptions (DeepSeek classes)", "build",
             [f"Run: python3 orchestration/lib/triage_exceptions.py {PP}",
              f"PROBE: test -f {PP}/workflow-output/exceptions-triage.json"],
             deps=["step_roundtrip"]),
        # Scheduled decision point A6-2: end-of-batch exceptions review — ONE
        # checkpoint for the whole batch, never per page.
        review_step("step_exceptions_review", "Batch exceptions review (scheduled decision point)",
                    [f"Review: the pre-triaged failure classes ({PP}/workflow-output/exceptions-triage.json — pattern vs page-specific, per-class counts + suggested actions) alongside the per-page probe results ({PP}/workflow-output/contribution + partition + publish-parity + roundtrip outputs) — pages that did not fit the frozen profile.",
                     f"Decide: POST /runs/{{run_id}}/steps/step_exceptions_review/decide with action=proceed, OR generalize new pattern-keyed rules into {PP}/workflow-output/scope-rules.json + action=apply_and_rerun with rerun_from targeting the failing pages' steps.",
                     "Gate: scheduled decision point — the engine pauses (decision_pending); this step is never sent to an agent."],
                    deps=["step_triage"]),
    ]

    groundtruth = [
        step("step_ground_truth", "GROUND-TRUTH gate: Jahia live vs source mirror (HALT)", "verify",
             [adv(f"PROBE[900]: bash orchestration/probes/groundtruth.sh {P} {SITE} 99"),
              "Gate: present groundtruth/review.html per-page fidelity, return status halt."],
             deps=["step_exceptions_review"]),
    ]

    # every step carries inputs.project = the project PATH (^projects/...) —
    # the engine derives the scope-rules file (<PP>/workflow-output/
    # scope-rules.json) from it at /decide time. inputs.site = the Jahia site key
    # so the engine-level integrity belt (verifier.run_integrity_belt) can diff
    # the live site against the artifacts on content steps WITHOUT parsing probe
    # command lines; the belt also falls back to the project basename when a plan
    # predates this field (the LIVE plan does), so adding it here is purely a
    # clean-path improvement, never a hard dependency.
    for grp in (analyze, module, content, groundtruth):
        for s in grp:
            s["inputs"].setdefault("project", PP)
            s["inputs"].setdefault("site", SITE)

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
    ap.add_argument("--per-cluster", type=int, default=3,
                    help="protocol v2: pages sampled per template cluster (k)")
    ap.add_argument("--threshold", type=int, default=95)
    ap.add_argument("--model", default="opencode/deepseek-v4-flash")
    ap.add_argument("--segmentation", choices=["vision", "heuristic"], default="vision",
                    help="component-model arm: vision (P2 A/B winner, default) or heuristic")
    ap.add_argument("--archetypes", action="store_true",
                    help="SEMANTIC authoring model (redesign §10): archetype manifest + "
                         "semantic CND/views + content→field mapper; fidelity gates demote "
                         "to advisory, cnd-review becomes blocking")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--content-locales", default="en",
                    help="CSV of locales content is LOADED in (load_content --locale + "
                         "publish-parity scope). A source-faithful migration loads only "
                         "the source's languages; the site is still created en,fr so "
                         "editors can translate later. Default: en")
    ap.add_argument("--out")
    a = ap.parse_args()
    params = {
        "project": a.project, "url": a.url, "ns": a.ns,
        "mixns": a.mixns or f"{a.ns}mix", "site": a.site,
        "module": a.module or a.project,
        "title": a.title or f"{a.site} (migrated)",
        "archetypes": a.archetypes,
        "max_pages": a.max_pages, "threshold": a.threshold,
        "per_cluster": a.per_cluster,
        "segmentation": a.segmentation,
        "content_locales": a.content_locales,
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
