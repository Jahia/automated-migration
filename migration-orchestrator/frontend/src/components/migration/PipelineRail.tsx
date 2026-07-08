import { MIGRATION_PHASES, REVIEWABLE_PHASE_KEYS, type Badge, type PhaseDef, type PhaseStatus, type StepLike } from './types'

const ACTIVE_STATUSES = new Set(['running', 'verifying', 'ready', 'halted', 'waiting_human'])

function phaseStatus(phase: PhaseDef, steps: StepLike[], activeStepId?: string): PhaseStatus {
  const matching = steps.filter((s) => phase.match.some((m) => s.id.toLowerCase().includes(m)))
  if (matching.length === 0) return 'absent'  // no step covers it — not "à venir" (P2 honesty)
  if (matching.some((s) => s.id === activeStepId || ACTIVE_STATUSES.has(s.status))) return 'active'
  if (matching.every((s) => s.status === 'done')) return 'done'
  if (matching.some((s) => s.status === 'done')) return 'active'
  return 'pending'
}

const BADGE_CLASS: Record<Badge, string> = {
  deterministic: 'text-[#0077bf] border-[#bcdcef] bg-[#e4f2fb]',
  'DeepSeek V4': 'text-[#0784ba] border-[#a9dcf4] bg-[#e6f5fd]',
  gated: 'text-[#ab6000] border-[#f0d9a8] bg-[#fbf0da]',
}

/**
 * The fixed migration pipeline (migration profile) — replaces the generic
 * Epic/Story/Step tree. Derives each phase's status from the run's steps.
 */
export function PipelineRail({
  steps,
  activeStepId,
  selectedKey,
  onSelectPhase,
}: {
  steps: StepLike[]
  activeStepId?: string
  selectedKey?: string
  onSelectPhase?: (key: string) => void
}) {
  // P2 honesty: judge the plan against the canonical phase spine ONCE, so a
  // partial plan (a phase-subset) announces itself instead of masquerading as a
  // full migration with phases merely "à venir".
  const statuses = MIGRATION_PHASES.map((p) => phaseStatus(p, steps, activeStepId))
  const absentCount = statuses.filter((s) => s === 'absent').length
  const partial = absentCount > 0

  return (
    <nav className="min-h-full border-r border-[#dae0e7] bg-white px-3.5 py-4">
      <div className="px-2 text-[10px] font-bold uppercase tracking-[1.6px] text-[#7d8a9a]">Migration pipeline</div>
      {partial ? (
        <div className="mx-2 mb-2 mt-1 rounded border border-[#f0d9a8] bg-[#fbf0da] px-2 py-1.5 text-[10px] leading-snug text-[#8a5a00]">
          <div className="font-bold">plan partiel — {steps.length} étape{steps.length > 1 ? 's' : ''}</div>
          <div className="text-[#a06f1a]">
            {absentCount} phase{absentCount > 1 ? 's' : ''} du pipeline complet absente{absentCount > 1 ? 's' : ''} de ce run
          </div>
        </div>
      ) : (
        <div className="px-2 pb-3 pt-0.5 text-[10px] text-[#9aa6b4]">Clique une phase pour la revoir</div>
      )}
      {MIGRATION_PHASES.map((phase, i) => {
        const status = statuses[i]
        const selected = phase.key === selectedKey
        // reviewable only once the phase has run AND it has a dedicated panel —
        // so clicking never dead-ends (scaffold) or 404s a not-yet-run artifact.
        // an ABSENT phase never ran and never will → never clickable.
        const reviewable = status !== 'pending' && status !== 'absent' && REVIEWABLE_PHASE_KEYS.has(phase.key)
        const statusLabel = status === 'done' ? 'terminé' : status === 'active' ? 'en cours' : status === 'absent' ? 'absente de ce plan' : 'à venir'
        const last = i === MIGRATION_PHASES.length - 1
        return (
          <button
            key={phase.key}
            type="button"
            disabled={!reviewable}
            onClick={reviewable ? () => onSelectPhase?.(phase.key) : undefined}
            aria-pressed={reviewable ? selected : undefined}
            aria-current={status === 'active' ? 'step' : undefined}
            className={`grid w-full grid-cols-[26px_1fr] gap-2.5 rounded-lg p-2.5 text-left outline-none transition ${
              reviewable ? 'cursor-pointer focus-visible:ring-2 focus-visible:ring-[#0077bf] focus-visible:ring-offset-1' : 'cursor-default'
            } ${status === 'absent' ? 'opacity-60' : ''} ${
              selected
                ? 'bg-[#e4f2fb] shadow-[inset_0_0_0_2px_#0077bf]'
                : status === 'active'
                ? 'bg-[#e4f2fb] shadow-[inset_0_0_0_1px_#bcdcef]'
                : reviewable
                ? 'hover:bg-[#f0f6fb]'
                : ''
            }`}
          >
            <span className="sr-only">{statusLabel}. </span>
            <div className="relative flex justify-center">
              <div
                aria-hidden="true"
                className={`z-10 grid h-[22px] w-[22px] place-items-center rounded-full border-[1.5px] bg-white text-[11px] ${
                  status === 'done'
                    ? 'border-[#12b08a] bg-[#e2f5ef] text-[#12b08a]'
                    : status === 'active'
                    ? 'border-[#0077bf] text-[#0077bf] shadow-[0_0_0_4px_#0077bf22]'
                    : status === 'absent'
                    ? 'border-dashed border-[#d0d6dd] text-[#c2cad4]'
                    : 'border-[#c7d0da] text-[#9aa6b4]'
                }`}
              >
                {status === 'done' ? '✓' : status === 'active' ? '◆' : ''}
              </div>
              {!last && (
                <span
                  className={`absolute left-1/2 top-[22px] -bottom-3 w-0.5 -translate-x-1/2 ${
                    status === 'done' ? 'bg-[#12b08a]' : status === 'absent' ? 'bg-[#e6eaef]' : 'bg-[#c7d0da]'
                  }`}
                />
              )}
            </div>
            <div>
              <div
                className={`text-[13px] font-semibold ${
                  status === 'absent'
                    ? 'italic text-[#9aa6b4]'
                    : status === 'pending'
                    ? 'text-[#7d8a9a]'
                    : 'text-[#001932]'
                }`}
              >
                {phase.title}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {status === 'absent' ? (
                  <span className="rounded border border-[#dbe1e8] bg-[#f4f6f9] px-1.5 font-mono text-[10px] text-[#9aa6b4]">
                    absente
                  </span>
                ) : (
                  phase.badges.map((b) => (
                    <span key={b} className={`rounded border px-1.5 font-mono text-[10px] ${BADGE_CLASS[b]}`}>
                      {b}
                    </span>
                  ))
                )}
              </div>
            </div>
          </button>
        )
      })}
    </nav>
  )
}
