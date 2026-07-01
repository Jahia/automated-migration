# Inter-step artifact contract

**Question this answers:** *is what is passed between epics/stories relevant and sufficient for the next step to run?*

**Short answer:** the JSON the loop passes between steps is deliberately thin — it is **not** sufficient on its own. The real hand-off is **files on disk at canonical paths**, verified by probes. This document is the single human-readable map of that file contract; the machine source of truth is [`lib/contract.py`](lib/contract.py), enforced by [`probes/contract.sh`](probes/contract.sh).

---

## What the orchestration loop actually passes between steps

Traced from `llm-orchestration-loop/src/prompt_builder.py` (`build_step_prompt`). Each step's prompt receives:

| Carried across a step boundary | Not carried |
|---|---|
| The step's own `inputs` (minus `_`-prefixed keys) | **`depends_on` results** — `depends_on` is ordering-only; the depended step's `agent_result` is never injected |
| Story + epic `goal` / `acceptance_criteria` | **Cross-epic results** — `_format_previous_stories` only looks at the *current* epic |
| From prior *approved* stories in the *same* epic: each step's `agent_result.summary` **truncated to 200 chars** + first **10** `modified_files` | Full file lists, `risks`, `commands_requested`, structured output |
| Loop/rectification reason + diagnosis (on re-runs) | **`expected_outputs`** — rendered into the prompt but the verifier never checks it |

The verifier (`src/verifier.py`) enforces a step **only** by running its `PROBE:` commands. So the durable contract has to live in files + probes, not in the passed JSON.

### Why this bites (the silent-degradation trap)

`orchestration/lib/load_content.py` reads its inputs with defaults:

```python
self.manifest = load_json(f"projects/{project}/workflow-output/component-manifest.json", {})
self.content  = load_json(f"orchestration/content/{project}.content-load.json", {"pages": {}})
self.imported = load_json(f"orchestration/images/{project}.imported.json", {})
```

If any path is wrong or the upstream step didn't deliver, the consumer runs on `{}` and **creates zero content without erroring** — the exact "0 of 40 images / far from reality" failure. Nothing in the passed JSON prevents this; only a path-pinned file check does.

---

## Producer → consumer map

Canonical paths use `<p>` for the project slug. Root-relative paths resolve from the jahiaMigration repo root.

| Artifact (canonical path) | Produced by | Consumed by | Enforced |
|---|---|---|---|
| `projects/<p>/workflow-output/component-manifest.json` | `step_analyze` | `step_scaffold`, `step_content_types`, `step_navigation`, `step_jcr_query`, `step_grid_row`, `step_components` (`components-all.sh`), `step_templates` (`template-govern.sh`), `step_content` (`load_content.py`) | `analyze.sh` (path now pinned), `contract.sh` |
| `projects/<p>/workflow-output/content-data.json` | `step_analyze` | `step_visual_diff` / `step_vanity` (page-list fallback) + legacy skill-09 path — a per-page analysis list `[{page,url,sections,…}]`, **not** the load payload | `analyze.sh` |
| `projects/<p>/workflow-output/asset-inventory.json` | `step_analyze` | **orphan** — read only by `analyze.sh`; superseded by `extract_media` | `analyze.sh` |
| `projects/<p>/workflow-output/analysis.md` | `step_analyze` | human review (Gate 1) | `analyze.sh` |
| `orchestration/images/<p>.json` | `step_extract` (`extract_media.py`) | `step_media` (`images/import.py`) | `extract.sh`, `media.sh`, `contract.sh` |
| `orchestration/content/<p>.content-load.json` | `step_extract` (`extract_content.py`, reads the captured `.reference/` DOM) | `step_content` (`load_content.py`) — the JCR load payload `{adapter, pages:{…}}` | `extract.sh`, `contract.sh` |
| `orchestration/images/<p>.imported.json` | `step_media` (`import.py`) | `step_content` (`load_content.py` image-wiring) | `media.sh`, `contract.sh` |
| `projects/<p>/component-baseline.txt` | `step_content_types` (`inventory.sh --write`) | `step_content` + `step_review` (`no-new-types.sh`) | `contract.sh` |
| `projects/<p>/workflow-output/review/REVIEW.md` | `step_review` | human | `artifact.sh`, `contract.sh` |
| `projects/<p>/workflow-output/a11y/A11Y.md` | `step_accessibility` | human | `artifact.sh`, `contract.sh` |
| `projects/<p>/workflow-output/visual-diff/SUMMARY.md` | `step_visual_diff` | human | `artifact.sh`, `contract.sh` |
| `projects/<p>/workflow-output/vanity/redirects.map` | `step_vanity` | vanity import | `artifact.sh`, `contract.sh` |

