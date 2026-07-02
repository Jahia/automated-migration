import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { fetchRuns, startRun, restartRun, deleteRun, pruneRuns } from '../api'

interface RunSummary {
  run_id: string
  goal: string
  status: string
  created_at: number
}

const statusColors: Record<string, string> = {
  created: 'bg-gray-500',
  running: 'bg-blue-500 animate-pulse',
  paused: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  aborted: 'bg-gray-500',
}

export default function RunList() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [lastPoll, setLastPoll] = useState<Date>(new Date())
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchRuns()
      setRuns(data)
      setError(null)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
      setLastPoll(new Date())
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [load])

  const handleStart = async (e: React.MouseEvent, runId: string) => {
    e.preventDefault()
    setActionLoading(runId)
    setError(null)
    try {
      await startRun(runId)
      await load()
    } catch (e) {
      setError(`Erreur démarrage: ${e}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleRestart = async (e: React.MouseEvent, runId: string) => {
    e.preventDefault()
    setActionLoading(runId)
    setError(null)
    try {
      await restartRun(runId)
      await load()
    } catch (e) {
      setError(`Erreur relance: ${e}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handleDelete = async (e: React.MouseEvent, runId: string) => {
    e.preventDefault()
    if (!window.confirm(`Supprimer définitivement le run ${runId} ?`)) return
    setActionLoading(runId)
    setError(null)
    try {
      await deleteRun(runId)
      await load()
    } catch (e) {
      setError(`Erreur suppression: ${e}`)
    } finally {
      setActionLoading(null)
    }
  }

  const handlePrune = async () => {
    if (!window.confirm('Supprimer tous les runs terminés (completed/failed/aborted) ?')) return
    setActionLoading('__prune__')
    setError(null)
    try {
      const res = await pruneRuns()
      await load()
      setError(res.count === 0 ? 'Aucun run terminé à supprimer.' : null)
    } catch (e) {
      setError(`Erreur purge: ${e}`)
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) return <div className="text-gray-400">Chargement...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Runs</h1>
        <div className="flex items-center gap-3">
          <Link
            to="/new"
            className="px-3 py-1.5 bg-[#0077bf] hover:bg-[#0069a8] rounded text-xs font-semibold text-white"
          >
            + Nouvelle migration
          </Link>
          <button
            onClick={handlePrune}
            disabled={actionLoading === '__prune__'}
            className="px-3 py-1 bg-red-800 hover:bg-red-700 disabled:opacity-50 rounded text-xs"
            title="Supprimer tous les runs terminés"
          >
            {actionLoading === '__prune__' ? '...' : 'Purger terminés'}
          </button>
          <span className="text-xs text-gray-500">
            Mis à jour: {lastPoll.toLocaleTimeString()}
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {runs.length === 0 ? (
        <p className="text-gray-500">
          Aucun run.{' '}
          <Link to="/new" className="text-[#4aa6dd] hover:text-[#7fd0f5]">
            Lancer une nouvelle migration
          </Link>
          .
        </p>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <Link
              key={run.run_id}
              to={`/runs/${run.run_id}`}
              className="block bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition"
            >
              <div className="flex items-center gap-3">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColors[run.status] || 'bg-gray-500'}`} />
                <span className="font-mono text-sm text-gray-400">{run.run_id}</span>
                <span className="text-gray-300 flex-1 truncate">{run.goal}</span>
                <span className="text-xs text-gray-500">{run.status}</span>
                {run.status === 'created' && (
                  <button
                    onClick={(e) => handleStart(e, run.run_id)}
                    disabled={actionLoading === run.run_id}
                    className="px-3 py-1 bg-green-700 hover:bg-green-600 disabled:opacity-50 rounded text-xs"
                  >
                    {actionLoading === run.run_id ? '...' : 'Démarrer'}
                  </button>
                )}
                {['failed', 'completed', 'aborted'].includes(run.status) && (
                  <button
                    onClick={(e) => handleRestart(e, run.run_id)}
                    disabled={actionLoading === run.run_id}
                    className="px-3 py-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 rounded text-xs"
                  >
                    {actionLoading === run.run_id ? '...' : 'Relancer'}
                  </button>
                )}
                {['failed', 'completed', 'aborted', 'created'].includes(run.status) && (
                  <button
                    onClick={(e) => handleDelete(e, run.run_id)}
                    disabled={actionLoading === run.run_id}
                    className="px-3 py-1 bg-gray-700 hover:bg-red-700 disabled:opacity-50 rounded text-xs"
                    title="Supprimer ce run"
                  >
                    {actionLoading === run.run_id ? '...' : 'Supprimer'}
                  </button>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
