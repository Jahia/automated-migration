import { useEffect, useState, type ReactNode } from 'react'
import { artifactUrl } from '../fidelity/api'
import type { ComponentManifest, ComponentType } from './types'

const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%)' } as const

/** Renders component-manifest.json: types, views, layout props, containers, cross-cutting, templates. */
export function ComponentModelView({ runId }: { runId: string }) {
  const [m, setM] = useState<ComponentManifest | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetch(artifactUrl(runId, 'component-manifest.json'))
      .then((r) => {
        if (!r.ok) throw new Error(`manifest unavailable (${r.status})`)
        return r.json()
      })
      .then(setM)
      .catch((e) => setErr(String(e.message ?? e)))
  }, [runId])

  if (err) return <div className="p-6 font-mono text-sm text-[#bd2a33]">{err}</div>
  if (!m) return <div className="p-6 text-[#7d8a9a]">Loading component model…</div>

  return (
    <div className="text-[#001932]">
      <div className="mb-4 grid grid-cols-3 gap-px overflow-hidden bg-[#dae0e7]" style={NOTCH}>
        <Stat v={m.components.length} l="content types" />
        <Stat v={m.templates.length} l="templates" />
        <Stat v={m.crossCutting.length} l="cross-cutting" accent />
      </div>

      <Section title="Cross-cutting · AbsoluteArea">
        <div className="flex flex-wrap gap-2">
          {m.crossCutting.map((c) => (
            <span key={c.nodeType} className="rounded-md border border-[#bcdcef] bg-[#e4f2fb] px-2.5 py-1 font-mono text-xs text-[#0077bf]">
              {c.nodeType} <span className="text-[#7d8a9a]">· {c.area}</span>
            </span>
          ))}
        </div>
      </Section>

      <Section title={`Content types (${m.components.length})`}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-[12px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wide text-[#7d8a9a]">
                <th className="py-1.5 pr-3 font-semibold">nodeType</th>
                <th className="py-1.5 pr-3 font-semibold">fields</th>
                <th className="py-1.5 pr-3 font-semibold">views</th>
                <th className="py-1.5 pr-3 font-semibold">traits</th>
                <th className="py-1.5 font-semibold">covers</th>
              </tr>
            </thead>
            <tbody>
              {m.components.map((c) => (
                <TypeRow key={c.nodeType} c={c} />
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={`Templates (${m.templates.length})`}>
        <div className="flex flex-wrap gap-2">
          {m.templates.map((t, i) => (
            <span key={i} className="rounded-md border border-[#dae0e7] bg-[#f6f9fb] px-2.5 py-1 text-xs">
              <b className="text-[#001932]">{t.name ?? t.kind}</b>{' '}
              <span className="text-[#7d8a9a]">
                · {t.kind} · {t.pages.length} pages
              </span>
            </span>
          ))}
        </div>
      </Section>
    </div>
  )
}

function TypeRow({ c }: { c: ComponentType }) {
  const traits: { label: string; cls: string }[] = []
  if (c.isContainer) traits.push({ label: 'container', cls: 'border-[#a9dcf4] bg-[#e6f5fd] text-[#0784ba]' })
  if (c.needsMainResource) traits.push({ label: 'mainResource', cls: 'border-[#b4e6d7] bg-[#e2f5ef] text-[#12b08a]' })
  if (c.layoutProperty) traits.push({ label: `layout:${c.layoutProperty.name}`, cls: 'border-[#f3b9d8] bg-[#fbe7f1] text-[#d6217d]' })
  if (c.childType) traits.push({ label: `↳ ${c.childType.nodeType.split(':').pop()}`, cls: 'border-[#c7d0da] bg-[#f6f9fb] text-[#3d556c]' })
  return (
    <tr className="border-t border-[#eef2f6]">
      <td className="py-1.5 pr-3 text-[#0077bf]">{c.nodeType}</td>
      <td className="py-1.5 pr-3 text-[#3d556c]">{c.fields?.length ?? 0}</td>
      <td className="py-1.5 pr-3 text-[#3d556c]">{c.views?.length ?? 1}</td>
      <td className="py-1.5 pr-3">
        <span className="flex flex-wrap gap-1">
          {traits.map((t) => (
            <span key={t.label} className={`rounded border px-1.5 text-[10px] ${t.cls}`}>
              {t.label}
            </span>
          ))}
        </span>
      </td>
      <td className="py-1.5 text-[11px] text-[#9aa6b4]">{(c.coversRoles ?? []).join(', ')}</td>
    </tr>
  )
}

function Stat({ v, l, accent }: { v: number; l: string; accent?: boolean }) {
  return (
    <div className="bg-[#f6f9fb] px-3 py-3">
      <div className={`font-mono text-xl font-bold ${accent ? 'text-[#0077bf]' : 'text-[#001932]'}`}>{v}</div>
      <div className="mt-0.5 text-[9.5px] uppercase tracking-wide text-[#7d8a9a]">{l}</div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="mb-2 text-[11px] font-bold uppercase tracking-[1.2px] text-[#7d8a9a]">{title}</h3>
      {children}
    </section>
  )
}
