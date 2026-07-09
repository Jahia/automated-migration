import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchProjectArtifacts, fetchRuns } from '../api'
import type { ProjectArtifactsReport, RunSummary } from '../types'

const statusColors: Record<string, string> = {
  created: 'bg-gray-500',
  running: 'bg-blue-500 animate-pulse',
  paused: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  aborted: 'bg-gray-500',
}

const NO_PROJECT = '(sans projet)'

interface ProjectGroup {
  project: string
  runs: RunSummary[]
  latest: RunSummary
}

/** Group runs by project; groups sorted by most recent activity desc, "(sans projet)" last. */
function groupByProject(runs: RunSummary[]): ProjectGroup[] {
  const byProject = new Map<string, RunSummary[]>()
  for (const run of runs) {
    const key = run.project || NO_PROJECT
    const list = byProject.get(key)
    if (list) list.push(run)
    else byProject.set(key, [run])
  }
  const groups: ProjectGroup[] = [...byProject.entries()].map(([project, list]) => {
    const sorted = [...list].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))
    return { project, runs: sorted, latest: sorted[0] }
  })
  groups.sort((a, b) => {
    if (a.project === NO_PROJECT) return 1
    if (b.project === NO_PROJECT) return -1
    return (b.latest?.created_at ?? 0) - (a.latest?.created_at ?? 0)
  })
  return groups
}

function formatCreatedAt(ms?: number): string {
  if (!ms) return ''
  return new Date(ms).toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** Compact staleness summary from a project's artifact registry. `undefined` while
 * loading, `null` if the endpoint is unavailable (older engine / no project dir). */
type ArtifactSummary = { stale: number; total: number } | null | undefined

function ArtifactChip({ summary }: { summary: ArtifactSummary }) {
  if (summary === undefined) return <span className="text-xs text-gray-600">artefacts…</span>
  if (summary === null) return <span className="text-xs text-gray-600" title="Provenance indisponible (moteur ancien ou projet absent)">artefacts —</span>
  if (summary.total === 0) return <span className="text-xs text-gray-600">aucun artefact</span>
  if (summary.stale === 0)
    return (
      <span className="text-xs text-green-400" title={`${summary.total} artefacts, tous à jour`}>
        ● {summary.total} artefacts à jour
      </span>
    )
  return (
    <span className="text-xs text-amber-400" title={`${summary.stale} artefact(s) stale sur ${summary.total}`}>
      ▲ {summary.stale}/{summary.total} stale
    </span>
  )
}

export default function ProjectList() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [artifacts, setArtifacts] = useState<Record<string, ArtifactSummary>>({})
  const [loading, setLoading] = useState(true)
  const [lastPoll, setLastPoll] = useState<Date>(new Date())
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

  const groups = groupByProject(runs)

  // Enrich each real project (never the "(sans projet)" bucket) with artifact staleness.
  // Best-effort and independent: a failing project degrades to a "—" chip, not a crash.
  useEffect(() => {
    let cancelled = false
    const realProjects = groups.filter((g) => g.project !== NO_PROJECT).map((g) => g.project)
    for (const project of realProjects) {
      fetchProjectArtifacts(project)
        .then((report: ProjectArtifactsReport) => {
          if (cancelled) return
          const present = report.artifacts.filter((a) => a.exists)
          const stale = present.filter((a) => a.stale).length
          setArtifacts((prev) => ({ ...prev, [project]: { stale, total: present.length } }))
        })
        .catch(() => {
          if (cancelled) return
          setArtifacts((prev) => ({ ...prev, [project]: null }))
        })
    }
    return () => {
      cancelled = true
    }
    // Re-run when the set of project names changes (join keeps it a stable primitive).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups.map((g) => g.project).join('|')])

  const openZoning = (e: React.MouseEvent, project: string) => {
    e.preventDefault()
    e.stopPropagation()
    navigate(`/zoning?project=${encodeURIComponent(project)}`)
  }

  if (loading) return <div className="text-gray-400">Chargement...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Projets</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {groups.filter((g) => g.project !== NO_PROJECT).length} projet(s) · {runs.length} run(s)
          </p>
        </div>
        <span className="text-xs text-gray-500">Mis à jour: {lastPoll.toLocaleTimeString()}</span>
      </div>

      {error && (
        <div className="mb-4 bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {runs.length === 0 ? (
        <p className="text-gray-500">Aucun run. Les runs sont pilotés via l'API (CONTROL-LOOP.md).</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => {
            const running = group.runs.filter((r) => r.status === 'running').length
            const paused = group.runs.filter((r) => r.status === 'paused').length
            return (
              <Link
                key={group.project}
                to={`/projects/${encodeURIComponent(group.project)}`}
                className="flex flex-col justify-between bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition min-h-[9rem]"
              >
                <div>
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="text-lg font-semibold text-gray-100 truncate">{group.project}</h2>
                    <span className="text-xs text-gray-500 whitespace-nowrap">
                      {group.runs.length} run{group.runs.length > 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-sm">
                    <span className={`w-2.5 h-2.5 rounded-full ${statusColors[group.latest.status] || 'bg-gray-500'}`} />
                    <span className="text-gray-400">{group.latest.status}</span>
                    <span className="text-xs text-gray-600 ml-auto whitespace-nowrap">
                      {formatCreatedAt(group.latest.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500 line-clamp-2">{group.latest.goal}</p>
                </div>

                <div className="mt-4 flex items-center justify-between gap-2 border-t border-gray-800 pt-3">
                  <ArtifactChip summary={group.project === NO_PROJECT ? null : artifacts[group.project]} />
                  <div className="flex items-center gap-3">
                    {(running > 0 || paused > 0) && (
                      <span className="text-xs text-gray-500">
                        {running > 0 && <span className="text-blue-400">{running} actif</span>}
                        {running > 0 && paused > 0 && ' · '}
                        {paused > 0 && <span className="text-yellow-400">{paused} en pause</span>}
                      </span>
                    )}
                    {group.project !== NO_PROJECT && (
                      <button
                        onClick={(e) => openZoning(e, group.project)}
                        className="text-xs text-[#a8c1d6] hover:text-white underline underline-offset-2"
                        title="Ouvrir le cockpit de zoning pour ce projet"
                      >
                        Zoning →
                      </button>
                    )}
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
