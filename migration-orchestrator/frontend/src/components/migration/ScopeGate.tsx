import { useState } from 'react'
import { GateActions, GateHeader, NOTCH } from './GateShell'
import { useJsonArtifact } from './useArtifact'

interface InvPage {
  url: string
  slug: string
  title?: string
  httpStatus?: number
  contentLength?: number
}
interface PageInventory {
  siteUrl?: string
  totalPages?: number
  assetsDownloaded?: number
  assetsBytes?: number
  pages: InvPage[]
}
interface Candidate {
  candidateId: string
  role: string
  frequency?: number
  pageCount?: number
}
interface Candidates {
  sxaMode?: boolean
  numPages?: number
  totalInstances?: number
  crossCutting: Candidate[]
  components: Candidate[]
  nestedParts?: Candidate[]
}
interface TemplateCluster {
  clusterId: string
  pageCount: number
  pages: string[]
  mainRolesRepresentative?: string[]
}
interface Templates {
  crossCuttingRoles?: string[]
  clusters: TemplateCluster[]
}

/** Scope & capture gate — approve WHAT was extracted (pages + candidates + template
 * clusters) before the LLM builds the component model. gate_type === 'scope'. */
export function ScopeGate({ runId, onApproved }: { runId: string; onApproved?: () => void }) {
  const inv = useJsonArtifact<PageInventory>(runId, 'page-inventory.json')
  const cand = useJsonArtifact<Candidates>(runId, 'semantic-candidates.json')
  const tpl = useJsonArtifact<Templates>(runId, 'semantic-templates.json')
  const [showPages, setShowPages] = useState(false)

  const pages = inv.data?.pages ?? []
  const nCand = (cand.data?.components.length ?? 0) + (cand.data?.crossCutting.length ?? 0)
  const clusters = tpl.data?.clusters ?? []
  const xcut = cand.data?.crossCutting ?? []

  const fmtBytes = (b?: number) => (b ? `${(b / 1e6).toFixed(1)} MB` : '—')

  return (
    <div className="text-[#001932]">
      <GateHeader
        icon="🕸"
        title="Scope & capture — approve the extraction before modeling"
        subtitle={
          <>
            What the crawl captured and how pages cluster into templates. Approving hands a stable candidate set to the
            bounded LLM grouping step. {cand.data?.sxaMode ? 'SXA fast-path detected.' : 'Agnostic altitude finder.'}
          </>
        }
        tone="info"
        badge={inv.data ? `${inv.data.totalPages ?? pages.length} pages` : undefined}
        actions={<GateActions runId={runId} onApproved={onApproved} approveLabel="Approve scope" />}
      />

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat v={String(inv.data?.totalPages ?? (pages.length || '—'))} l="pages crawled" />
        <Stat v={String(inv.data?.assetsDownloaded ?? '—')} l={`assets · ${fmtBytes(inv.data?.assetsBytes)}`} />
        <Stat v={String(nCand || '—')} l="candidates" accent />
        <Stat v={String(clusters.length || '—')} l="template clusters" accent />
      </div>

      <Section title={`Cross-cutting roles (${xcut.length})`}>
        <div className="flex flex-wrap gap-2">
          {xcut.length === 0 && <span className="text-[12px] text-[#7d8a9a]">none detected yet</span>}
          {xcut.map((c) => (
            <span key={c.candidateId} className="rounded-md border border-[#bcdcef] bg-[#e4f2fb] px-2.5 py-1 font-mono text-xs text-[#0077bf]">
              {c.role} <span className="text-[#7d8a9a]">· {c.frequency ?? 0}×</span>
            </span>
          ))}
        </div>
      </Section>

      <Section title={`Template clusters (${clusters.length})`}>
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
          {clusters.map((c) => (
            <div key={c.clusterId} className="border border-[#dae0e7] bg-white px-3 py-2.5" style={NOTCH}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12.5px] font-bold text-[#001932]">{c.clusterId}</span>
                <span className="text-[11px] text-[#7d8a9a]">{c.pageCount} pages</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {(c.mainRolesRepresentative ?? []).slice(0, 4).map((r, i) => (
                  <span key={i} className="rounded border border-[#c7d0da] bg-[#f6f9fb] px-1.5 font-mono text-[10px] text-[#3d556c]">
                    {r}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title={`Pages (${pages.length})`}>
        <button onClick={() => setShowPages((s) => !s)} className="mb-2 text-[12px] font-semibold text-[#0077bf] hover:underline">
          {showPages ? 'Hide' : 'Show'} page list
        </button>
        {showPages && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-[12px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-[#7d8a9a]">
                  <th className="py-1.5 pr-3 font-semibold">slug</th>
                  <th className="py-1.5 pr-3 font-semibold">title</th>
                  <th className="py-1.5 font-semibold">status</th>
                </tr>
              </thead>
              <tbody>
                {pages.map((p) => (
                  <tr key={p.slug} className="border-t border-[#eef2f6]">
                    <td className="py-1.5 pr-3 text-[#0077bf]">{p.slug}</td>
                    <td className="py-1.5 pr-3 text-[#3d556c]">{(p.title ?? '').slice(0, 60)}</td>
                    <td className={`py-1.5 ${p.httpStatus === 200 ? 'text-[#12b08a]' : 'text-[#ab6000]'}`}>{p.httpStatus ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  )
}

function Stat({ v, l, accent }: { v: string; l: string; accent?: boolean }) {
  return (
    <div className="border border-[#dae0e7] bg-white px-3 py-2.5" style={NOTCH}>
      <div className={`font-mono text-[20px] font-bold leading-none tabular-nums ${accent ? 'text-[#0077bf]' : 'text-[#001932]'}`}>{v}</div>
      <div className="mt-1 text-[9.5px] font-semibold uppercase tracking-[0.8px] text-[#7d8a9a]">{l}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="mb-2 text-[11px] font-bold uppercase tracking-[1.2px] text-[#7d8a9a]">{title}</h3>
      {children}
    </section>
  )
}
