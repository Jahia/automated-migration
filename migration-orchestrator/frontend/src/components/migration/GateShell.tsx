import { useState, type ReactNode } from 'react'
import { pauseRun, resumeRun } from '../../api'

export const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%)' } as const

export type GateTone = 'ok' | 'review' | 'info'

const TONE: Record<GateTone, string> = {
  ok: 'border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]',
  review: 'border-[#f0d9a8] bg-[#fbf0da] text-[#ab6000]',
  info: 'border-[#bcdcef] bg-[#e4f2fb] text-[#0077bf]',
}

export function GateHeader({
  icon = '◆',
  title,
  subtitle,
  tone = 'info',
  badge,
  actions,
}: {
  icon?: string
  title: string
  subtitle?: ReactNode
  tone?: GateTone
  badge?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start gap-4 bg-white p-5 shadow-sm" style={NOTCH}>
      <div className="grid h-10 w-10 flex-none place-items-center rounded-xl border border-[#bcdcef] bg-[#e4f2fb] text-lg text-[#0077bf]">
        {icon}
      </div>
      <div className="min-w-0">
        <h1 className="text-[17px] font-bold tracking-tight text-[#001932]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-[64ch] text-[12.5px] text-[#3d556c]">{subtitle}</p>}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {badge && (
          <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-extrabold uppercase tracking-wide ${TONE[tone]}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
            {badge}
          </span>
        )}
        {actions}
      </div>
    </div>
  )
}

/**
 * Approve / Hold controls for a HALT gate. Approve → POST /resume (the engine
 * forces the halted step to done); Hold → POST /pause. Shared by scope/content/
 * go-live gates (the fidelity gate keeps its own richer action row).
 */
export function GateActions({ runId, onApproved, approveLabel = 'Approve & continue' }: { runId: string; onApproved?: () => void; approveLabel?: string }) {
  const [busy, setBusy] = useState(false)
  const approve = async () => {
    setBusy(true)
    try {
      await resumeRun(runId)
      onApproved?.()
    } finally {
      setBusy(false)
    }
  }
  const hold = async () => {
    setBusy(true)
    try {
      await pauseRun(runId)
      onApproved?.()
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button
        onClick={hold}
        disabled={busy}
        className="rounded-md border border-[#c7d0da] bg-white px-3.5 py-2 text-[11.5px] font-bold uppercase tracking-wide hover:border-[#bd2a33] hover:text-[#bd2a33] disabled:opacity-60"
      >
        Hold
      </button>
      <button
        onClick={approve}
        disabled={busy}
        className="rounded-md border border-[#0077bf] bg-[#0077bf] px-3.5 py-2 text-[11.5px] font-bold uppercase tracking-wide text-white hover:bg-[#025a91] disabled:opacity-60"
      >
        {approveLabel} <span className="ml-2 border-l border-white/60 pl-2 font-normal opacity-70">›</span>
      </button>
    </>
  )
}

export function EmptyArtifact({ label }: { label: string }) {
  return (
    <div className="border border-dashed border-[#c7d0da] bg-white/60 px-4 py-8 text-center text-[13px] text-[#7d8a9a]" style={NOTCH}>
      {label}
    </div>
  )
}
