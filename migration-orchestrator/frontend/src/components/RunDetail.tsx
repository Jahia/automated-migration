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
import { useEffect, useState, useRef } from 'react'

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const { run, loading, error, reload } = useRun(runId || null)
  const [lastPoll, setLastPoll] = useState(new Date())
  const [pollCount, setPollCount] = useState(0)
  const [healthOk, setHealthOk] = useState(true)
  const [showRaw, setShowRaw] = useState(false)
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)
  const pollTimer = useRef<ReturnType<typeof setInterval>>()

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
              <EpicTimeline run={run} />
            </div>
          )}
        </div>
      ) : (
        <>
          <RunReport run={run} />
          <EpicTimeline run={run} />
        </>
      )}
    </div>
  )
}
