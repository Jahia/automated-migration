import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchRuns, deleteRun, pruneRuns } from '../api'
import type { RunSummary } from '../types'

const statusColors: Record<string, string> = {
  created: 'bg-gray-500',
  running: 'bg-blue-500 animate-pulse',
  paused: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  aborted: 'bg-gray-500',
}

const NO_PROJECT = '(sans projet)'

/** Group runs by project; groups sorted by most recent created_at desc, "(sans projet)" always last. */
function groupByProject(runs: RunSummary[]): { project: string; runs: RunSummary[] }[] {
  const byProject = new Map<string, RunSummary[]>()
  for (const run of runs) {
    const key = run.project || NO_PROJECT
    const list = byProject.get(key)
    if (list) list.push(run)
    else byProject.set(key, [run])
  }
  const groups = [...byProject.entries()].map(([project, list]) => ({
    project,
    runs: [...list].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0)),
  }))
  groups.sort((a, b) => {
    if (a.project === NO_PROJECT) return 1
    if (b.project === NO_PROJECT) return -1
    return (b.runs[0]?.created_at ?? 0) - (a.runs[0]?.created_at ?? 0)
  })
  return groups
}

/** Compact creation date-time (created_at is epoch milliseconds). */
function formatCreatedAt(ms?: number): string {
  if (!ms) return ''
  return new Date(ms).toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function RunList() {
  // When mounted at /projects/:project the list is scoped to that one project
  // (the ProjectList grid is the landing); at /runs it shows every project.
  const { project: projectParam } = useParams<{ project?: string }>()
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

  const scoped = projectParam ? decodeURIComponent(projectParam) : null
  const visibleRuns = scoped ? runs.filter((r) => (r.project || NO_PROJECT) === scoped) : runs

  return (
    <div>
      {scoped && (
        <Link to="/" className="mb-3 inline-block text-sm text-[#a8c1d6] hover:text-white">
          ← Projets
        </Link>
      )}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{scoped ? scoped : 'Runs'}</h1>
        <div className="flex items-center gap-3">
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

      {visibleRuns.length === 0 ? (
        <p className="text-gray-500">
          {scoped ? 'Aucun run pour ce projet.' : "Aucun run. Les runs sont pilotés via l'API (CONTROL-LOOP.md)."}
        </p>
      ) : (
        <div className="space-y-6">
          {groupByProject(visibleRuns).map((group) => (
            <div key={group.project}>
              <div className="flex items-baseline gap-2 mb-2">
                <h2 className="text-sm font-semibold text-gray-300">{group.project}</h2>
                <span className="text-xs text-gray-500">
                  {group.runs.length} run{group.runs.length > 1 ? 's' : ''}
                </span>
              </div>
              <div className="space-y-3">
                {group.runs.map((run) => (
                  <Link
                    key={run.run_id}
                    to={`/runs/${run.run_id}`}
                    className="block bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`w-2.5 h-2.5 rounded-full ${statusColors[run.status] || 'bg-gray-500'}`} />
                      <span className="font-mono text-sm text-gray-400">{run.run_id}</span>
                      <span className="text-gray-300 flex-1 truncate">{run.goal}</span>
                      <span className="text-xs text-gray-600 whitespace-nowrap">{formatCreatedAt(run.created_at)}</span>
                      <span className="text-xs text-gray-500">{run.status}</span>
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
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