Content written to **Jahia itself** (`step_content` → JCR nodes) is not a file artifact — it is verified by `content.sh` / `render-all.sh` / `publish-parity.sh`, not by this contract.

---

## Gaps found in the audit (and their status)

1. **Producer path ≠ consumer path for the manifest.** `analyze.sh` accepted `component-manifest.json` *anywhere* under the project via `find`, while every consumer pins `workflow-output/component-manifest.json`. An off-path manifest passed the gate while `components-all.sh` silently skipped its drop-guard and `load_content.py` read `{}`. **Fixed:** `analyze.sh` now pins the canonical `workflow-output/` path and reports an off-path file as a violation.

2. **`expected_outputs` unused.** It was `{}` on all 18 steps and the verifier never checks it anyway. **Fixed:** `wire_contract.py` populates it from the contract table (so the agent is told what to write) and `contract.sh` enforces it.

3. **Consumer input paths not passed.** Steps received orientation params only (`project`, `skill`), never the upstream artifact path. **Fixed:** `inputs.consumes` now carries the canonical read paths into each consumer step.

4. **`content-data.json` name collision.** `step_analyze` wrote `workflow-output/content-data.json` (a per-page analysis list) and `step_extract` wrote `orchestration/content/<p>.content-data.json` (the JCR load payload) — different schemas, same base name. **Fixed:** the ETL load payload was renamed to `orchestration/content/<p>.content-load.json` across `extract_content.py`, `load_content.py`, `extract.sh`, `contract.py`, the `source-extract` skill, and all plans. The analyze artifact keeps its name (its ~50 refs across legacy commands/skills are untouched). No more collision; the two names now say what they are.

5. **`step_extract` false consume (found during the rename).** `contract.py` claimed `step_extract` consumes the analyze `content-data.json` as a seed. It does not — `extract_content.py` reads the captured `.reference/` DOM directly. **Fixed:** removed that consume from `contract.py`; `wire_contract.py` now *reconciles* (deletes a `consumes` that was emptied) instead of only adding, and stripped the stale `inputs.consumes` from every plan.

6. **`asset-inventory.json` is an orphan** — produced but consumed by no downstream step. **Documented** in `contract.py::ORPHANS`; kept as the human analysis catalogue (superseded for machine use by `extract_media`).

---

## How to use it

- **Enforce for one step:** `bash orchestration/probes/contract.sh projects/<p> <step_id>` — checks the step's `produces` exist non-stub and its `consumes` exist at the canonical path (naming the upstream producer of any missing input).
- **Wire a plan:** `python3 orchestration/lib/wire_contract.py orchestration/plans/<plan>.json` — injects `expected_outputs`, `inputs.consumes`, and the `contract.sh` PROBE into every step. Idempotent; `--check` verifies without writing.
- **The contract PROBE runs automatically** as part of each wired step's acceptance criteria, so the loop fails a step the moment the data passed to/from it is insufficient — instead of degrading silently three steps later.

Editing the contract: change [`lib/contract.py`](lib/contract.py) only, then re-run `wire_contract.py` on the template and active plans.
