import { useEffect, useState } from 'react'
import { BeforeAfterSlider } from './BeforeAfterSlider'
import { approveFidelityGate, artifactUrl, fetchReconstructReport, rejectFidelityGate, rerunFidelity } from './api'
import type { ReconstructPage, ReconstructReport } from './types'

const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%)' } as const

interface Props {
  runId: string
  stepId: string
  onApproved?: () => void
}

/**
 * The Fidelity gate — the migration-specific HALT review. Renders the
 * reconstruct.json report as a gallery of drag-to-compare cards (source vs a
 * reconstruction built from ONLY the extracted components), and lets the
 * operator approve before templatization. Replaces the generic RectificationPanel
 * for gate_type === 'fidelity'.
 */
export function FidelityGate({ runId, stepId, onApproved }: Props) {
  const [report, setReport] = useState<ReconstructReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () =>
    fetchReconstructReport(runId)
      .then((r) => {
        setReport(r)
        setError(null)
      })
      .catch((e) => setError(String(e.message ?? e)))

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, stepId])

  if (error) return <div className="p-6 font-mono text-sm text-[#bd2a33]">Fidelity report unavailable — {error}</div>
  if (!report) return <div className="p-6 text-[#7d8a9a]">Loading reconstruction report…</div>

  const pages = report.pages
  const passed = pages.filter((p) => p.ok && p.pass).length
  const allPass = passed === pages.length

  const approve = async () => {
    setBusy(true)
    await approveFidelityGate(runId)
    setBusy(false)
    onApproved?.()
  }

  return (
    <div className="text-[#001932]">
      {/* gate header */}
      <div className="mb-4 flex flex-wrap items-start gap-4 bg-white p-5 shadow-sm" style={NOTCH}>
        <div className="grid h-10 w-10 flex-none place-items-center rounded-xl border border-[#bcdcef] bg-[#e4f2fb] text-lg text-[#0077bf]">
          ◆
        </div>
        <div className="min-w-0">
          <h1 className="text-[17px] font-bold tracking-tight">Reconstruction fidelity — approve before templatization</h1>
          <p className="mt-1 max-w-[64ch] text-[12.5px] text-[#3d556c]">
            Each page is rebuilt from <b>only</b> the extracted components and pixel-diffed against the live source. Drag
            the divider to compare. Approving hands a verified model to the template step.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-wide ${
              allPass
                ? 'border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]'
                : 'border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]'
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
            {allPass ? `Gate green · ${passed}/${pages.length}` : `Review · ${passed}/${pages.length} pass`}
          </span>
          <button
            onClick={() => rerunFidelity(runId).then(load)}
            className="rounded-md border border-[#c7d0da] bg-white px-3.5 py-2 text-[11.5px] font-bold uppercase tracking-wide hover:border-[#0077bf]"
          >
            Re-run
          </button>
          <button
            onClick={() => rejectFidelityGate(runId, 'fidelity gap — fixing extraction')}
            className="rounded-md border border-[#c7d0da] bg-white px-3.5 py-2 text-[11.5px] font-bold uppercase tracking-wide hover:border-[#bd2a33] hover:text-[#bd2a33]"
          >
            Reject
          </button>
          <button
            onClick={approve}
            disabled={busy}
            className="rounded-md border border-[#0077bf] bg-[#0077bf] px-3.5 py-2 text-[11.5px] font-bold uppercase tracking-wide text-white hover:bg-[#025a91] disabled:opacity-60"
          >
            Approve &amp; continue <span className="ml-2 border-l border-white/60 pl-2 font-normal opacity-70">›</span>
          </button>
        </div>
      </div>

      {/* per-page review cards */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
        {pages.map((p) => (
          <PageCard key={p.slug} runId={runId} page={p} />
        ))}
      </div>

      <p className="mt-4 px-0.5 text-[11.5px] text-[#3d556c]">
        Pink = pixels the components don’t reproduce (section backgrounds &amp; hero imagery). That layer is the{' '}
        <b className="text-[#001932]">template + asset-import</b>’s job — quantified here so those steps get a spec, not
        a surprise.
      </p>
    </div>
  )
}

function PageCard({ runId, page }: { runId: string; page: ReconstructPage }) {
  if (!page.ok) {
    return (
      <div className="bg-white p-4 shadow-sm" style={NOTCH}>
        <div className="font-mono text-[12.5px]">{page.slug}</div>
        <div className="mt-2 font-mono text-xs text-[#bd2a33]">FAILED — {page.error}</div>
      </div>
    )
  }
  const real = (page.orphanSamples ?? []).filter((o) => !o.ignorable)
  const ignorable = (page.orphanSamples ?? []).filter((o) => o.ignorable)
  return (
    <div className="overflow-hidden bg-white shadow-sm" style={NOTCH}>
      <div className="flex items-center gap-2 border-b border-[#dae0e7] px-3 py-2.5">
        <span className="font-mono text-[12.5px]">{page.slug}</span>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-extrabold tracking-wide ${
            page.pass ? 'border border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]' : 'border border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]'
          }`}
        >
          {page.pass ? 'PASS' : 'REVIEW'}
        </span>
      </div>

      <BeforeAfterSlider
        before={artifactUrl(runId, `reconstruct/${page.slug}.source.png`)}
        after={artifactUrl(runId, `reconstruct/${page.slug}.recon.png`)}
      />

      <div className="flex gap-4 border-t border-[#dae0e7] px-3 py-2.5 font-mono tabular-nums">
        <Metric v={`${page.contentCoverage ?? 0}%`} l="content" cls="text-[#12b08a]" />
        <Metric v={`${page.pixelSimilarity ?? 0}%`} l="pixel" cls="text-[#d6217d]" />
        <Metric v={String(page.nComps ?? 0)} l="components" />
      </div>

      <div className="flex flex-wrap gap-1.5 px-3 pb-3">
        {real.length === 0 && (
          <span className="rounded-full border border-[#c7d0da] px-2 py-0.5 font-mono text-[10px] text-[#7d8a9a] opacity-75">
            no real content uncaptured ✓
          </span>
        )}
        {real.map((o, i) => (
          <span
            key={`r${i}`}
            title={`<${o.tag} class="${o.cls}">`}
            className="rounded-full border border-[#f0d9a8] bg-[#fbf0da] px-2 py-0.5 font-mono text-[10px] text-[#ab6000]"
          >
            {o.text.slice(0, 28)}
          </span>
        ))}
        {ignorable.slice(0, 2).map((o, i) => (
          <span
            key={`i${i}`}
            className="rounded-full border border-[#c7d0da] px-2 py-0.5 font-mono text-[10px] text-[#7d8a9a] opacity-70"
          >
            {o.text.slice(0, 22)} · ignorable
          </span>
        ))}
      </div>
    </div>
  )
}

function Metric({ v, l, cls = 'text-[#001932]' }: { v: string; l: string; cls?: string }) {
  return (
    <div>
      <div className={`text-sm font-bold ${cls}`}>{v}</div>
      <div className="text-[9px] uppercase tracking-wide text-[#7d8a9a]">{l}</div>
    </div>
  )
}
