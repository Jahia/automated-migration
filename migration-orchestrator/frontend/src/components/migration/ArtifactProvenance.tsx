import { useEffect, useState } from 'react'
import { fetchProjectArtifacts } from '../../api'
import type { ProjectArtifact } from '../../types'

// ── P3b: artifact staleness visible in the cockpit ────────────────────────
// GET /projects/{project}/artifacts (artifact_provenance.py) returns, per known
// pipeline artifact, its provenance stamp (generated_at/run_id/git_sha — null
// for a pre-P0 artifact) and whether a DAG-upstream stage regenerated AFTER it
// (stale). This module is the single place that renders that signal: a compact
// line + a STALE chip, reused by both the per-gate panels (ScopeGate,
// MirrorGate, FidelityGate, ComponentModelView) and the consolidated
// "Artefacts — fraîcheur" list in RunDetail.

const STAGE_LABELS: Record<string, string> = {
  crawl: 'Crawl',
  mirror: 'Miroir local',
  semantic: 'Extraction sémantique',
  segment: 'Segmentation (vision)',
  zone: 'Zonage (signal fin)',
  model: 'Modèle de composants',
  contentload: 'Spéc. contenu',
  compose: 'Composition',
  cnd: 'CND / vues',
  reconstruct: 'Reconstruction (fidelity)',
  load: 'Chargement JCR',
  dam: 'DAM (médias)',
  groundtruth: 'Ground truth',
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

/** Compact French relative time: "à l'instant" / "il y a 5 min" / "il y a 2 h"
 * / "il y a 3 j", falling back to a locale date past 30 days. Never throws on
 * a malformed timestamp — echoes it back so a bug is visible, not swallowed. */
export function fmtRelative(iso?: string | null): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  const diffS = Math.max(0, (Date.now() - t) / 1000)
  if (diffS < 60) return "à l'instant"
  if (diffS < 3600) return `il y a ${Math.round(diffS / 60)} min`
  if (diffS < 86400) return `il y a ${Math.round(diffS / 3600)} h`
  if (diffS < 30 * 86400) return `il y a ${Math.round(diffS / 86400)} j`
  return new Date(t).toLocaleDateString()
}

/** "run_1799001234" -> "1799001234" (strip the label prefix — "run" is already
 * implied by the surrounding text); truncated defensively for any future
 * longer id scheme. */
export function fmtShortRunId(runId?: string | null): string {
  if (!runId) return ''
  const bare = runId.startsWith('run_') ? runId.slice(4) : runId
  return bare.length > 12 ? `${bare.slice(0, 12)}…` : bare
}

/** git_sha is already provenance.py's --short=12 (+"-dirty"); shrink to the
 * conventional 7-char short sha for the compact line. */
export function fmtShortSha(sha?: string | null): string {
  if (!sha) return ''
  const dirty = sha.endsWith('-dirty')
  const base = dirty ? sha.slice(0, -'-dirty'.length) : sha
  return base.slice(0, 7) + (dirty ? '-dirty' : '')
}

/** Fetch + index GET /projects/{project}/artifacts. Degrades silently (empty
 * map, status 'missing') on any error — an older engine, a project not yet
 * created, or a transient network error must never crash the cockpit; it just
 * means no provenance chips render. `refreshKey` is an optional cheap
 * invalidation trigger (e.g. a terminal-step count) for callers that want a
 * refetch without polling continuously. */
