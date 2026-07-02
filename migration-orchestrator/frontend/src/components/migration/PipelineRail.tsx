import { MIGRATION_PHASES, type Badge, type PhaseDef, type PhaseStatus, type StepLike } from './types'

const ACTIVE_STATUSES = new Set(['running', 'verifying', 'ready', 'halted', 'waiting_human'])

function phaseStatus(phase: PhaseDef, steps: StepLike[], activeStepId?: string): PhaseStatus {
  const matching = steps.filter((s) => phase.match.some((m) => s.id.toLowerCase().includes(m)))
  if (matching.length === 0) return 'pending'
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
  onSelectPhase,
}: {
  steps: StepLike[]
  activeStepId?: string
  onSelectPhase?: (key: string) => void
}) {
  return (
    <nav className="min-h-full border-r border-[#dae0e7] bg-white px-3.5 py-4">
      <div className="px-2 pb-3 text-[10px] font-bold uppercase tracking-[1.6px] text-[#7d8a9a]">Migration pipeline</div>
      {MIGRATION_PHASES.map((phase, i) => {
        const status = phaseStatus(phase, steps, activeStepId)
        const last = i === MIGRATION_PHASES.length - 1
        return (
          <button
            key={phase.key}
            onClick={() => onSelectPhase?.(phase.key)}
            className={`grid w-full grid-cols-[26px_1fr] gap-2.5 rounded-lg p-2.5 text-left ${
              status === 'active' ? 'bg-[#e4f2fb] shadow-[inset_0_0_0_1px_#bcdcef]' : ''
            }`}
          >
            <div className="relative flex justify-center">
              <div
                className={`z-10 grid h-[22px] w-[22px] place-items-center rounded-full border-[1.5px] bg-white text-[11px] ${
                  status === 'done'
                    ? 'border-[#12b08a] bg-[#e2f5ef] text-[#12b08a]'
                    : status === 'active'
                    ? 'border-[#0077bf] text-[#0077bf] shadow-[0_0_0_4px_#0077bf22]'
                    : 'border-[#c7d0da] text-[#9aa6b4]'
                }`}
              >
                {status === 'done' ? '✓' : status === 'active' ? '◆' : ''}
              </div>
              {!last && (
                <span
                  className={`absolute left-1/2 top-[22px] -bottom-3 w-0.5 -translate-x-1/2 ${
                    status === 'done' ? 'bg-[#12b08a]' : 'bg-[#c7d0da]'
                  }`}
                />
              )}
            </div>
            <div>
              <div className={`text-[13px] font-semibold ${status === 'pending' ? 'text-[#7d8a9a]' : 'text-[#001932]'}`}>
                {phase.title}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {phase.badges.map((b) => (
                  <span key={b} className={`rounded border px-1.5 font-mono text-[10px] ${BADGE_CLASS[b]}`}>
                    {b}
                  </span>
                ))}
              </div>
            </div>
          </button>
        )
      })}
    </nav>
  )
}
