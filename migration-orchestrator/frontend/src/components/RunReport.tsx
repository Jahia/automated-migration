import { useState } from 'react'
import type { RunState } from '../types'

/** End-of-run report aggregated from the persisted run state (works on recall):
 *  risks flagged during each story, the steps that failed/halted, and token/cost
 *  totals. The data already lives on each step's agent_result — this consolidates it. */
export default function RunReport({ run }: { run: RunState }) {
  const terminal = ['completed', 'failed', 'aborted'].includes(run.status)
  const [open, setOpen] = useState(terminal)

  // Aggregate
  let tokensOut = 0
  let cost = 0
  let stepsDone = 0
  let stepsTotal = 0
  let storiesApproved = 0
  let storiesTotal = 0
  const risks: { epic: string; story: string; step: string; risk: string }[] = []
  const issues: { epic: string; story: string; step: string; status: string; detail: string }[] = []

  for (const e of run.epics) {
    for (const s of e.stories) {
      storiesTotal++
      if (s.status === 'approved') storiesApproved++
      for (const st of s.steps) {
        stepsTotal++
        if (st.status === 'done') stepsDone++
        tokensOut += st.tokens_out || 0
        cost += st.cost || 0
        for (const r of st.agent_result?.risks || []) {
          risks.push({ epic: e.title, story: s.title, step: st.id, risk: r })
        }
        if (['failed', 'halted', 'blocked'].includes(st.status)) {
          const detail = st.verification?.errors?.join('; ') || st.agent_result?.summary?.slice(0, 160) || ''
          issues.push({ epic: e.title, story: s.title, step: st.id, status: st.status, detail })
        }
      }
    }
  }

  // group risks by epic -> story
  const byStory = new Map<string, { epic: string; story: string; items: string[] }>()
  for (const r of risks) {
    const key = `${r.epic}␟${r.story}`
    if (!byStory.has(key)) byStory.set(key, { epic: r.epic, story: r.story, items: [] })
    byStory.get(key)!.items.push(`${r.risk}  (${r.step})`)
  }

  return (
    <div className="mb-4 border border-gray-800 rounded-lg bg-gray-950">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-900/50 transition"
      >
        <span className="text-gray-500 text-xs font-mono">{open ? '▼' : '▶'}</span>
        <span className="text-sm font-semibold">Run Report</span>
        <span className="text-xs text-gray-500">
          {storiesApproved}/{storiesTotal} stories · {stepsDone}/{stepsTotal} steps · {risks.length} risk(s)
          {issues.length ? ` · ${issues.length} issue(s)` : ''}
        </span>
        <span className="ml-auto text-xs text-gray-600 font-mono">
          {tokensOut.toLocaleString()} tok · ${cost.toFixed(4)}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 text-xs">
          {/* Risks grouped by story */}
          <div className="mt-2 font-semibold text-gray-300">Risks flagged during the run</div>
          {byStory.size === 0 ? (
            <div className="text-gray-600 mt-1">No risks were flagged.</div>
          ) : (
            [...byStory.values()].map((g, i) => (
              <div key={i} className="mt-2">
                <div className="text-gray-400">
                  {g.epic} <span className="text-gray-600">›</span> {g.story}
                </div>
                <ul className="list-disc list-inside text-yellow-600/90 ml-2">
                  {g.items.map((it, j) => (
                    <li key={j}>{it}</li>
                  ))}
                </ul>
              </div>
            ))
          )}

          {/* Issues: failed / halted / blocked steps */}
          {issues.length > 0 && (
            <>
              <div className="mt-4 font-semibold text-gray-300">Unresolved steps</div>
              <ul className="mt-1 space-y-1">
                {issues.map((it, i) => (
                  <li key={i} className="text-red-400">
                    <span className="font-mono">{it.step}</span> [{it.status}]
                    {it.detail && <span className="text-gray-500"> — {it.detail}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
