#!/usr/bin/env python3
"""contract.py — the SINGLE SOURCE OF TRUTH for the inter-step artifact contract.

The llm-orchestration-loop passes almost nothing between steps in the prompt
itself (only a 200-char summary + 10 filenames from prior *approved* stories in
the *same* epic; `depends_on` is ordering-only and is never injected as context;
`expected_outputs` is rendered into the prompt but never verified). The REAL
hand-off between steps is FILES ON DISK at canonical paths, verified by PROBEs.

This module encodes that file contract explicitly so it stops being tribal
knowledge living in the skills. Each step declares:
  * produces — files it must write (post-condition; checked after the step)
  * consumes — files it reads, produced by an upstream step (pre-condition; if
               missing, the upstream producer silently failed to deliver and
               THIS step would run on empty/default data — e.g. load_content.py
               falls back to {} and creates ZERO content without erroring).

Paths use {project} which the probe substitutes. Root-relative paths resolve
from the jahiaMigration repo root.

`contract.sh <project> <step_id>` (the gate) verifies, for one step:
  1. every `produces` file exists and is non-empty / non-stub JSON
  2. every `consumes` file exists at its canonical path and is non-empty
     -> naming, per producer, WHICH upstream step should have produced it.

This is deliberately UNGAMEABLE: it checks the real artifact at the real path
consumers read, not a proxy threshold. Renaming a class or writing the file to
a different directory fails the gate instead of silently passing.
"""
from __future__ import annotations

# Which upstream step is expected to produce each canonical artifact — used only
# to make the failure message actionable ("missing X, produced by step_Y").
PRODUCED_BY = {
    "projects/{project}/workflow-output/component-manifest.json": "step_analyze",
    "projects/{project}/workflow-output/content-data.json": "step_analyze",
    "projects/{project}/workflow-output/asset-inventory.json": "step_analyze",
    "projects/{project}/workflow-output/analysis.md": "step_analyze",
    "orchestration/images/{project}.json": "step_extract",
    "orchestration/content/{project}.content-data.json": "step_extract",
    "projects/{project}/component-baseline.txt": "step_content_types",
    "orchestration/images/{project}.imported.json": "step_media",
    "projects/{project}/workflow-output/review/REVIEW.md": "step_review",
    "projects/{project}/workflow-output/a11y/A11Y.md": "step_accessibility",
    "projects/{project}/workflow-output/visual-diff/SUMMARY.md": "step_visual_diff",
    "projects/{project}/workflow-output/vanity/redirects.map": "step_vanity",
}

# step_id -> {"produces": [...canonical paths...], "consumes": [...]}
# Only steps that read or write a cross-step artifact appear here. Steps that
# only mutate the module source tree (navigation/jcr_query/grid_row) or Jahia
# itself (deploy) are covered by their own dedicated probes and are listed with
# just their consumes so the pre-condition is still enforced.
CONTRACT = {
    "step_connect": {"produces": [], "consumes": []},
    "step_analyze": {
        "produces": [
            "projects/{project}/workflow-output/component-manifest.json",
            "projects/{project}/workflow-output/content-data.json",
            "projects/{project}/workflow-output/asset-inventory.json",
            "projects/{project}/workflow-output/analysis.md",
        ],
        "consumes": [],
    },
    "step_extract": {
        "produces": [
            "orchestration/images/{project}.json",
            "orchestration/content/{project}.content-data.json",
        ],
        # analyze's content-data.json seeds the deterministic extractor
        "consumes": ["projects/{project}/workflow-output/content-data.json"],
    },
    "step_scaffold": {
        "produces": ["projects/{project}/package.json"],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_assets": {
        "produces": ["projects/{project}/static/css/theme-tokens.css"],
        "consumes": ["projects/{project}/workflow-output/asset-inventory.json"],
    },
    "step_content_types": {
        "produces": [
            "projects/{project}/settings/definitions.cnd",
            "projects/{project}/component-baseline.txt",
        ],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_navigation": {
        "produces": [],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_jcr_query": {
        "produces": [],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_grid_row": {
        "produces": [],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_components": {
        "produces": [],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_templates": {
        "produces": [],
        "consumes": ["projects/{project}/workflow-output/component-manifest.json"],
    },
    "step_deploy": {"produces": [], "consumes": []},
    "step_media": {
        "produces": ["orchestration/images/{project}.imported.json"],
        "consumes": ["orchestration/images/{project}.json"],
    },
    "step_content": {
        "produces": [],
        "consumes": [
            "projects/{project}/workflow-output/component-manifest.json",
            "orchestration/content/{project}.content-data.json",
            "orchestration/images/{project}.imported.json",
            "projects/{project}/component-baseline.txt",
        ],
    },
    "step_review": {
        "produces": ["projects/{project}/workflow-output/review/REVIEW.md"],
        "consumes": ["projects/{project}/component-baseline.txt"],
    },
    "step_accessibility": {
        "produces": ["projects/{project}/workflow-output/a11y/A11Y.md"],
        "consumes": [],
    },
    "step_visual_diff": {
        "produces": ["projects/{project}/workflow-output/visual-diff/SUMMARY.md"],
        "consumes": [],
    },
    "step_vanity": {
        "produces": ["projects/{project}/workflow-output/vanity/redirects.map"],
        "consumes": [],
    },
}

# Artifacts that are produced but read by no downstream step or probe. Not a
# failure — flagged so the contract stays honest about dead weight.
ORPHANS = {
    "projects/{project}/workflow-output/asset-inventory.json":
        "read only by analyze.sh (its own producer probe); superseded downstream "
        "by orchestration/images/{project}.json from extract_media. Kept as the "
        "human analysis catalogue; not a machine hand-off.",
}


def resolve(path: str, project: str) -> str:
    return path.replace("{project}", project)


def for_step(step_id: str, project: str) -> dict:
    """Return {'produces': [...], 'consumes': [...]} with {project} resolved."""
    spec = CONTRACT.get(step_id, {"produces": [], "consumes": []})
    return {
        "produces": [resolve(p, project) for p in spec.get("produces", [])],
        "consumes": [resolve(p, project) for p in spec.get("consumes", [])],
    }


def producer_of(path_template: str) -> str:
    return PRODUCED_BY.get(path_template, "an upstream step")
