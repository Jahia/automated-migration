import { useEffect, useState } from 'react'
import type { RunState } from '../../types'
import { artifactUrl } from '../fidelity/api'
import type { ComponentManifest } from './types'
import type { ReconstructReport } from '../fidelity/types'

const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 13px) 0, 100% 13px, 100% 100%, 0 100%)' } as const

/**
 * The migration KPI strip: model size + fidelity + spend, pulled from the run's
 * artifacts (component-manifest.json, reconstruct.json) and its step ledger.
 * Values read "—" until the phase that produces them completes; the effect
 * re-fetches whenever another step finishes (a new artifact has appeared).
 */
export function KpiBar({ run }: { run: RunState }) {
  const [manifest, setManifest] = useState<ComponentManifest | null>(null)
  const [recon, setRecon] = useState<ReconstructReport | null>(null)
  const [inventory, setInventory] = useState<{ pages: unknown[] } | null>(null)

  const steps = run.epics.flatMap((e) => e.stories).flatMap((s) => s.steps)
  const doneCount = steps.filter((s) => s.status === 'done').length

  useEffect(() => {
    let alive = true
    const grab = <T,>(path: string, set: (v: T | null) => void) =>
      fetch(artifactUrl(run.run_id, path))
        .then((r) => (r.ok ? (r.json() as Promise<T>) : null))
        .then((d) => alive && set(d))
        .catch(() => {})
    grab<ComponentManifest>('component-manifest.json', setManifest)
    grab<ReconstructReport>('reconstruct/reconstruct.json', setRecon)
    grab<{ pages: unknown[] }>('page-inventory.json', setInventory)
    return () => {
      alive = false
    }
  }, [run.run_id, doneCount])

  const cost = steps.reduce((a, s) => a + (s.cost || 0), 0)
  const tokensOut = steps.reduce((a, s) => a + (s.tokens_out || 0), 0)

  const types = manifest?.components.length
  const templates = manifest?.templates.length
  const xcut = manifest?.crossCutting.length
  // crawled inventory is the honest page count; template-covered pages as fallback
  const pages = inventory?.pages?.length ?? (manifest ? new Set(manifest.templates.flatMap((t) => t.pages)).size : undefined)

  const covPages = recon?.pages.filter((p) => p.contentCoverage != null) ?? []
  const coverage = covPages.length
    ? covPages.reduce((a, p) => a + (p.contentCoverage ?? 0), 0) / covPages.length
    : undefined

  return (
    <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <Kpi label="Pages" value={num(pages)} />
      <Kpi label="Content types" value={num(types)} accent />
      <Kpi label="Templates" value={num(templates)} />
      <Kpi label="Cross-cutting" value={num(xcut)} accent />
      <Kpi label="Fidelity coverage" value={coverage != null ? `${coverage.toFixed(0)}%` : '—'} bar={coverage} />
      <Kpi
        label="Spend"
        value={cost ? `$${cost.toFixed(2)}` : '—'}
        sub={tokensOut ? `${(tokensOut / 1000).toFixed(0)}k tok out` : undefined}
      />
    </div>
  )
}

function num(n?: number) {
  return n == null ? '—' : String(n)
}

function Kpi({
  label,
  value,
  accent,
  sub,
  bar,
}: {
  label: string
  value: string
  accent?: boolean
  sub?: string
  bar?: number
}) {
  const ok = bar != null && bar >= 95
  return (
    <div className="border border-[#dae0e7] bg-white px-3 py-2.5" style={NOTCH}>
      <div className={`font-mono text-[22px] font-bold leading-none tabular-nums ${accent ? 'text-[#0077bf]' : 'text-[#001932]'}`}>
        {value}
      </div>
      <div className="mt-1 text-[9.5px] font-semibold uppercase tracking-[0.8px] text-[#7d8a9a]">{label}</div>
      {bar != null && (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[#eef2f6]">
          <div
            className={`h-full rounded-full ${ok ? 'bg-[#12b08a]' : 'bg-[#d6217d]'}`}
            style={{ width: `${Math.min(100, Math.max(0, bar))}%` }}
          />
        </div>
      )}
      {sub && <div className="mt-1 text-[10px] text-[#9aa6b4]">{sub}</div>}
    </div>
  )
}
