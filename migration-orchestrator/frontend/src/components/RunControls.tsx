import { useState } from 'react'
import { pauseRun, resumeRun, abortRun } from '../api'
import type { RunState } from '../types'

interface Props {
  run: RunState
  onReload: () => void
}

// Observability-only cockpit: runs are launched and relaunched exclusively via
// the REST API (see CONTROL-LOOP.md). This surface keeps only the in-flight
// decision controls — pause / resume / abort — never start or restart.
export default function RunControls({ run, onReload }: Props) {
  const [loading, setLoading] = useState<string | null>(null)

  const runAction = async (name: string, fn: () => Promise<void>) => {
    setLoading(name)
    try {
      await fn()
      onReload()
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="flex items-center gap-2">
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
    </div>
  )
}
