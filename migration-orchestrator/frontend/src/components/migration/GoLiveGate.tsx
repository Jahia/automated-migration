import { GateActions, GateHeader, EmptyArtifact, NOTCH } from './GateShell'
import { useTextArtifact } from './useArtifact'

/** Go-live gate — visual-diff summary + vanity redirect map, the final review
 * before the migrated site is published. gate_type === 'golive'. */
export function GoLiveGate({ runId, onApproved }: { runId: string; onApproved?: () => void }) {
  const summary = useTextArtifact(runId, 'visual-diff/SUMMARY.md')
  const redirects = useTextArtifact(runId, 'vanity/redirects.map')

  const redirectLines = (redirects.text ?? '')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'))

  return (
    <div className="text-[#001932]">
      <GateHeader
        icon="🚀"
        title="Go-live — visual diff & redirects"
        subtitle="Final review: how the migrated site compares to the source, and the vanity URLs that will redirect old paths. Approving publishes."
        tone="info"
        badge={redirectLines.length ? `${redirectLines.length} redirects` : undefined}
        actions={<GateActions runId={runId} onApproved={onApproved} approveLabel="Publish · go live" />}
      />

      <Section title="Visual-diff summary">
        {summary.status === 'missing' && <EmptyArtifact label="No visual-diff/SUMMARY.md yet." />}
        {summary.text && (
          <pre className="overflow-x-auto whitespace-pre-wrap border border-[#dae0e7] bg-white p-4 text-[12.5px] leading-relaxed text-[#001932]" style={NOTCH}>
            {summary.text}
          </pre>
        )}
      </Section>

      <Section title={`Redirect map (${redirectLines.length})`}>
        {redirects.status === 'missing' && <EmptyArtifact label="No vanity/redirects.map yet." />}
        {redirectLines.length > 0 && (
          <div className="overflow-x-auto border border-[#dae0e7] bg-white" style={NOTCH}>
            <table className="w-full border-collapse font-mono text-[12px]">
              <tbody>
                {redirectLines.slice(0, 200).map((l, i) => {
                  const [from, ...rest] = l.split(/\s+/)
                  const to = rest.join(' ').replace(/;$/, '')
                  return (
                    <tr key={i} className="border-t border-[#eef2f6] first:border-0">
                      <td className="py-1.5 pl-3 pr-3 text-[#3d556c]">{from}</td>
                      <td className="py-1.5 pr-2 text-[#9aa6b4]">→</td>
                      <td className="py-1.5 pr-3 text-[#0077bf]">{to}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {redirectLines.length > 200 && (
              <div className="border-t border-[#eef2f6] px-3 py-2 text-[11px] text-[#7d8a9a]">
                +{redirectLines.length - 200} more…
              </div>
            )}
          </div>
        )}
      </Section>
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
