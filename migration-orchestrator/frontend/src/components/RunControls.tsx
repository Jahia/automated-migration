import { useState } from 'react'
import { pauseRun, resumeRun, abortRun, jumpToStep, startRun, restartRun } from '../api'
import type { RunState } from '../types'

interface Props {
  run: RunState
  onReload: () => void
}

export default function RunControls({ run, onReload }: Props) {
  const [jumpTarget, setJumpTarget] = useState('')
  const [resetDeps, setResetDeps] = useState(true)
  const [loading, setLoading] = useState<string | null>(null)

  const allSteps = run.epics.flatMap((epic) =>
    epic.stories.flatMap((story) =>
      story.steps.map((step) => ({
        id: step.id,
        label: `${epic.id}/${story.id}/${step.task_type} [${step.status}]`,
        status: step.status,
      }))
    )
  )

  const runAction = async (name: string, fn: () => Promise<void>) => {
    setLoading(name)
    try {
      await fn()
      onReload()
    } finally {
      setLoading(null)
    }
  }

  const isTerminal = ['failed', 'completed', 'aborted'].includes(run.status)

  return (
    <div className="flex items-center gap-2">
      {run.status === 'created' && (
        <button onClick={() => runAction('start', () => startRun(run.run_id))} disabled={!!loading}
          className="px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded text-sm">
          {loading === 'start' ? '...' : 'Démarrer'}
        </button>
      )}
      {run.status === 'running' && (
        <button onClick={() => runAction('pause', () => pauseRun(run.run_id))} disabled={!!loading}
          className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 rounded text-sm">
          {loading === 'pause' ? '...' : 'Pause'}
        </button>
      )}
      {run.status === 'paused' && (
        <button onClick={() => runAction('resume', () => resumeRun(run.run_id))} disabled={!!loading}
          className="px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded text-sm">
          {loading === 'resume' ? '...' : 'Resume'}
        </button>
      )}
      {(run.status === 'running' || run.status === 'paused') && (
        <button onClick={() => { if (confirm('Annuler ?')) runAction('abort', () => abortRun(run.run_id)) }} disabled={!!loading}
          className="px-3 py-1.5 bg-red-700 hover:bg-red-600 disabled:opacity-50 rounded text-sm">
          Abort
        </button>
      )}
      {isTerminal && (
        <button onClick={() => { if (confirm('Relancer ?')) runAction('restart', () => restartRun(run.run_id)) }} disabled={!!loading}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm">
          {loading === 'restart' ? 'Relancement...' : 'Relancer'}
        </button>
      )}
      {(run.status === 'running' || run.status === 'paused') && (
        <div className="flex items-center gap-1 ml-2">
          <select value={jumpTarget} onChange={(e) => setJumpTarget(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm">
            <option value="">Jump to...</option>
            {allSteps.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
          <label className="flex items-center gap-1 text-xs text-gray-400">
            <input type="checkbox" checked={resetDeps} onChange={(e) => setResetDeps(e.target.checked)} />
            Reset deps
          </label>
          <button onClick={() => runAction('jump', () => jumpToStep(run.run_id, jumpTarget, resetDeps).then(() => {}))}
            disabled={!jumpTarget || !!loading}
            className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 rounded text-sm">
            Go
          </button>
        </div>
      )}
    </div>
  )
}
