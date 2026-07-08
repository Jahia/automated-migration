import type { StepProvenance, StepState } from '../../types'

// ── P2 step honesty ────────────────────────────────────────────────────
// Each step renders as EXACTLY ONE honest state, so a partial plan's fast
// probe-only step never reads as "a full migration ran":
//   3) réutilisé — the artifact this step gated on was produced by a DIFFERENT
//                  run (done fast, no real work this run). Wins over 1/2.
//   2) validé sans exécution — done but never executed: attempt 0 or no start
//                  timestamp (a review checkpoint decided via 'proceed', or a
//                  step skipped by an arm-swap strategy).
//   1) exécuté   — real work: attempt>0 and a start timestamp → show duration +
//                  start→end timestamps (a ~5ms duration is itself the tell).

/** Human duration: a validate-only probe reads as "5 ms". */
export function fmtDuration(ms?: number | null): string {
  if (ms == null) return ''
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s % 60).toString().padStart(2, '0')}s`
}

export function fmtClock(ms?: number | null): string {
  return ms ? new Date(ms).toLocaleTimeString() : ''
}

export type Honesty =
  | { kind: 'reused'; runId: string | null; at: string | null }
  | { kind: 'validated' }
  | { kind: 'executed' }
  | { kind: 'none' }

export function honestyOf(step: StepState, prov?: StepProvenance): Honesty {
  if (prov?.reused) return { kind: 'reused', runId: prov.produced_by_run ?? null, at: prov.generated_at ?? null }
  const executed = step.attempt > 0 && !!step.started_at
  if (step.status === 'done') return executed ? { kind: 'executed' } : { kind: 'validated' }
  // failed / halted / rejected that genuinely ran still show their timing
  if (['failed', 'halted', 'rejected'].includes(step.status) && executed) return { kind: 'executed' }
  return { kind: 'none' }
}

/** The single honest badge line for a step, reused by the flat execution list
 * (prominent) and the deep Epic/Story/Step tree (StepCard). */
export function StepHonestyBadge({ step, provenance }: { step: StepState; provenance?: StepProvenance }) {
  const honesty = honestyOf(step, provenance)
  if (honesty.kind === 'none') return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px]">
      {honesty.kind === 'reused' && (
        <>
          <span
            className="rounded border border-amber-600/70 bg-amber-500/15 px-1.5 py-0.5 text-amber-700 dark:text-amber-300"
            title={`Artefact réutilisé — produit par le run ${honesty.runId ?? '(inconnu)'}${honesty.at ? ` le ${honesty.at}` : ''}. Cette étape n'a pas refait le travail : son probe a validé un fichier préexistant.`}
          >
            ♻ réutilisé{honesty.runId ? ` · run ${honesty.runId}` : ''}
          </span>
          {honesty.at && <span className="text-gray-500">généré {honesty.at}</span>}
        </>
      )}
      {honesty.kind === 'validated' && (
        <span
          className="rounded border border-gray-500 bg-transparent px-1.5 py-0.5 text-gray-400"
          title="Gate décidée / artefact préexistant validé par probe — aucune exécution ce run (attempt 0 ou pas d'horodatage de début)."
        >
          ☐ validé sans exécution
        </span>
      )}
      {honesty.kind === 'executed' && (
        <>
          <span className="rounded border border-green-700/60 bg-green-500/15 px-1.5 py-0.5 text-green-700 dark:text-green-300">
            exécuté{step.duration_ms != null ? ` · ${fmtDuration(step.duration_ms)}` : ''}
          </span>
          {step.started_at && (
            <span
              className="text-gray-500"
              title={`Début ${new Date(step.started_at).toLocaleString()}${step.completed_at ? ` · fin ${new Date(step.completed_at).toLocaleString()}` : ''}`}
            >
              {fmtClock(step.started_at)}{step.completed_at ? ` → ${fmtClock(step.completed_at)}` : ''}
            </span>
          )}
        </>
      )}
    </div>
  )
}
