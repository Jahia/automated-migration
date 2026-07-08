import { GateActions, GateHeader, NOTCH } from './GateShell'
import { useJsonArtifact } from './useArtifact'
import { artifactUrl } from '../fidelity/api'
import { ArtifactProvenanceLine, useProjectArtifacts } from './ArtifactProvenance'

interface MirrorPage {
  slug: string
  offlineRendered?: boolean
  styleSheets?: number
  cssRules?: number
  localImages?: number
  externalBlocked?: number
  realMiss?: string[]
  realMissCount?: number
  localMiss?: string[]
  localMissCount?: number
  ignorableBlocked?: number
  runtimeRepaired?: number
  runtimeResidue?: number
  mirrorFidelity?: number
  ok?: boolean
  error?: string
}
interface MirrorCheck {
  project?: string
  gatePass?: boolean
  pages: MirrorPage[]
}
interface MirrorJson {
  pages?: { slug: string }[]
  assets?: { total?: number; localized?: number; bytes?: number; localizablePct?: number }
  residue?: string[]
}

/** Local-mirror gate — the offline render check that runs BEFORE the global
 * fidelity gate. GREEN = every sample page renders with zero external static
 * assets and zero local 404s (runtime-composed URLs are captured by the
 * probe's repair pass). gate_type === 'mirror'. */
export function MirrorGate({
  runId,
  project,
  onApproved,
  readOnly,
}: {
  runId: string
  project?: string | null
  onApproved?: () => void
  readOnly?: boolean
}) {
  const check = useJsonArtifact<MirrorCheck>(runId, 'mirror/mirror-check.json')
  const mirror = useJsonArtifact<MirrorJson>(runId, 'local-mirror/mirror.json')
  const { byId: artifacts } = useProjectArtifacts(project)

  const pages = check.data?.pages ?? []
  const gatePass = !!check.data?.gatePass
  const misses = pages.reduce((s, p) => s + (p.realMissCount ?? 0) + (p.localMissCount ?? 0), 0)
  const repaired = pages.reduce((s, p) => s + (p.runtimeRepaired ?? 0), 0)
  const fids = pages.map((p) => p.mirrorFidelity).filter((f): f is number => f != null)
  const assets = mirror.data?.assets

  return (
    <div className="text-[#001932]">
      <GateHeader
        icon="🪞"
        title="Local mirror — offline render gate"
        subtitle={
          <>
            The crawl is localized into a self-contained mirror, then each sample page is rendered with every external
            origin blocked. Runtime-composed URLs (JS loaders, chunk maps) are captured once by the repair pass and
            served offline afterwards. Approving hands a deterministic, WAF-free render source to the fidelity gate.
          </>
        }
        tone={check.status === 'ok' ? (gatePass ? 'ok' : 'review') : 'info'}
        badge={check.status === 'ok' ? (gatePass ? 'GREEN — truly local' : `RED — ${misses} miss`) : undefined}
        actions={readOnly ? undefined : <GateActions runId={runId} onApproved={onApproved} approveLabel="Approve mirror" />}
      />

      <div className="mb-3 space-y-1">
        <ArtifactProvenanceLine label="local-mirror/mirror.json" entry={artifacts['local-mirror']} />
        <ArtifactProvenanceLine label="mirror/mirror-check.json" entry={artifacts['mirror-check']} />
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat v={mirror.data?.pages ? String(mirror.data.pages.length) : '—'} l="pages mirrored" />
        <Stat
          v={assets?.localizablePct != null ? `${assets.localizablePct}%` : '—'}
          l={`assets localized${assets?.total ? ` · ${assets.localized}/${assets.total}` : ''}`}
        />
        <Stat v={repaired ? String(repaired) : '0'} l="runtime-repaired" accent />
        <Stat v={fids.length ? `${Math.min(...fids)}%` : '—'} l="worst mirror-fidelity vs live" accent />
      </div>

      <div className="mb-4 overflow-x-auto bg-white p-4 shadow-sm" style={NOTCH}>
        <table className="w-full border-collapse font-mono text-[12px]">
          <thead>
            <tr className="border-b border-[#dae0e7] text-left text-[11px] uppercase tracking-wide text-[#7d8a9a]">
              <th className="py-1.5 pr-3">page</th>
              <th className="py-1.5 pr-3">offline</th>
              <th className="py-1.5 pr-3">ext miss</th>
              <th className="py-1.5 pr-3">local 404</th>
              <th className="py-1.5 pr-3">repaired</th>
              <th className="py-1.5 pr-3">fidelity</th>
            </tr>
          </thead>
          <tbody>
            {pages.length === 0 && (
              <tr>
                <td colSpan={6} className="py-3 text-[#7d8a9a]">
                  {check.status === 'loading' ? 'Loading mirror-check…' : 'No mirror-check.json yet — the localize step has not probed the mirror.'}
                </td>
              </tr>
            )}
            {pages.map((p) => {
              const bad = !p.offlineRendered || (p.realMissCount ?? 0) > 0 || (p.localMissCount ?? 0) > 0
              return (
                <tr key={p.slug} className="border-b border-[#eef1f5]">
                  <td className="py-1.5 pr-3 font-bold">{p.slug}</td>
                  <td className={`py-1.5 pr-3 ${p.offlineRendered ? 'text-[#12b08a]' : 'text-[#d64545]'}`}>
                    {p.offlineRendered ? '✓' : '✗'}
                  </td>
                  <td className={`py-1.5 pr-3 ${(p.realMissCount ?? 0) > 0 ? 'text-[#d64545] font-bold' : ''}`}>{p.realMissCount ?? 0}</td>
                  <td className={`py-1.5 pr-3 ${(p.localMissCount ?? 0) > 0 ? 'text-[#d64545] font-bold' : ''}`}>{p.localMissCount ?? 0}</td>
                  <td className="py-1.5 pr-3">{p.runtimeRepaired ?? 0}</td>
                  <td className={`py-1.5 pr-3 ${bad ? '' : 'text-[#12b08a]'}`}>{p.mirrorFidelity != null ? `${p.mirrorFidelity}%` : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="mt-3 flex flex-wrap gap-4 text-[12px]">
          <a
            href={artifactUrl(runId, 'mirror/mirror-review.html')}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-[#0077bf] hover:underline"
          >
            ▶ Revue visuelle local ↔ live (slider) ↗
          </a>
          {(mirror.data?.residue?.length ?? 0) > 0 && (
            <span className="text-[#7d8a9a]">{mirror.data!.residue!.length} download residue (404 on source / oversize)</span>
          )}
        </div>
      </div>

      {misses > 0 && (
        <div className="bg-white p-4 shadow-sm" style={NOTCH}>
          <div className="mb-2 text-[12px] font-bold uppercase tracking-wide text-[#ab6000]">Still missing offline</div>
          <ul className="max-h-56 space-y-1 overflow-y-auto font-mono text-[11.5px] text-[#3d556c]">
            {pages.flatMap((p) => [...(p.realMiss ?? []), ...(p.localMiss ?? [])].map((u, i) => (
              <li key={`${p.slug}-${i}`} className="break-all">
                <span className="text-[#7d8a9a]">{p.slug}:</span> {u}
              </li>
            )))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Stat({ v, l, accent }: { v: string; l: string; accent?: boolean }) {
  return (
    <div className="border border-[#dae0e7] bg-white px-3 py-2.5" style={NOTCH}>
      <div className={`text-[19px] font-extrabold tracking-tight ${accent ? 'text-[#0077bf]' : 'text-[#001932]'}`}>{v}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-[#7d8a9a]">{l}</div>
    </div>
  )
}
