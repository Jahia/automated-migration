import { useEffect, useState } from 'react'
import { fetchZoningProjects, fetchZoningPages, applyZoning, type ZoningPage } from '../api'

/**
 * Zoning — the manual zoning inspector, embedded in the cockpit.
 *
 * Pick a project + a page; the inspector page (served by src/routes/manual.py at
 * /projects/{p}/zoning/mirror/<slug>.manual.html) renders in an <iframe> — reusing the
 * vanilla-JS inspector as-is. Its decisions persist same-origin to the /zoning API.
 * "Appliquer" re-runs the deterministic engine so those decisions land in the content-load.
 * Read/decision only — never touches Jahia.
 */
export default function Zoning() {
  const [projects, setProjects] = useState<{ project: string; pages: number }[]>([])
  const [project, setProject] = useState<string>('')
  const [pages, setPages] = useState<ZoningPage[]>([])
  const [slug, setSlug] = useState<string>('')
  const [err, setErr] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyMsg, setApplyMsg] = useState<string | null>(null)
  const [frame, setFrame] = useState(0) // bump to reload the iframe

  useEffect(() => {
    fetchZoningProjects()
      .then((ps) => {
        setProjects(ps)
        if (ps.length && !project) setProject(ps[0].project)
      })
      .catch((e) => setErr(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!project) return
    setErr(null)
    setApplyMsg(null)
    fetchZoningPages(project)
      .then((pg) => {
        setPages(pg)
        setSlug(pg.length ? pg[0].slug : '')
      })
      .catch((e) => setErr(String(e)))
  }, [project])

  async function onApply() {
    setApplying(true)
    setApplyMsg(null)
    try {
      const r = await applyZoning(project)
      setApplyMsg(r.summary || (r.ok ? 'Appliqué (aucune décision).' : 'Échec.'))
      // refresh the page list (decision counts) and reload the iframe
      fetchZoningPages(project).then(setPages).catch(() => {})
      setFrame((f) => f + 1)
    } catch (e) {
      setApplyMsg(`Erreur: ${e}`)
    } finally {
      setApplying(false)
    }
  }

  const totalDecisions = pages.reduce((n, p) => n + p.decisions, 0)
  const sel = 'rounded border border-[#0a3252] bg-[#001932] px-2 py-1 text-sm text-gray-100'

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-white">Zoning manuel</h1>
        <p className="text-sm text-[#a8c1d6]">
          Survole un bloc pour le surligner, clique pour l'inspecter et le décider
          (composant / area / absolute area). Les décisions sont retenues ; «&nbsp;Appliquer&nbsp;»
          relance le moteur pour qu'elles entrent dans le découpage — byte-exact garanti.
        </p>
      </div>

      {err && <div className="rounded bg-red-950 px-3 py-2 text-sm text-red-300">{err}</div>}

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-[#a8c1d6]">
          Projet{' '}
          <select className={sel} value={project} onChange={(e) => setProject(e.target.value)}>
            {projects.length === 0 && <option value="">(aucun local-mirror)</option>}
            {projects.map((p) => (
              <option key={p.project} value={p.project}>
                {p.project} ({p.pages} pages)
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-[#a8c1d6]">
          Page{' '}
          <select className={sel} value={slug} onChange={(e) => setSlug(e.target.value)}>
            {pages.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.slug}
                {p.decisions ? ` · ${p.decisions} décision(s)` : ''}
              </option>
            ))}
          </select>
        </label>

        <span className="text-xs text-[#5e88ad]">
          {totalDecisions} décision(s) sur ce projet
        </span>

        <button
          onClick={onApply}
          disabled={!project || applying}
          className="ml-auto rounded bg-emerald-700 px-3 py-1 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
        >
          {applying ? 'Application…' : 'Appliquer les décisions'}
        </button>
      </div>

      {applyMsg && (
        <div className="rounded bg-[#001932] px-3 py-2 font-mono text-xs text-emerald-300">{applyMsg}</div>
      )}

      {project && slug ? (
        <iframe
          key={`${project}/${slug}#${frame}`}
          title="zoning-inspector"
          src={`/projects/${encodeURIComponent(project)}/zoning/mirror/${encodeURIComponent(slug)}.manual.html`}
          className="h-[80vh] w-full rounded border border-[#0a3252] bg-white"
        />
      ) : (
        <div className="rounded border border-[#0a3252] px-3 py-6 text-center text-sm text-[#5e88ad]">
          Aucune page. Génère-les :{' '}
          <code className="text-[#a8c1d6]">
            python3 orchestration/lib/zone_to_contentload.py &lt;projet&gt; --manual [--overlay-src frozen]
          </code>
        </div>
      )}
    </div>
  )
}
