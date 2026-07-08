import { useParams } from 'react-router-dom'
import { useRun } from '../hooks/useRun'
import RunControls from './RunControls'
import EpicTimeline from './EpicTimeline'
import ActivityBar from './ActivityBar'
import LiveLog from './LiveLog'
import RunReport from './RunReport'
import { PipelineRail } from './migration/PipelineRail'
import { KpiBar } from './migration/KpiBar'
import { MigrationStage } from './migration/MigrationStage'
import { ContentLoadProgress } from './migration/ContentLoadProgress'
import { isPartialPlan } from './migration/types'
import { StepHonestyBadge } from './migration/StepHonesty'
import { ArtifactFreshnessPanel } from './migration/ArtifactProvenance'
import { fetchRunProvenance } from '../api'
import type { StepProvenance } from '../types'
import { useEffect, useState, useRef } from 'react'

// Step-status pill colors for the flat execution list (light-themed migration area).
const STEP_PILL: Record<string, string> = {
  done: 'bg-[#e2f5ef] text-[#0a7d5f]',
  running: 'bg-[#e4f2fb] text-[#0077bf]',
  verifying: 'bg-[#e4f2fb] text-[#0077bf]',
  halted: 'bg-[#fbf0da] text-[#8a5a00]',
  waiting_human: 'bg-[#fbf0da] text-[#8a5a00]',
  decision_pending: 'bg-[#fbf0da] text-[#8a5a00]',
  failed: 'bg-[#fbe4e4] text-[#b0271f]',
  rejected: 'bg-[#fbe4e4] text-[#b0271f]',
  blocked: 'bg-[#fbe4e4] text-[#b0271f]',
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const { run, loading, error, reload } = useRun(runId || null)
  const [lastPoll, setLastPoll] = useState(new Date())
  const [pollCount, setPollCount] = useState(0)
  const [healthOk, setHealthOk] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const [stepsOpen, setStepsOpen] = useState(false)
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)
  const [provenance, setProvenance] = useState<Record<string, StepProvenance>>({})
  const pollTimer = useRef<ReturnType<typeof setInterval>>()

  // Per-step artifact provenance (the "réutilisé" detector). One batched call,
  // refetched as steps reach a terminal status (their artifacts settle) — the
  // map is otherwise stable, so we key on the terminal-step count, not each poll.
  const terminalCount = (run?.epics ?? [])
    .flatMap((e) => e.stories).flatMap((s) => s.steps)
    .filter((st) => ['done', 'failed', 'halted', 'rejected'].includes(st.status)).length
  useEffect(() => {
    if (!runId || !run) return
    let cancelled = false
    fetchRunProvenance(runId)
      .then((p) => { if (!cancelled) setProvenance(p.steps || {}) })
      .catch(() => { /* older engine w/o the endpoint → no honesty chips, no error */ })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, terminalCount])

  // Partial-plan honesty: a plan that omits canonical phases is the exact case
  // that misled twice ("step 4 done" ⇒ "a full migration ran"). Open the flat
  // per-step execution list by default for it (once per run) so it is not hidden.
  useEffect(() => {
    if (!run) return
    const steps = run.epics.flatMap((e) => e.stories).flatMap((s) => s.steps)
    const migration = steps.some((st) => /crawl|semantic|group|reconstruct|component_model|assemble/i.test(st.id))
    if (migration && isPartialPlan(steps)) setStepsOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id])

  useEffect(() => {
    const check = async () => {
      setPollCount(c => c + 1)
      setLastPoll(new Date())
      try {
        const resp = await fetch('/health')
        const data = await resp.json()
        setHealthOk(data.status === 'ok')
      } catch {
        setHealthOk(false)
      }
    }
    check()
    pollTimer.current = setInterval(check, 3000)
    return () => clearInterval(pollTimer.current)
  }, [])

  // When a NEW gate halts the run, drop any stale phase-review selection so the
  // actionable gate is never hidden behind a read-only view of a past phase.
  const gateStepId = run?.epics
    .flatMap((e) => e.stories)
    .flatMap((s) => s.steps)
    .find((st) => (st.status === 'halted' || st.status === 'waiting_human') && st.gate_type)?.id
  useEffect(() => {
    if (gateStepId) setSelectedPhase(null)
  }, [gateStepId])

  if (loading) return <div className="text-gray-400">Chargement...</div>
  if (error) return (
    <div>
      <div className="text-red-400 mb-2">Erreur: {error}</div>
      <button onClick={reload} className="px-3 py-1 bg-blue-700 rounded text-sm">Réessayer</button>
    </div>
  )
  if (!run) return <div className="text-gray-500">Run non trouvé</div>

  const statusColors: Record<string, string> = {
    created: 'text-gray-400',
    running: 'text-blue-400',
    paused: 'text-yellow-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
    aborted: 'text-gray-400',
  }

  const allSteps = run.epics.flatMap(e => e.stories).flatMap(s => s.steps)
  const runningStep = allSteps.find(st => st.status === 'running')
  const gateStep = allSteps.find(st => (st.status === 'halted' || st.status === 'waiting_human') && st.gate_type)
  const activeStepId = (runningStep ?? gateStep)?.id
  const isMigration = allSteps.some(st => /crawl|semantic|group|reconstruct|component_model|assemble/i.test(st.id))

  return (
    <div>
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{run.goal}</h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`font-mono text-sm ${statusColors[run.status] || 'text-gray-400'}`}>
              {run.status}
            </span>
            <span className="text-gray-500 text-sm">{run.run_id}</span>
            {run.project && (
              <span className="px-2 py-0.5 rounded-full bg-gray-800 border border-gray-700 text-xs text-gray-300">
                {run.project}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-xs text-gray-500 text-right leading-relaxed">
            <div className="flex items-center gap-2 justify-end">
              <span className={`w-2 h-2 rounded-full ${healthOk ? 'bg-green-500' : 'bg-red-500'}`} />
              <span>{healthOk ? 'OK' : 'ERR'}</span>
              <span className="text-gray-600">|</span>
              <span className={`font-medium ${statusColors[run.status] || ''}`}>{run.status}</span>
            </div>
            <div className="text-gray-600">
              poll #{pollCount} · {lastPoll.toLocaleTimeString()}
            </div>
            {runningStep && (
              <div className="text-blue-400">▶ {runningStep.task_type}@{runningStep.agent}</div>
            )}
          </div>
          <RunControls run={run} onReload={reload} />
        </div>
      </div>

      {run.status === 'running' && (
        <div className="mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm text-blue-400">Exécution en cours...</span>
        </div>
      )}

      {error && (
        <div className="mb-4 bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {isMigration && <KpiBar run={run} />}

      {isMigration && <ContentLoadProgress run={run} />}

      {isMigration && (
        <div className="mb-6 grid grid-cols-1 items-start gap-4 lg:grid-cols-[260px_1fr]">
          <div className="overflow-hidden rounded-lg">
            <PipelineRail
              steps={allSteps}
              activeStepId={activeStepId}
              selectedKey={selectedPhase ?? undefined}
              onSelectPhase={(k) => setSelectedPhase((p) => (p === k ? null : k))}
            />
          </div>
          <div className="min-w-0 rounded-lg bg-[#eef2f6] p-4">
            <MigrationStage
              run={run}
              gateStep={gateStep}
              selectedPhase={selectedPhase}
              onClearPhase={() => setSelectedPhase(null)}
              onApproved={reload}
            />
          </div>
        </div>
      )}

      {/* Artifact staleness (P3b): every known pipeline artifact's provenance +
          whether a DAG-upstream stage regenerated after it — visible even for
          stages with no dedicated gate panel (groundtruth, compose, cnd, ...). */}
      {isMigration && <ArtifactFreshnessPanel project={run.project} />}

      {/* Flat per-step execution honesty (P2): each step is exactly one of
          exécuté / validé sans exécution / réutilisé — the antidote to a partial
          plan reading as "a full migration ran". Auto-opens for partial plans. */}
      {isMigration && (
        <div className="mb-6 rounded-lg border border-[#dae0e7] bg-white">
          <button
            onClick={() => setStepsOpen((o) => !o)}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left"
          >
            <span className="text-xs text-[#7d8a9a]">{stepsOpen ? '▾' : '▸'}</span>
            <span className="text-sm font-semibold text-[#001932]">Étapes — exécution</span>
            <span className="text-xs text-[#7d8a9a]">
              {allSteps.length} étape{allSteps.length > 1 ? 's' : ''} · exécuté / validé sans exécution / réutilisé
            </span>
          </button>
          {stepsOpen && (
            <div className="divide-y divide-[#f0f3f7] border-t border-[#eef2f6]">
              {allSteps.map((st, i) => (
                <div key={st.id} className="flex items-start gap-3 px-4 py-2">
                  <span className="w-5 shrink-0 text-right text-[11px] text-[#9aa6b4]">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[11px] text-[#5b6b7b]">{st.id}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${STEP_PILL[st.status] || 'bg-[#eef2f6] text-[#5b6b7b]'}`}>
                        {st.status}
                      </span>
                      <span className="truncate text-[12px] text-[#33445a]">{st.title}</span>
                    </div>
                    <div className="mt-0.5">
                      <StepHonestyBadge step={st} provenance={provenance[st.id]} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <ActivityBar run={run} />
      <LiveLog run={run} />

      {isMigration ? (
        <div className="mt-4 border-t border-gray-800 pt-3">
          <button
            onClick={() => setShowRaw((s) => !s)}
            className="text-xs font-medium text-gray-500 hover:text-gray-300"
          >
            {showRaw ? '▾' : '▸'} Détails bruts (Epic / Story / Step)
          </button>
          {showRaw && (
            <div className="mt-3 space-y-4">
              <RunReport run={run} />
              <EpicTimeline run={run} provenance={provenance} />
            </div>
          )}
        </div>
      ) : (
        <>
          <RunReport run={run} />
          <EpicTimeline run={run} provenance={provenance} />
        </>
      )}
    </div>
  )
}
