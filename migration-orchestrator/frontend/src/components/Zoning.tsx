import { useEffect, useRef, useState } from 'react'
import { fetchZoningProjects, fetchZoningPages, applyZoning, type ZoningPage } from '../api'

/**
 * Zoning — the manual zoning inspector, embedded in the cockpit.
 *
 * Pick a project + a page; the inspector page (served by src/routes/manual.py at
 * /projects/{p}/zoning/mirror/<slug>.manual.html) renders in an <iframe> — reusing the
 * vanilla-JS inspector as-is. Its decisions persist same-origin to the /zoning API.
 * "Appliquer" re-runs the deterministic engine so those decisions land in the content-load.
 *
 * The inspector also postMessages a STRUCTURAL TREE (zones / absolute-areas / components,
 * with ⚠ gaps for code not yet wrapped by a component) which we render as a left panel;
 * clicking a node focuses it in the page. The iframe takes the full remaining width, so the
 * responsive-width control resizes the PAGE only (the tree never eats into it).
 * Read/decision only — never touches Jahia.
 */

type TreeNode = {
  k: 'component' | 'zone' | 'absolute' | 'layout' | 'gap'
  name?: string
  color?: string
  chars?: number
  html?: string
  uid?: number | null
  children?: TreeNode[]
}

const KIND: Record<TreeNode['k'], { icon: string; color: string; label: string }> = {
  component: { icon: '●', color: '#1aa06a', label: 'composant' },
  zone: { icon: '▤', color: '#1f6fd6', label: 'zone' },
  absolute: { icon: '▤', color: '#d33a2c', label: 'absolute area' },
  layout: { icon: '▦', color: '#14b8a6', label: 'layout' },
  gap: { icon: '⚠', color: '#f59e0b', label: 'non assigné' },
}

