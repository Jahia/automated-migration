# Frontend refactor plan — generic orchestrator → dedicated Migration Cockpit

Goal: turn the generic Run → Epic → Story → Step UI into a cockpit organised around
the **site** and its **fidelity**, without throwing away the proven engine. The
generic engine stays; we add a thin **migration profile** on top (a fixed plan
template + typed gates + domain-artifact views).

---

## 0. Principle — a profile, not a rewrite

The engine still: selects steps, runs their `Run:`/`PROBE:` commands, gates on exit
codes, HALTs for humans, streams SSE. We add three things:

1. a **fixed migration plan template** the engine owns (operator supplies a *config*, not a plan);
2. **typed gates** (`gate_type`) so the frontend knows which domain panel to render;
3. **artifact serving** so the frontend can show the real outputs (screenshots, manifest, CND).

Everything reversible: remove the profile → the generic engine is back.

---

## 1. Engine-side contracts (backend TODO)

### 1a. Start a migration from a config (not a plan JSON) — ✅ SHIPPED
```
POST /migrations
{ "site_url": "https://www.acquia.com", "project": "acquia-drupal", "ns": "acq",
  "mixns": "acqmix", "max_pages": 18, "depth": 2, "sample_pages": ["home","about-us","blog"] }
→ { "run_id": "...", "status": "created" }   # engine expands the config into the fixed plan
```
`_build_migration_plan()` (`src/routes/runs.py`) materializes the analyze plan step-for-step
from `orchestration/plans/acquia-analyze.plan.json`: crawl → semantic_extract → group_llm(DeepSeek)
→ assemble+CND → **reconstruct fidelity gate** (last step returns `status: "halt"`), each carrying
its `PROBE:`. `mixns` defaults to `<ns>mix`; `repo_dir` defaults to the harness root. Frontend:
`components/migration/NewMigration.tsx` + `createMigration()` in `api.ts`.

### 1b. Typed gates
Add to `StepState` (models.py) a `gate_type` when a step HALTs:
```
gate_type: 'scope' | 'model' | 'fidelity' | 'content' | 'golive' | null
```
The frontend maps `gate_type` → the right panel (see §3). Approve = existing `POST /runs/{id}/resume`
(the engine already forces the halted step to done on resume). Reject = `pause` + a flag.

### 1c. Artifact serving (needed by the Fidelity gate today)
```
GET /runs/{id}/artifacts/{path}          # static, from projects/<project>/workflow-output/<path>
```
e.g. `reconstruct/reconstruct.json`, `reconstruct/home.source.png`, `component-manifest.json`,
`semantic-candidates.json`, `coverage/coverage.json`, `definitions.cnd`, `views.json`.
FastAPI: mount a `StaticFiles`/`FileResponse` route resolved from the run's `repo_dir` + project.

### 1d. Fidelity re-run (typed action)
```
POST /runs/{id}/fidelity/rerun   { "pages": ["home","careers"] }   # runs reconstruct_probe on a chosen sample
```

---

## 2. Migration config (SSE + state additions)

Add to `RunState`: `profile: 'migration'`, `source_url`, `namespace`, `site_key`, and a derived
`phase` (the current macro phase). New SSE events reuse the existing ones — no new stream needed;
the frontend derives phase/gate from step status + `gate_type`.

---

## 3. Component tree (old → new)

```
App
├── TopBar (navy + Jahia logo)  ✅ DONE            # App.tsx nav: logo, Runs / Nouvelle migration / API
├── MigrationList              ← RunList          # cards: source → :ns, phase, fidelity %  (+ "Nouvelle migration" CTA ✅)
├── NewMigration               ✅ DONE            # form: url + project + ns + mixns + sample  (1a)
└── MigrationDetail            ← RunDetail
    ├── KpiBar                  ✅ DONE            # pages / types / templates / x-cut / fidelity% / spend
    ├── PipelineRail            ✅ DONE ← EpicTimeline/EpicCard/StoryCard/StepCard
    │                                              # 8 fixed phases + det/LLM/gate badges
    ├── MigrationStage (dispatch by gate_type) ✅ DONE
    │   ├── ScopeGate     ✅ DONE ← QuestionPanel  # pages + candidates + template clusters + x-cut
    │   ├── ModelGate     ✅ DONE ← SchemaViewer   # ComponentModelView (types/views/templates/x-cut)
    │   ├── FidelityGate  ✅ DONE ← RectificationPanel   # reconstruct gallery + approve
    │   ├── ContentGate   ✅ DONE ← RectificationPanel   # content-data overview + section histogram
    │   └── GoLiveGate    ✅ DONE ← RectificationPanel   # visual-diff summary + redirect map
    └── SidePanel
        ├── ProofStrip            ← (from verification) # PROBE results, green checks
        └── CostPanel             ← TokenCounter   # DeepSeek tokens / cost (KpiBar surfaces spend today)
```
Shared, kept as-is: `LiveLog`, `AgentOutput` (renamed conceptually to StepLog), SSE plumbing,
`RunControls`.

