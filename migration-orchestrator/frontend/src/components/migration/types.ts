// component-manifest.json (orchestration/lib/assemble_manifest.py)

export interface ComponentField {
  name: string
  type: string
  i18n?: boolean
  mandatory?: boolean
}

export interface ComponentType {
  name: string
  nodeType: string
  coversRoles?: string[]
  isContainer?: boolean
  needsMainResource?: boolean
  childType?: { name: string; nodeType: string } | null
  layoutProperty?: { name: string; options: string[] } | null
  views?: { name: string }[]
  fields?: ComponentField[]
  frequency?: number
}

export interface CrossCuttingType {
  name: string
  nodeType: string
  area: string
}

export interface ComponentManifest {
  crossCutting: CrossCuttingType[]
  components: ComponentType[]
  templates?: { name?: string; kind: string; pages: string[] }[]
  namingQuality?: 'good' | 'mixed' | 'poor'
  namingViolations?: { nodeType: string; reason?: string }[]
  genericShare?: number
}

// ── the fixed migration pipeline (migration profile) ──

// 'absent' (P2 honesty): a canonical phase that NO step in this run's plan
// covers — rendered as a grayed placeholder, distinct from 'pending' ("à venir",
// a phase that WILL run). This is how a partial plan (e.g. a 5-step zone plan)
// stops reading as "a full migration with phases still to come".
export type PhaseStatus = 'done' | 'active' | 'pending' | 'absent'
export type Badge = 'deterministic' | 'DeepSeek V4' | 'gated'

export interface PhaseDef {
  key: string
  title: string
  badges: Badge[]
  /** step-id substrings that belong to this phase */
  match: string[]
}

export const MIGRATION_PHASES: PhaseDef[] = [
  { key: 'capture', title: 'Capture', badges: ['deterministic'], match: ['crawl', 'capture'] },
  { key: 'mirror', title: 'Miroir local', badges: ['gated'], match: ['localize', 'mirror'] },
  { key: 'analyze', title: 'Analyze', badges: ['deterministic'], match: ['extract', 'semantic', 'analyze', 'block'] },
  { key: 'model', title: 'Model components', badges: ['DeepSeek V4', 'gated'], match: ['group', 'component_model', 'assemble', 'discover', 'cluster', 'cnd', 'content_type'] },
  { key: 'fidelity', title: 'Fidelity gate', badges: ['gated'], match: ['reconstruct', 'fidelity'] },
  { key: 'scaffold', title: 'Scaffold module', badges: ['deterministic'], match: ['scaffold'] },
  { key: 'implement', title: 'Implement + templates', badges: ['DeepSeek V4', 'gated'], match: ['implement', 'navigation', 'jcr', 'grid', 'component', 'template'] },
  { key: 'content', title: 'Content + publish', badges: ['gated'], match: ['content', 'create', 'publish'] },
  { key: 'golive', title: 'Go-live · visual diff', badges: ['deterministic'], match: ['visual', 'vanity', 'golive', 'review', 'accessibility'] },
]

export interface StepLike {
  id: string
  status: string
  gate_type?: string | null
}

/** Does any step in the plan cover this canonical phase? */
export function phaseHasSteps(phase: PhaseDef, steps: StepLike[]): boolean {
  return steps.some((s) => phase.match.some((m) => s.id.toLowerCase().includes(m)))
}

/**
 * PARTIAL-PLAN detection (P2 honesty). CHOICE: the canonical stage list is
 * MIGRATION_PHASES above — it mirrors orchestration/lib/gen_plan.py's full-loop
 * phases (kept in sync with migration_control.PHASES). A run's plan is partial
 * when it OMITS ≥1 canonical phase (no step matches it). We compare at PHASE
 * granularity, not against gen_plan's exact 30 step ids, because the step set
 * legitimately varies (vision vs heuristic arm, zone-only plans) while the phase
 * spine is stable — so a phase-level check is the reliable canonical list the
 * task calls for, without hardcoding a brittle step-id roster in the frontend.
 */
export function isPartialPlan(steps: StepLike[]): boolean {
  return steps.length > 0 && MIGRATION_PHASES.some((p) => !phaseHasSteps(p, steps))
}

/** Phase keys that have a dedicated review panel (MigrationStage.panelForPhase).
 * 'scaffold' has none → not reviewable. Used to gate rail clickability. */
export const REVIEWABLE_PHASE_KEYS = new Set<string>([
  'capture', 'mirror', 'analyze', 'model', 'fidelity', 'implement', 'content', 'golive',
])