export function useProjectArtifacts(project?: string | null, refreshKey: unknown = 0) {
  const [list, setList] = useState<ProjectArtifact[]>([])
  const [status, setStatus] = useState<'loading' | 'ok' | 'missing'>('loading')

  useEffect(() => {
    if (!project) {
      setList([])
      setStatus('missing')
      return
    }
    let alive = true
    setStatus('loading')
    fetchProjectArtifacts(project)
      .then((r) => {
        if (!alive) return
        setList(r.artifacts)
        setStatus('ok')
      })
      .catch(() => {
        if (alive) {
          setList([])
          setStatus('missing')
        }
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, refreshKey])

  const byId: Record<string, ProjectArtifact> = {}
  for (const a of list) byId[a.artifact] = a
  return { list, byId, status }
}

/**
 * The compact provenance line for ONE artifact, meant to sit right under/next
 * to an existing artifact panel's link or header. Renders NOTHING when the
 * artifact hasn't been produced yet (the panel's own "not generated yet"
 * empty-state already covers that) — it only ever ADDS information.
 */
export function ArtifactProvenanceLine({ entry, label }: { entry?: ProjectArtifact; label?: string }) {
  if (!entry || !entry.exists) return null
  const known = !!entry.generated_at
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-[#7d8a9a]">
      {label && <span className="font-semibold text-[#5b6b7b]">{label}</span>}
      <span>
        {known ? (
          <>
            généré {fmtRelative(entry.generated_at)}
            {entry.run_id ? ` · run ${fmtShortRunId(entry.run_id)}` : ''}
            {entry.git_sha ? ` · ${fmtShortSha(entry.git_sha)}` : ''}
          </>
        ) : (
          'provenance inconnue (pré-P0)'
        )}
      </span>
      {entry.stale && (
        <span
          title={entry.stale_reason ?? undefined}
          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-bold ${
            known ? 'border-[#e6b4b4] bg-[#f7e2e2] text-[#bd2a33]' : 'border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]'
          }`}
        >
          STALE{entry.stale_reason ? ` (${entry.stale_reason})` : ''}
        </span>
      )}
      {entry.partial && (
        <span
          title={`Rapport ground-truth PARTIEL — ${entry.partial.pages_covered ?? '?'}/${
            entry.partial.pages_total ?? '?'
          } pages. Le dernier rapport complet reste disponible (review.html).`}
          className="rounded border border-[#bcdcef] bg-[#e4f2fb] px-1.5 py-0.5 font-mono text-[10px] font-bold text-[#0077bf]"
        >
          partiel {entry.partial.pages_covered ?? '?'}/{entry.partial.pages_total ?? '?'} pages
        </span>
      )}
    </div>
  )
}

/**
 * Consolidated, always-complete view of every known pipeline artifact for a
 * project (DAG order, as returned by the endpoint) — the safety net that
 * guarantees staleness is visible even for stages with no dedicated gate panel
 * yet (groundtruth, compose, cnd, segment, zone, load, dam, contentload).
 * Collapsed by default; auto-labelled with a stale count when non-zero.
 */
export function ArtifactFreshnessPanel({ project }: { project?: string | null }) {
  const { list, status } = useProjectArtifacts(project)
  const [open, setOpen] = useState(false)

  if (!project) return null
  const staleCount = list.filter((a) => a.stale).length
  const existCount = list.filter((a) => a.exists).length

  useEffectAutoOpenOnStale(staleCount, setOpen)

  return (
    <div className="mb-6 rounded-lg border border-[#dae0e7] bg-white">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left">
        <span className="text-xs text-[#7d8a9a]">{open ? '▾' : '▸'}</span>
        <span className="text-sm font-semibold text-[#001932]">Artefacts — fraîcheur</span>
        <span className="text-xs text-[#7d8a9a]">
          {status === 'loading' ? 'chargement…' : `${existCount}/${list.length} générés`}
        </span>
        {staleCount > 0 && (
          <span className="rounded border border-[#e6b4b4] bg-[#f7e2e2] px-1.5 py-0.5 text-[10px] font-bold text-[#bd2a33]">
            {staleCount} périmé{staleCount > 1 ? 's' : ''}
          </span>
        )}
      </button>
      {open && (
        <div className="divide-y divide-[#f0f3f7] border-t border-[#eef2f6]">
          {list.length === 0 && status !== 'loading' && (
            <div className="px-4 py-3 text-[12px] text-[#7d8a9a]">
              Aucune information de provenance disponible pour ce projet.
            </div>
          )}
          {list.map((a) => (
            <div key={a.artifact} className="flex flex-wrap items-start gap-3 px-4 py-2">
              <span className="w-36 shrink-0 text-[11px] text-[#5b6b7b]">{stageLabel(a.stage)}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px] text-[#33445a]">{a.artifact}</span>
                  {!a.exists && <span className="text-[10.5px] italic text-[#9aa6b4]">pas encore généré</span>}
                </div>
                <ArtifactProvenanceLine entry={a} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Auto-open the panel the first time it reports ≥1 stale artifact for this
 * project, so an operator approving a gate doesn't have to know to expand it —
 * same "surface honesty by default" instinct as RunDetail's partial-plan
 * auto-open (see isPartialPlan). Fires once per mount, never fights a manual toggle. */
function useEffectAutoOpenOnStale(staleCount: number, setOpen: (v: boolean) => void) {
  const [armed, setArmed] = useState(true)
  useEffect(() => {
    if (armed && staleCount > 0) {
      setOpen(true)
      setArmed(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staleCount, armed])
}
