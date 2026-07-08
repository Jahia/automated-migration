import { useEffect, useMemo, useState } from 'react'
import { BeforeAfterSlider } from './BeforeAfterSlider'
import { approveFidelityGate, artifactUrl, fetchReconstructReport, rejectFidelityGate, rerunFidelity } from './api'
import type { ReconstructPage, ReconstructReport } from './types'
import { ArtifactProvenanceLine, useProjectArtifacts } from '../migration/ArtifactProvenance'

const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%)' } as const

interface Props {
  runId: string
  project?: string | null
  stepId?: string
  onApproved?: () => void
  /** Review mode: render without the approve/reject/rerun actions
   * (e.g. re-viewing a completed run's fidelity gate). */
  readOnly?: boolean
}

/**
 * The Fidelity gate — the migration-specific HALT review. Shows every migrated
 * (probed) page in a table with its pass/fail + content/pixel/component metrics;
 * selecting a row opens a side-by-side source↔reconstruction comparison with the
 * per-page artifact links. Approving hands a verified model to the template step.
 */
export function FidelityGate({ runId, project, stepId, onApproved, readOnly }: Props) {
  const [report, setReport] = useState<ReconstructReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const { byId: artifacts } = useProjectArtifacts(project)

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

  const pages = report?.pages ?? []
  const threshold = report?.threshold ?? 95

  // default selection = the page most worth looking at (a failure, else the
  // lowest content coverage) so the detail panel is never empty.
  const worstSlug = useMemo(() => {
    if (!pages.length) return null
    const ranked = [...pages].sort((a, b) => score(a) - score(b))
    return ranked[0].slug
  }, [pages])
  const activeSlug = selected ?? worstSlug
  const active = pages.find((p) => p.slug === activeSlug) ?? null

  if (error)
    return (
      <div className="border border-dashed border-[#c7d0da] bg-white/60 px-4 py-8 text-center text-[13px] text-[#7d8a9a]" style={NOTCH}>
        Fidelity report not available yet.
      </div>
    )
  if (!report) return <div className="p-6 text-[#7d8a9a]">Loading reconstruction report…</div>

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
        <div className="grid h-10 w-10 flex-none place-items-center rounded-xl border border-[#bcdcef] bg-[#e4f2fb] text-lg text-[#0077bf]">◆</div>
        <div className="min-w-0">
          <h1 className="text-[17px] font-bold tracking-tight">Reconstruction fidelity — approve before templatization</h1>
          <p className="mt-1 max-w-[64ch] text-[12.5px] text-[#3d556c]">
            Each page is rebuilt from <b>only</b> the extracted components and pixel-diffed against the source. Pick a page
            in the table to compare side-by-side. Approving hands a verified model to the template step.
          </p>
          <div className="mt-1.5">
            <ArtifactProvenanceLine label="reconstruct/reconstruct.json" entry={artifacts['reconstruct']} />
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-wide ${
              allPass ? 'border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]' : 'border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]'
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
            {allPass ? `Gate green · ${passed}/${pages.length}` : `Review · ${passed}/${pages.length} pass`}
          </span>
          {!readOnly && (
            <>
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
            </>
          )}
        </div>
      </div>

      {/* pages table — all migrated pages + indicators; click a row to compare */}
      <div className="mb-5 overflow-x-auto bg-white shadow-sm" style={NOTCH}>
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-[#dae0e7] text-[10px] uppercase tracking-wide text-[#7d8a9a]">
              <th className="px-3 py-2 font-semibold">Page</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 text-right font-semibold">Content</th>
              <th className="px-3 py-2 text-right font-semibold">Pixel</th>
              <th className="px-3 py-2 text-right font-semibold">Components</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((p) => {
              const isActive = p.slug === activeSlug
              const status = !p.ok ? 'FAILED' : p.pass ? 'PASS' : 'REVIEW'
              return (
                <tr
                  key={p.slug}
                  onClick={() => setSelected(p.slug)}
                  aria-selected={isActive}
                  className={`cursor-pointer border-b border-[#eef1f5] text-[12.5px] transition ${
                    isActive ? 'bg-[#e4f2fb] shadow-[inset_2px_0_0_#0077bf]' : 'hover:bg-[#f0f6fb]'
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-[#001932]">{p.slug}</td>
                  <td className="px-3 py-2">
                    <StatusPill status={status} />
                  </td>
                  <td className={`px-3 py-2 text-right font-mono tabular-nums ${cov(p, threshold)}`}>
                    {p.ok ? `${p.contentCoverage ?? 0}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-[#3d556c]">
                    {p.ok ? `${p.pixelSimilarity ?? 0}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-[#3d556c]">{p.ok ? (p.nComps ?? 0) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="border-t border-[#dae0e7] px-3 py-1.5 text-[10.5px] text-[#7d8a9a]">
          content = % of visible text captured by components (gate, threshold {threshold}%) · pixel = components-only
          render vs source (100 − pixel = template/asset job)
        </div>
      </div>

      {/* selected page detail: big artifact buttons + side-by-side comparison */}
      {active && <PageDetail runId={runId} page={active} />}
    </div>
  )
}

/** score for default-selection ranking: failures first, then lowest coverage. */
function score(p: ReconstructPage): number {
  if (!p.ok) return -1000
  if (!p.pass) return (p.contentCoverage ?? 0) - 500
  return p.contentCoverage ?? 0
}

function cov(p: ReconstructPage, threshold: number): string {
  if (!p.ok) return 'text-[#bd2a33]'
  return (p.contentCoverage ?? 0) >= threshold ? 'text-[#12b08a]' : 'text-[#ab6000] font-bold'
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === 'PASS'
      ? 'border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]'
      : status === 'FAILED'
        ? 'border-[#e6b4b4] bg-[#f7e2e2] text-[#bd2a33]'
        : 'border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]'
  return <span className={`rounded px-2 py-0.5 text-[10px] font-extrabold tracking-wide border ${cls}`}>{status}</span>
}

function PageDetail({ runId, page }: { runId: string; page: ReconstructPage }) {
  if (!page.ok) {
    return (
      <div className="bg-white p-5 shadow-sm" style={NOTCH}>
        <div className="font-mono text-[13px] font-bold">{page.slug}</div>
        <div className="mt-2 font-mono text-xs text-[#bd2a33]">FAILED — {page.error}</div>
      </div>
    )
  }

  const reconLocal = page.local && page.reconHtml
  const buttons: { href: string; label: string; strong?: boolean }[] = [
    { href: artifactUrl(runId, `reconstruct/${page.slug}.source.png`), label: 'source ↗' },
    { href: artifactUrl(runId, `reconstruct/${page.slug}.recon.png`), label: 'reconstruction ↗' },
    { href: artifactUrl(runId, `reconstruct/${page.slug}.overlay.html`), label: '🗺 carte composants ↗' },
    ...(page.mirrorPage ? [{ href: artifactUrl(runId, page.mirrorPage), label: '▶ page locale ↗', strong: true }] : []),
    {
      href: artifactUrl(runId, reconLocal ? page.reconHtml! : `reconstruct/${page.slug}.recon.html`),
      label: `▶ reconstruction${reconLocal ? ' locale' : ''} ↗`,
      strong: true,
    },
  ]

  const real = (page.orphanSamples ?? []).filter((o) => !o.ignorable)
  const ignorable = (page.orphanSamples ?? []).filter((o) => o.ignorable)

  return (
    <div className="overflow-hidden bg-white shadow-sm" style={NOTCH}>
      {/* detail header: page + metrics + BIG artifact buttons */}
      <div className="border-b border-[#dae0e7] px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[13.5px] font-bold">{page.slug}</span>
          <StatusPill status={page.pass ? 'PASS' : 'REVIEW'} />
          <div className="ml-auto flex items-center gap-5 font-mono tabular-nums">
            <Metric v={`${page.contentCoverage ?? 0}%`} l="content" cls="text-[#12b08a]" />
            <Metric v={`${page.pixelSimilarity ?? 0}%`} l="pixel" cls="text-[#d6217d]" />
            <Metric v={String(page.nComps ?? 0)} l="components" />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {buttons.map((b) => (
            <a
              key={b.label}
              href={b.href}
              target="_blank"
              rel="noreferrer"
              className={`rounded-md border px-4 py-2.5 text-[13px] font-bold tracking-tight transition ${
                b.strong
                  ? 'border-[#0077bf] bg-[#0077bf] text-white hover:bg-[#025a91]'
                  : 'border-[#bcdcef] bg-[#e4f2fb] text-[#0077bf] hover:border-[#0077bf]'
              }`}
            >
              {b.label}
            </a>
          ))}
        </div>
      </div>

      <BeforeAfterSlider
        before={artifactUrl(runId, `reconstruct/${page.slug}.source.png`)}
        after={artifactUrl(runId, `reconstruct/${page.slug}.recon.png`)}
      />

      <div className="flex flex-wrap gap-1.5 px-4 py-3">
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
        {ignorable.slice(0, 3).map((o, i) => (
          <span key={`i${i}`} className="rounded-full border border-[#c7d0da] px-2 py-0.5 font-mono text-[10px] text-[#7d8a9a] opacity-70">
            {o.text.slice(0, 22)} · ignorable
          </span>
        ))}
      </div>

      <p className="border-t border-[#dae0e7] px-4 py-2.5 text-[11.5px] text-[#3d556c]">
        Pink = pixels the components don’t reproduce (section backgrounds &amp; hero imagery). That layer is the{' '}
        <b className="text-[#001932]">template + asset-import</b>’s job — quantified here so those steps get a spec.
      </p>
    </div>
  )
}

function Metric({ v, l, cls = 'text-[#001932]' }: { v: string; l: string; cls?: string }) {
  return (
    <div className="text-right">
      <div className={`text-[15px] font-bold ${cls}`}>{v}</div>
      <div className="text-[9px] uppercase tracking-wide text-[#7d8a9a]">{l}</div>
    </div>
  )
}
