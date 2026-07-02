import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createMigration, startRun, type MigrationInput } from '../../api'

const NOTCH = { clipPath: 'polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%)' } as const

function hostSlug(url: string): string {
  try {
    const h = new URL(url.startsWith('http') ? url : `https://${url}`).hostname.replace(/^www\./, '')
    return (h.split('.')[0] || '').replace(/[^a-z0-9]+/gi, '-').toLowerCase()
  } catch {
    return ''
  }
}
function nsFromProject(p: string): string {
  const base = p.replace(/[^a-z0-9]/gi, '').toLowerCase()
  return base.slice(0, 4)
}

export default function NewMigration() {
  const nav = useNavigate()
  const [url, setUrl] = useState('')
  const [project, setProject] = useState('')
  const [ns, setNs] = useState('')
  const [mixns, setMixns] = useState('')
  const [maxPages, setMaxPages] = useState(18)
  const [depth, setDepth] = useState(2)
  const [samplePages, setSamplePages] = useState('')
  const [autonomy, setAutonomy] = useState<'manual' | 'assisted' | 'autonomous'>('assisted')
  const [autostart, setAutostart] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Derive project + namespace from the URL host until the operator overrides them.
  const [touchedProject, setTouchedProject] = useState(false)
  const [touchedNs, setTouchedNs] = useState(false)
  const onUrlBlur = () => {
    const slug = hostSlug(url)
    if (slug && !touchedProject && !project) setProject(slug)
    const p = touchedProject ? project : project || slug
    if (p && !touchedNs && !ns) setNs(nsFromProject(p))
  }

  const projectMix = mixns.trim() || (ns ? `${ns}mix` : '')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!url.trim() || !project.trim() || !ns.trim()) {
      setError('URL, projet et namespace sont requis.')
      return
    }
    const payload: MigrationInput = {
      site_url: url.trim(),
      project: project.trim(),
      ns: ns.trim(),
      mixns: mixns.trim() || undefined,
      max_pages: maxPages,
      depth,
      sample_pages: samplePages
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      autonomy,
    }
    setBusy(true)
    try {
      const res = await createMigration(payload)
      if (autostart) {
        try {
          await startRun(res.run_id)
        } catch {
          /* run is created; operator can start it from the cockpit */
        }
      }
      nav(`/runs/${res.run_id}`)
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-5">
        <div className="text-[11px] font-bold uppercase tracking-[2px] text-[#5e88ad]">Migration cockpit</div>
        <h1 className="mt-1 text-2xl font-bold text-white">Nouvelle migration</h1>
        <p className="mt-1 text-sm text-gray-400">
          Analyse déterministe : crawl → extraction de candidats → groupage borné (DeepSeek V4 Flash, gate-vérifié) →
          CND + vues → <span className="text-[#7fd0f5]">gate de fidélité</span> avant templatisation.
        </p>
      </div>

      <form onSubmit={submit} className="bg-white p-6 text-[#001932]" style={NOTCH}>
        <Field label="URL du site" hint="Page d'accueil du site source à migrer.">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={onUrlBlur}
            placeholder="https://www.acquia.com"
            className={inputCls}
            autoFocus
          />
        </Field>

        <div className="mt-4 grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
          <Field label="Projet" hint="Dossier sous projects/ (le module Jahia).">
            <input
              type="text"
              value={project}
              onChange={(e) => {
                setTouchedProject(true)
                setProject(e.target.value)
              }}
              placeholder="acquia-drupal"
              className={inputCls}
            />
          </Field>
          <div className="grid grid-cols-2 items-start gap-3">
            <Field label="Namespace" hint="Préfixe CND (ex. acq).">
              <input
                type="text"
                value={ns}
                onChange={(e) => {
                  setTouchedNs(true)
                  setNs(e.target.value)
                }}
                placeholder="acq"
                className={inputCls}
              />
            </Field>
            <Field label="Mixins" hint={`Défaut : ${projectMix || 'nsmix'}`}>
              <input
                type="text"
                value={mixns}
                onChange={(e) => setMixns(e.target.value)}
                placeholder={projectMix || 'acqmix'}
                className={inputCls}
              />
            </Field>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 items-start gap-4 sm:grid-cols-3">
          <Field label="Pages max" hint="Étendue du crawl.">
            <input
              type="number"
              min={1}
              max={200}
              value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="Profondeur" hint="Niveaux de liens.">
            <input
              type="number"
              min={0}
              max={5}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="Échantillon fidélité" hint="Slugs séparés par des virgules (option).">
            <input
              type="text"
              value={samplePages}
              onChange={(e) => setSamplePages(e.target.value)}
              placeholder="home, about-us, blog"
              className={inputCls}
            />
          </Field>
        </div>

        <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
          <Field label="Autonomie de l'agent" hint="Pilotage LLM des gates de qualité (voir CONTROL-LOOP.md).">
            <select
              value={autonomy}
              onChange={(e) => setAutonomy(e.target.value as typeof autonomy)}
              className={inputCls}
            >
              <option value="manual">Manuel — un humain approuve chaque gate</option>
              <option value="assisted">Assisté — auto si vert, escalade si ambre/rouge</option>
              <option value="autonomous">Autonome — l'agent décide, humain sur échec</option>
            </select>
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm text-[#3d556c]">
            <input type="checkbox" checked={autostart} onChange={(e) => setAutostart(e.target.checked)} className="accent-[#0077bf]" />
            Démarrer l'analyse immédiatement
          </label>
        </div>

        {error && (
          <div className="mt-4 rounded border border-[#f0c2c5] bg-[#fdeaeb] px-3 py-2 text-sm text-[#bd2a33]">{error}</div>
        )}

        <div className="mt-6 flex items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="bg-[#0077bf] px-5 py-2.5 text-[13px] font-bold uppercase tracking-[1px] text-white transition hover:bg-[#0069a8] disabled:opacity-50"
            style={NOTCH}
          >
            {busy ? 'Création…' : 'Créer la migration ›'}
          </button>
          <button type="button" onClick={() => nav('/')} className="text-sm text-[#7d8a9a] hover:text-[#001932]">
            Annuler
          </button>
        </div>
      </form>
    </div>
  )
}

const inputCls =
  'w-full rounded-md border border-[#c7d0da] bg-white px-3 py-2 text-sm text-[#001932] outline-none placeholder:text-[#9aa6b4] focus:border-[#0077bf] focus:ring-2 focus:ring-[#0077bf22]'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.8px] text-[#7d8a9a]">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-[#9aa6b4]">{hint}</span>}
    </label>
  )
}