export default function Zoning() {
  const [projects, setProjects] = useState<{ project: string; pages: number }[]>([])
  const [project, setProject] = useState<string>('')
  const [pages, setPages] = useState<ZoningPage[]>([])
  const [slug, setSlug] = useState<string>('')
  const [err, setErr] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyMsg, setApplyMsg] = useState<string | null>(null)
  const [frame, setFrame] = useState(0) // bump to reload the iframe
  const [width, setWidth] = useState<number | null>(null) // page width (px) inside the iframe; null = full
  const [tree, setTree] = useState<TreeNode[] | null>(null)
  const [gap, setGap] = useState<{ node: TreeNode; x: number; y: number } | null>(null)
  const frameRef = useRef<HTMLIFrameElement>(null)

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

  // the inspector (same-origin iframe) posts its structural tree here
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const d = e.data
      if (d && d.zmTree && Array.isArray(d.tree)) setTree(d.tree)
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  // a new page → drop the stale tree until the fresh iframe re-posts
  useEffect(() => {
    setTree(null)
    setGap(null)
  }, [slug, frame])

  function requestTree() {
    frameRef.current?.contentWindow?.postMessage({ zmReq: true }, '*')
  }
  function focusNode(uid?: number | null) {
    if (uid == null) return
    frameRef.current?.contentWindow?.postMessage({ zmFocus: uid }, '*')
  }

  async function onApply() {
    setApplying(true)
    setApplyMsg(null)
    try {
      const r = await applyZoning(project)
      setApplyMsg(r.summary || (r.ok ? 'Appliqué (aucune décision).' : 'Échec.'))
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
          (composant / area / absolute area). L'arbre à gauche montre les zones &amp; composants ;
          «&nbsp;<span className="text-[#f59e0b]">⚠</span>&nbsp;» = du code encore non assigné à un composant.
          «&nbsp;Appliquer&nbsp;» relance le moteur — byte-exact garanti.
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

        <span className="text-xs text-[#5e88ad]">{totalDecisions} décision(s) sur ce projet</span>

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
        // full-bleed: break out of the max-w-7xl <main> so the iframe truly spans the width
        <div className="relative left-1/2 right-1/2 -ml-[50vw] -mr-[50vw] w-screen px-4">
          <div className="flex gap-3">
            {/* LEFT: structural tree of zones & components */}
            <aside className="flex h-[84vh] w-[340px] shrink-0 flex-col rounded border border-[#0a3252] bg-[#001526]">
              <div className="border-b border-[#0a3252] px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[#5e88ad]">
                Arbre — zones &amp; composants
              </div>
              <div className="min-h-0 flex-1 overflow-auto px-1 py-2">
                {tree == null ? (
                  <div className="px-2 py-3 text-xs text-[#5e88ad]">Chargement de l'arbre…</div>
                ) : tree.length === 0 ? (
                  <div className="px-2 py-3 text-xs text-[#5e88ad]">Aucune zone / composant détecté sur cette page.</div>
                ) : (
                  <TreeRows
                    nodes={tree}
                    depth={0}
                    onFocus={focusNode}
                    onGapEnter={(node, e) => setGap({ node, x: e.clientX, y: e.clientY })}
                    onGapLeave={() => setGap(null)}
                  />
                )}
              </div>
            </aside>

            {/* RIGHT: responsive-width controls + the inspector iframe (fills remaining width) */}
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2 text-sm text-[#a8c1d6]">
                <span>Largeur&nbsp;:</span>
                {(
                  [
                    ['Mobile', 375],
                    ['Tablet', 768],
                    ['Laptop', 1024],
                    ['Desktop', 1440],
                  ] as [string, number][]
                ).map(([lbl, w]) => (
                  <button
                    key={w}
                    onClick={() => setWidth(w)}
                    className={`rounded border px-2 py-0.5 ${width === w ? 'border-violet-500 bg-violet-700 text-white' : 'border-[#0a3252] bg-[#001932] hover:bg-[#0a3252]'}`}
                  >
                    {lbl} {w}
                  </button>
                ))}
                <button
                  onClick={() => setWidth(null)}
                  className={`rounded border px-2 py-0.5 ${width === null ? 'border-violet-500 bg-violet-700 text-white' : 'border-[#0a3252] bg-[#001932] hover:bg-[#0a3252]'}`}
                >
                  Full
                </button>
                <input
                  type="range"
                  min={320}
                  max={1600}
                  step={5}
                  value={width ?? 1600}
                  onChange={(e) => setWidth(Number(e.target.value))}
                  className="w-48 accent-violet-500"
                  title="Largeur de la page (à la volée)"
                />
                <span className="font-mono text-xs text-[#7fd1ff]">{width ? `${width}px` : 'pleine largeur'}</span>
              </div>
              <div className="overflow-x-auto rounded border border-[#0a3252] bg-[#00223f] p-2">
                <iframe
                  ref={frameRef}
                  key={`${project}/${slug}#${frame}`}
                  title="zoning-inspector"
                  onLoad={requestTree}
                  src={`/projects/${encodeURIComponent(project)}/zoning/mirror/${encodeURIComponent(slug)}.manual.html`}
                  style={{ width: width ? `${width}px` : '100%' }}
                  className="mx-auto block h-[84vh] rounded border border-[#0a3252] bg-white"
                />
              </div>
            </div>
          </div>

          {/* hover a ⚠ gap → popin of the unassigned HTML */}
          {gap && (
            <div
              className="pointer-events-none fixed z-50 max-h-[60vh] w-[520px] overflow-auto rounded border border-amber-600 bg-[#1b1300] p-2 shadow-2xl"
              style={{
                left: Math.min(gap.x + 14, window.innerWidth - 540),
                top: Math.min(gap.y + 14, window.innerHeight - 220),
              }}
            >
              <div className="mb-1 text-xs font-semibold text-amber-400">
                Code non assigné à un composant · {gap.node.chars} car.{' '}
                <span className="font-normal text-amber-200/70">(sera perdu à la recompose — à composantiser)</span>
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-amber-100">
                {gap.node.html}
              </pre>
            </div>
          )}
        </div>
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

/** Recursive tree rows. A ⚠ gap sits between components wherever code is not yet componentized. */
function TreeRows({
  nodes,
  depth,
  onFocus,
  onGapEnter,
  onGapLeave,
}: {
  nodes: TreeNode[]
  depth: number
  onFocus: (uid?: number | null) => void
  onGapEnter: (node: TreeNode, e: React.MouseEvent) => void
  onGapLeave: () => void
}) {
  return (
    <ul className="text-[13px]">
      {nodes.map((n, i) => {
        const meta = KIND[n.k]
        const dot = n.k === 'component' && n.color ? n.color : meta.color
        const isGap = n.k === 'gap'
        return (
          <li key={i}>
            <button
              onClick={() => onFocus(n.uid)}
              onMouseEnter={isGap ? (e) => onGapEnter(n, e) : undefined}
              onMouseLeave={isGap ? onGapLeave : undefined}
              className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left hover:bg-[#0a2942] ${isGap ? 'text-amber-300' : 'text-gray-200'}`}
              style={{ paddingLeft: 6 + depth * 14 }}
              title={isGap ? 'Survole pour voir le code · clic pour le localiser' : n.name || meta.label}
            >
              <span style={{ color: dot }} className="shrink-0 text-[11px]">
                {meta.icon}
              </span>
              {isGap ? (
                <span className="truncate">
                  {n.chars} car. non assigné
                </span>
              ) : (
                <>
                  <span className="truncate font-medium">{n.name || meta.label}</span>
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-[#5e88ad]">{meta.label}</span>
                </>
              )}
            </button>
            {n.children && n.children.length > 0 && (
              <TreeRows
                nodes={n.children}
                depth={depth + 1}
                onFocus={onFocus}
                onGapEnter={onGapEnter}
                onGapLeave={onGapLeave}
              />
            )}
          </li>
        )
      })}
    </ul>
  )
}
