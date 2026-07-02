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
  templates: { name?: string; kind: string; pages: string[] }[]
}

// ── the fixed migration pipeline (migration profile) ──

export type PhaseStatus = 'done' | 'active' | 'pending'
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

/** Phase keys that have a dedicated review panel (MigrationStage.panelForPhase).
 * 'scaffold' has none → not reviewable. Used to gate rail clickability. */
export const REVIEWABLE_PHASE_KEYS = new Set<string>([
  'capture', 'analyze', 'model', 'fidelity', 'implement', 'content', 'golive',
])
