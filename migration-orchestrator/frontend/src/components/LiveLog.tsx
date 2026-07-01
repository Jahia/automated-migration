import { useEffect, useRef, useState } from 'react'
import type { RunState, StepState } from '../types'

/** The step whose chat we show: the one currently running/verifying, else the
 *  most recent step that produced any output. */
function activeStep(run: RunState): StepState | undefined {
  const steps = run.epics.flatMap((e) => e.stories).flatMap((s) => s.steps)
  return (
    steps.find((s) => s.status === 'running' || s.status === 'verifying') ||
    [...steps].reverse().find((s) => s.streaming_text || s.agent_result)
  )
}

const REASON = '\u{1f9e0}' // 🧠 — backend prefixes reasoning lines with this

/** Persistent live LLM chat/log window for the run. Shows the active step's
 *  streaming output as it executes — including the model's *reasoning* (dimmed),
 *  so a reasoning-only turn that produces no final text is still visible. */
export default function LiveLog({ run }: { run: RunState }) {
  const [open, setOpen] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const step = activeStep(run)
  const live = step?.status === 'running' || step?.status === 'verifying'
  const text = step?.streaming_text || step?.agent_result?.summary || ''

  useEffect(() => {
    if (open && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [text, open])

  const lines = text ? text.split('\n') : []

  return (
    <div className="mb-4 border border-gray-800 rounded-lg bg-gray-950">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-900/50 transition"
      >
        <span className="text-gray-500 text-xs font-mono">{open ? '▼' : '▶'}</span>
        <span className="text-sm font-semibold">LLM Log</span>
        {step && (
          <span className="text-xs text-gray-500 font-mono">
            {step.id} · {step.task_type}@{step.agent}
            {step.tokens_out ? ` · ${step.tokens_out} tok out` : ''}
          </span>
        )}
        {live && <span className="ml-auto w-2 h-2 rounded-full bg-blue-500 animate-pulse" />}
      </button>

      {open && (
        <div ref={scrollRef} className="max-h-80 overflow-y-auto px-3 pb-3 font-mono text-xs leading-relaxed">
          {lines.length > 0 ? (
            lines.map((ln, i) =>
              ln.startsWith(REASON) ? (
                <div key={i} className="text-gray-500 italic whitespace-pre-wrap">
                  {ln}
                </div>
              ) : (
                <div key={i} className="text-gray-200 whitespace-pre-wrap">
                  {ln || ' '}
                </div>
              ),
            )
          ) : (
            <div className="text-gray-600">{live ? 'En attente de la sortie du LLM…' : 'Aucune sortie pour le moment'}</div>
          )}
          {live && <span className="animate-pulse text-blue-400">▌</span>}
        </div>
      )}
    </div>
  )
}
