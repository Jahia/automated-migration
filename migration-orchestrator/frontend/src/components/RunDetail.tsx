import { useParams } from 'react-router-dom'
import { useRun } from '../hooks/useRun'
import RunControls from './RunControls'
import EpicTimeline from './EpicTimeline'
import ActivityBar from './ActivityBar'
import LiveLog from './LiveLog'
import RunReport from './RunReport'
import { useEffect, useState, useRef } from 'react'

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const { run, loading, error, reload } = useRun(runId || null)
  const [lastPoll, setLastPoll] = useState(new Date())
  const [pollCount, setPollCount] = useState(0)
  const [healthOk, setHealthOk] = useState(true)
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

  const runningStep = run.epics
    .flatMap(e => e.stories)
    .flatMap(s => s.steps)
    .find(st => st.status === 'running')

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

      <ActivityBar run={run} />
      <RunReport run={run} />
      <LiveLog run={run} />
      <EpicTimeline run={run} />
    </div>
  )
}
