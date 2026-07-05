import { useEffect, useRef, useState } from 'react'
import type { ContentProgress, ContentTick, RunState } from '../../types'
import { fetchContentProgress } from '../../api'

/**
 * Content-load progress card — read-only observability for step_content_load
 * (Julian, 2026-07-04). Polls GET /projects/{project}/content-progress every 30s,
 * which reads the content_watch.sh ticker (no Jahia call). Degrades gracefully:
 * the endpoint only exists after the next engine restart, so a 404/network error
 * shows a "belt endpoint not loaded" note instead of breaking the run view.
 *
 * The cockpit is observability-only (commit 3388ee4): this card never pilots.
 */
const POLL_MS = 30_000

/** The project this run migrates: any step's inputs carry projects/<name>. */
export function projectOfRun(run: RunState): string | null {
  for (const epic of run.epics) {
    for (const story of epic.stories) {
      for (const step of story.steps) {
        const raw = (step.inputs?.project_path ?? step.inputs?.project) as string | undefined
        if (raw && typeof raw === 'string') {
          // 'projects/discoverasr' → 'discoverasr'; a bare 'discoverasr' → itself
          const seg = raw.replace(/\/+$/, '').split('/').pop()
          if (seg) return seg
        }
      }
    }
  }
  return null
}

export function ContentLoadProgress({ run }: { run: RunState }) {
  const project = projectOfRun(run)
  const [data, setData] = useState<ContentProgress | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    if (!project) return
    let alive = true
    const poll = () =>
      fetchContentProgress(project)
        .then((d) => {
          if (!alive) return
          setData(d)
          setUnavailable(false)
        })
        .catch(() => {
          if (!alive) return
          setUnavailable(true)
        })
    poll()
    timer.current = setInterval(poll, POLL_MS)
    return () => {
      alive = false
      clearInterval(timer.current)
    }
  }, [project])

  if (!project) return null

  return (
    <div className="mb-4 border border-[#dae0e7] bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[10px] font-semibold uppercase tracking-[0.8px] text-[#7d8a9a]">
          Content load progress
        </div>
        <div className="font-mono text-[10px] text-[#9aa6b4]">{project}</div>
      </div>
      {unavailable && !data ? (
        <div className="text-xs text-[#9aa6b4]">
          belt endpoint non chargé (redémarrage moteur en attente)
        </div>
      ) : !data || data.ticks.length === 0 ? (
        <div className="text-xs text-[#9aa6b4]">en attente du premier tick…</div>
      ) : (
        <Body data={data} />
      )}
    </div>
  )
}

function Body({ data }: { data: ContentProgress }) {
  const latest = data.latest as ContentTick
  const expected = latest.expected || 0
  const created = latest.created || 0
  const pct = latest.pct ?? (expected ? (100 * created) / expected : 0)
  const done = pct >= 100

  return (
    <div>
      {/* created / expected progress bar */}
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-mono text-[22px] font-bold leading-none tabular-nums text-[#001932]">
          {created.toLocaleString()}
          <span className="text-[13px] font-semibold text-[#9aa6b4]"> / {expected.toLocaleString()}</span>
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums text-[#0077bf]">
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-[#eef2f6]">
        <div
          className={`h-full rounded-full ${done ? 'bg-[#12b08a]' : 'bg-[#0077bf]'}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>

      {/* counters */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <Metric label="Pages started" value={`${latest.pagesStarted} / ${latest.pagesTotal}`} />
        <Metric label="Media (DAM)" value={latest.media.toLocaleString()} />
        <Metric
          label="Mismatches"
          value={data.report ? String(data.report.mismatchCount) : '—'}
          warn={!!data.report && data.report.mismatchCount > 0}
        />
      </div>

      <Sparkline ticks={data.ticks} />

      <div className="mt-2 flex items-center justify-between text-[10px] text-[#9aa6b4]">
        <span>{data.ticks.length} tick(s)</span>
        <span>{latest.ts ? new Date(latest.ts).toLocaleTimeString() : ''}</span>
      </div>
    </div>
  )
}

function Metric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="border border-[#eef2f6] bg-[#f7f9fb] px-2 py-1.5">
      <div className={`font-mono text-sm font-bold tabular-nums ${warn ? 'text-[#d6217d]' : 'text-[#001932]'}`}>
        {value}
      </div>
      <div className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.6px] text-[#7d8a9a]">{label}</div>
    </div>
  )
}

/** A dependency-free SVG sparkline of created-count over the ticks. */
function Sparkline({ ticks }: { ticks: ContentTick[] }) {
  const W = 100
  const H = 24
  if (ticks.length < 2) {
    return <div className="h-6 text-[10px] leading-6 text-[#c0c9d3]">courbe: en attente de plus de ticks…</div>
  }
  const vals = ticks.map((t) => t.created ?? 0)
  const max = Math.max(...vals, 1)
  const n = vals.length
  const pts = vals.map((v, i) => {
    const x = (i / (n - 1)) * W
    const y = H - (v / max) * (H - 2) - 1
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })
  const line = pts.join(' ')
  const area = `0,${H} ${line} ${W},${H}`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-6 w-full" role="img" aria-label="created nodes over time">
      <polygon points={area} fill="#0077bf" fillOpacity="0.08" />
      <polyline points={line} fill="none" stroke="#0077bf" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
