import { GateActions, GateHeader, EmptyArtifact, NOTCH } from './GateShell'
import { useJsonArtifact } from './useArtifact'

interface Section {
  type: string
  [k: string]: unknown
}
interface ContentPage {
  page: string
  url: string
  pageType?: string
  sections?: Section[]
}

/** Content & publish gate — review the content extracted/created for the Jahia
 * site before it goes live. gate_type === 'content'. */
export function ContentGate({ runId, onApproved, readOnly }: { runId: string; onApproved?: () => void; readOnly?: boolean }) {
  const { data, status } = useJsonArtifact<ContentPage[]>(runId, 'content-data.json')
  const pages = Array.isArray(data) ? data : []

  const sectionCounts = new Map<string, number>()
  let totalSections = 0
  for (const p of pages)
    for (const s of p.sections ?? []) {
      sectionCounts.set(s.type, (sectionCounts.get(s.type) ?? 0) + 1)
      totalSections++
    }
  const histogram = [...sectionCounts.entries()].sort((a, b) => b[1] - a[1])

  return (
    <div className="text-[#001932]">
      <GateHeader
        icon="📝"
        title="Content & publish — review before go-live"
        subtitle="Content mapped onto the component model, page by page. Approving publishes to the live workspace. Reference-vs-Jahia screenshots appear here once the content step captures them."
        tone="info"
        badge={pages.length ? `${pages.length} pages` : undefined}
        actions={readOnly ? undefined : <GateActions runId={runId} onApproved={onApproved} approveLabel="Approve & publish" />}
      />

      {status === 'missing' && <EmptyArtifact label="No content-data.json yet — this gate populates once the content step runs." />}

      {pages.length > 0 && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Stat v={String(pages.length)} l="pages" />
            <Stat v={String(totalSections)} l="sections" accent />
            <Stat v={String(histogram.length)} l="section types" accent />
          </div>

          <Section title="Section types">
            <div className="flex flex-wrap gap-2">
              {histogram.map(([type, n]) => (
                <span key={type} className="rounded-md border border-[#dae0e7] bg-white px-2.5 py-1 font-mono text-xs">
                  <b className="text-[#001932]">{type}</b> <span className="text-[#7d8a9a]">· {n}</span>
                </span>
              ))}
            </div>
          </Section>

          <Section title={`Pages (${pages.length})`}>
            <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
              {pages.map((p, i) => (
                <div key={i} className="border border-[#dae0e7] bg-white px-3 py-2.5" style={NOTCH}>
                  <div className="flex items-center justify-between">
                    <span className="truncate font-semibold text-[13px] text-[#001932]">{p.page}</span>
                    {p.pageType && (
                      <span className="ml-2 flex-none rounded border border-[#bcdcef] bg-[#e4f2fb] px-1.5 font-mono text-[10px] text-[#0077bf]">
                        {p.pageType}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[11px] text-[#7d8a9a]">{p.url}</div>
                  <div className="mt-1 text-[11px] text-[#9aa6b4]">{(p.sections ?? []).length} sections</div>
                </div>
              ))}
            </div>
          </Section>
        </>
      )}
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