New leaf components to build after this PR: `BeforeAfterSlider` ✅, `ComponentModelView`,
`SitemapTree`, `CndPreview`, `CoveragePanel`, `DiffGallery`.

---

## 4. Frontend type contracts (`types.ts` additions)

```ts
export type GateType = 'scope' | 'model' | 'fidelity' | 'content' | 'golive'
export type MigrationPhase =
  | 'capture' | 'analyze' | 'model' | 'fidelity'
  | 'scaffold' | 'implement' | 'content' | 'golive'

export interface MigrationConfig {
  sourceUrl: string; namespace: string; siteKey: string
  language: string; maxPages: number; fidelitySample: string[]
}

// component-manifest.json (assemble_manifest.py)
export interface ComponentType {
  name: string; nodeType: string; coversRoles: string[]
  isContainer: boolean; needsMainResource: boolean
  childType?: { name: string; nodeType: string } | null
  layoutProperty?: { name: string; options: string[] } | null
  views: { name: string }[]; fields: { name: string; type: string; i18n?: boolean; mandatory?: boolean }[]
  frequency: number
}
export interface ComponentManifest {
  crossCutting: { name: string; nodeType: string; area: string }[]
  components: ComponentType[]
  templates: { name?: string; kind: string; pages: string[] }[]
}
```
Fidelity types already shipped in `components/fidelity/types.ts` (`ReconstructReport`).

Extend `StepState` (mirror backend 1b): `gate_type?: GateType | null`.

---

## 5. How the FidelityGate plugs in (this PR)

In `RunDetail`/`Stage`, when the active step is halted with `gate_type === 'fidelity'`:
```tsx
import { FidelityGate } from './components/fidelity/FidelityGate'
...
{halted && step.gate_type === 'fidelity' && (
  <FidelityGate runId={runId} stepId={step.id} onApproved={refresh} />
)}
```
Until `gate_type` exists on the backend, gate on the step id instead:
`step.id === 'step_reconstruct_gate'`.

The engine must serve artifacts (1c) so the `<img>`s resolve. The gate approve button calls the
existing `/runs/{id}/resume`.

---

## 6. Build order (incremental, low-risk)

1. **FidelityGate** ✅ + backend artifact serving (1c) ✅ + resume wiring ✅. Highest value; the data exists.
2. **PipelineRail** ✅ — phase list re-badged (det / LLM / gate); status derived from step state.
3. **ComponentModelView** (ModelGate) ✅ — renders `component-manifest.json`.
4. **NewMigration** form + `POST /migrations` (1a) ✅ — replaces plan-JSON authoring.
5. **TopBar** (navy + logo) ✅ + **KpiBar** ✅ — cockpit identity + at-a-glance KPIs.
6. **ScopeGate / ContentGate / GoLiveGate** ✅ — typed panels over their artifacts, dispatched by `MigrationStage`.
7. **Raw toggle** ✅ — generic Epic/Story/Step cards (`RunReport` + `EpicTimeline`) hidden behind a "Détails bruts" toggle in migration runs; `ActivityBar` + `LiveLog` stay (live shell).

**Next:** `mainResource` / detail-page auto-detection (the pixel-perfect blocker) — see ANALYZE-PIPELINE.md §8.

---

## 7. Visual identity (already pinned)

Jahia navy `#001932` app bar (grid + aurora), azure `#0077bf` / cyan `#00a1e3` primary, light
`#eef2f6` body, Plus Jakarta Sans, uppercase + `›` buttons, notched top-right cards. Magenta
`#d6217d` reserved for the pixel-diff motif only. See the mockup published this session.
Add the palette to `tailwind.config.js theme.extend.colors` (jnavy, jblue, jcyan, …) and inline
Plus Jakarta Sans via `@font-face` in `index.css` (27 KB woff2, self-hosted).
