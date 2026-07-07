import { useEffect, useRef, useState } from 'react'
import {
  fetchZoningProjects, fetchZoningPages, applyZoning, fetchNodetypes, fetchViewCode,
  fetchDecisions, suppressNodeType, fetchNamespace, setNamespace,
  type ZoningPage, type NodeTypeEntry, type NodeTypeView,
} from '../api'

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
  nt?: string // camelCase nodetype local name (component/layout) — displayed as <ns>:<nt>
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
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set()) // tree paths whose children are hidden
  const [tab, setTab] = useState<'nodetypes' | 'tree'>('tree')
  const [nodetypes, setNodetypes] = useState<{ entries: NodeTypeEntry[]; seeded: boolean } | null>(null)
  const [ntOpen, setNtOpen] = useState<Set<string>>(new Set())   // expanded nodetype rows (views shown)
  const [supNT, setSupNT] = useState<Set<string>>(new Set())     // suppressed nodeType ids (asr:x)
  const [supShort, setSupShort] = useState<Set<string>>(new Set()) // suppressed short type names (lc)
  const [viewCode, setViewCode] = useState<{ title: string; code: string } | null>(null)
  const [ns, setNs] = useState('custom') // the one JCR namespace prefix for all nodetypes
  const [cacheBust] = useState(() => Date.now()) // refetch the (regenerated) inspector page per load
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

  // the inspector (same-origin iframe) posts its structural tree — and notifies us when it
  // suppressed a type from inside the popin, so the Nodetypes tab stays in sync.
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const d = e.data
      if (d && d.zmTree && Array.isArray(d.tree)) setTree(d.tree)
      if (d && d.zmChanged) loadModelAndSuppressed()
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project])

  // load the single-source model + which types are currently suppressed (for the Nodetypes tab)
  const loadModelAndSuppressed = () => {
    if (!project) return
    fetchNamespace(project).then(setNs).catch(() => {})
    fetchNodetypes(project).then(setNodetypes).catch(() => setNodetypes({ entries: [], seeded: false }))
    fetchDecisions(project)
      .then((ds) => {
        const nt = new Set<string>(), sh = new Set<string>()
        ds.forEach((d) => {
          if (d.action === 'suppress') {
            if (d.nodeType) nt.add(String(d.nodeType))
            if (d.type) sh.add(String(d.type).toLowerCase())
          }
        })
        setSupNT(nt); setSupShort(sh)
      })
      .catch(() => {})
  }
  useEffect(() => {
    setNodetypes(null); setNtOpen(new Set())
    loadModelAndSuppressed()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project])

  // a new page → drop the stale tree until the fresh iframe re-posts
  useEffect(() => {
    setTree(null)
    setGap(null)
    setCollapsed(new Set())
  }, [slug, frame])

  function requestTree() {
    const w = frameRef.current?.contentWindow
    if (w) { w.postMessage({ zmReq: true }, '*'); w.postMessage({ zmNs: ns }, '*') }
  }
  function focusNode(uid?: number | null) {
    if (uid == null) return
    frameRef.current?.contentWindow?.postMessage({ zmFocus: uid }, '*')
  }
  // keep the inspector's popin namespace in sync as you type
  useEffect(() => {
    frameRef.current?.contentWindow?.postMessage({ zmNs: ns }, '*')
  }, [ns])
  async function saveNs(e: React.SyntheticEvent<HTMLInputElement>) {
    const v = (e.currentTarget.value || '').trim() // read the DOM value, not a possibly-stale closure
    if (!/^[A-Za-z][A-Za-z0-9]*$/.test(v)) { fetchNamespace(project).then(setNs); return } // revert invalid
    const saved = await setNamespace(project, v).catch(() => v)
    setNs(saved)
  }
  function toggleCollapse(path: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }
  const collapseAll = () => setCollapsed(new Set(branchPaths(tree ?? [], '')))
  const expandAll = () => setCollapsed(new Set())

  async function onApply() {
    setApplying(true)
    setApplyMsg(null)
    try {
      const r = await applyZoning(project)
      setApplyMsg(r.summary || (r.ok ? 'Appliqué (aucune décision).' : 'Échec.'))
      fetchZoningPages(project).then(setPages).catch(() => {})
      loadModelAndSuppressed() // the engine re-seeded component-model.json
      setFrame((f) => f + 1)
    } catch (e) {
      setApplyMsg(`Erreur: ${e}`)
    } finally {
      setApplying(false)
    }
  }

  const isSuppressed = (e: NodeTypeEntry) => supNT.has(e.id) || supShort.has(e.name.toLowerCase())

  async function onDeleteNodetype(e: NodeTypeEntry) {
    if (!confirm(
      `Supprimer le composant « ${e.name} » ?\n${e.instances} instance(s) sur ${e.pageCount} page(s) ` +
      `seront désassignées (rendues verbatim, byte-exact). Irréversible via l'outil.`)) return
    await suppressNodeType(project, e.id, e.name)
    setSupNT((p) => new Set(p).add(e.id))
    setSupShort((p) => new Set(p).add(e.name.toLowerCase()))
    frameRef.current?.contentWindow?.postMessage({ zmReload: true }, '*') // sync the tree/overlay
  }

  async function onViewCode(e: NodeTypeEntry, v: NodeTypeView) {
    try {
      const r = await fetchViewCode(project, v.file)
      setViewCode({ title: `${e.name} · ${v.name}`, code: r.code })
    } catch (err) {
      setViewCode({ title: `${e.name} · ${v.name}`, code: `// ${err}` })
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

        <label className="text-sm text-[#a8c1d6]">
          Namespace{' '}
          <input
            value={ns}
            onChange={(e) => setNs(e.target.value)}
            onBlur={saveNs}
            onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
            spellCheck={false}
            className="w-28 rounded border border-[#0a3252] bg-[#001932] px-2 py-1 font-mono text-sm text-gray-100"
            title="Préfixe JCR unique pour tous les nodetypes (ex. custom → custom:languageSwitcher)"
          />
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
            <aside className="flex h-[84vh] w-[360px] shrink-0 flex-col rounded border border-[#0a3252] bg-[#001526]">
              <div className="flex border-b border-[#0a3252] text-xs font-semibold">
                <button
                  onClick={() => setTab('nodetypes')}
                  className={`flex-1 px-3 py-2 ${tab === 'nodetypes' ? 'bg-[#0a2942] text-white' : 'text-[#5e88ad] hover:text-white'}`}
                >
                  Nodetypes
                </button>
                <button
                  onClick={() => setTab('tree')}
                  className={`flex-1 px-3 py-2 ${tab === 'tree' ? 'bg-[#0a2942] text-white' : 'text-[#5e88ad] hover:text-white'}`}
                >
                  Component tree
                </button>
              </div>

              {tab === 'tree' && (
                <>
                  <div className="flex items-center gap-2 border-b border-[#0a3252] px-3 py-1.5 text-[11px] uppercase tracking-wide text-[#5e88ad]">
                    <span>zones &amp; composants</span>
                    {tree && tree.length > 0 && (
                      <span className="ml-auto flex gap-1 normal-case tracking-normal">
                        <button onClick={collapseAll} title="Tout replier" className="rounded border border-[#0a3252] px-1.5 py-0.5 font-normal text-[#a8c1d6] hover:bg-[#0a3252]">▸ replier</button>
                        <button onClick={expandAll} title="Tout déplier" className="rounded border border-[#0a3252] px-1.5 py-0.5 font-normal text-[#a8c1d6] hover:bg-[#0a3252]">▾ déplier</button>
                      </span>
                    )}
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
                        path=""
                        ns={ns}
                        collapsed={collapsed}
                        onToggle={toggleCollapse}
                        onFocus={focusNode}
                        onGapEnter={(node, e) => setGap({ node, x: e.clientX, y: e.clientY })}
                        onGapLeave={() => setGap(null)}
                      />
                    )}
                  </div>
                </>
              )}

              {tab === 'nodetypes' && (
                <div className="min-h-0 flex-1 overflow-auto px-1 py-2">
                  <NodetypesPanel
                    model={nodetypes}
                    ns={ns}
                    isSuppressed={isSuppressed}
                    open={ntOpen}
                    onToggle={(id) => setNtOpen((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })}
                    onViewCode={onViewCode}
                    onDelete={onDeleteNodetype}
                  />
                </div>
              )}
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
                  src={`/projects/${encodeURIComponent(project)}/zoning/mirror/${encodeURIComponent(slug)}.manual.html?v=${cacheBust}`}
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

          {/* click a view in the Nodetypes tab → overlay showing that component's code (skeleton) */}
          {viewCode && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={() => setViewCode(null)}>
              <div className="flex max-h-[85vh] w-[860px] max-w-full flex-col rounded border border-[#0a3252] bg-[#001526] shadow-2xl" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center gap-2 border-b border-[#0a3252] px-3 py-2">
                  <span className="font-mono text-sm font-semibold text-white">{viewCode.title}</span>
                  <span className="text-xs text-[#5e88ad]">skeleton — le « code » à ce stade (pré-module)</span>
                  <button onClick={() => setViewCode(null)} className="ml-auto rounded px-2 text-lg text-[#5e88ad] hover:text-white">✕</button>
                </div>
                <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[11px] leading-snug text-gray-200">{viewCode.code}</pre>
              </div>
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

/** All node paths that have children — used by "Tout replier". Path = dash-joined sibling indices. */
function branchPaths(nodes: TreeNode[], prefix: string): string[] {
  const out: string[] = []
  nodes.forEach((n, i) => {
    const p = prefix ? `${prefix}-${i}` : `${i}`
    if (n.children && n.children.length) {
      out.push(p)
      out.push(...branchPaths(n.children, p))
    }
  })
  return out
}

/** Recursive tree rows. A ⚠ gap sits between components wherever code is not yet componentized.
 * Nodes with children carry a ▸/▾ chevron (collapse/expand); the label click focuses in the page. */
function TreeRows({
  nodes,
  depth,
  path,
  ns,
  collapsed,
  onToggle,
  onFocus,
  onGapEnter,
  onGapLeave,
}: {
  nodes: TreeNode[]
  depth: number
  path: string
  ns: string
  collapsed: Set<string>
  onToggle: (path: string) => void
  onFocus: (uid?: number | null) => void
  onGapEnter: (node: TreeNode, e: React.MouseEvent) => void
  onGapLeave: () => void
}) {
  return (
    <ul className="text-[13px]">
      {nodes.map((n, i) => {
        const p = path ? `${path}-${i}` : `${i}`
        const meta = KIND[n.k]
        const dot = n.k === 'component' && n.color ? n.color : meta.color
        const isGap = n.k === 'gap'
        const hasKids = !!(n.children && n.children.length)
        const isCollapsed = collapsed.has(p)
        return (
          <li key={p}>
            <div className="flex items-stretch" style={{ marginLeft: depth * 12 }}>
              {hasKids ? (
                <button
                  onClick={() => onToggle(p)}
                  title={isCollapsed ? 'Déplier' : 'Replier'}
                  className="grid h-[15px] w-[15px] shrink-0 place-items-center rounded border border-[#1c4a70] text-[13px] font-bold leading-none text-[#7fd1ff] hover:bg-[#0a3252]"
                >
                  {isCollapsed ? '+' : '−'}
                </button>
              ) : (
                <span className="w-[15px] shrink-0" />
              )}
              <button
                onClick={() => onFocus(n.uid)}
                onMouseEnter={isGap ? (e) => onGapEnter(n, e) : undefined}
                onMouseLeave={isGap ? onGapLeave : undefined}
                className={`flex flex-1 items-center gap-1.5 rounded px-1.5 py-1 text-left hover:bg-[#0a2942] ${isGap ? 'text-amber-300' : 'text-gray-200'}`}
                title={isGap ? 'Survole pour voir le code · clic pour le localiser' : n.name || meta.label}
              >
                <span style={{ color: dot }} className="shrink-0 text-[11px]">
                  {meta.icon}
                </span>
                {isGap ? (
                  <span className="truncate">{n.chars} car. non assigné</span>
                ) : (
                  <>
                    <span className="truncate font-medium" title={n.nt ? `${ns}:${n.nt}` : n.name}>
                      {n.nt ? `${ns}:${n.nt}` : n.name || meta.label}
                    </span>
                    {hasKids && isCollapsed && (
                      <span className="shrink-0 text-[10px] text-[#5e88ad]">
                        {n.children!.length}
                      </span>
                    )}
                    <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wide text-[#5e88ad]">
                      {meta.label}
                    </span>
                  </>
                )}
              </button>
            </div>
            {hasKids && !isCollapsed && (
              <TreeRows
                nodes={n.children!}
                depth={depth + 1}
                path={p}
                ns={ns}
                collapsed={collapsed}
                onToggle={onToggle}
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

const NT_KIND: Record<string, { color: string; label: string }> = {
  component: { color: '#1aa06a', label: 'composant' },
  container: { color: '#1f6fd6', label: 'conteneur' },
  zone: { color: '#1f6fd6', label: 'zone' },
  absolute: { color: '#d33a2c', label: 'absolute area' },
  passthrough: { color: '#8a94a6', label: 'verbatim' },
}

/** Nodetypes tab — the single-source component model: the editable list of identified types,
 * their views (skeleton variants), a code overlay, and a site-wide delete. */
function NodetypesPanel({
  model,
  ns,
  isSuppressed,
  open,
  onToggle,
  onViewCode,
  onDelete,
}: {
  model: { entries: NodeTypeEntry[]; seeded: boolean } | null
  ns: string
  isSuppressed: (e: NodeTypeEntry) => boolean
  open: Set<string>
  onToggle: (id: string) => void
  onViewCode: (e: NodeTypeEntry, v: NodeTypeView) => void
  onDelete: (e: NodeTypeEntry) => void
}) {
  if (model == null) return <div className="px-2 py-3 text-xs text-[#5e88ad]">Chargement du modèle…</div>
  if (!model.seeded)
    return (
      <div className="px-2 py-3 text-xs leading-relaxed text-[#5e88ad]">
        Modèle pas encore généré. Lance <b className="text-[#a8c1d6]">« Appliquer les décisions »</b> une
        fois — le moteur seed <code className="text-[#a8c1d6]">component-model.json</code>.
      </div>
    )
  const live = model.entries.filter((e) => !isSuppressed(e))
  const dead = model.entries.filter((e) => isSuppressed(e))
  return (
    <ul className="text-[13px]">
      {live.length === 0 && <li className="px-2 py-3 text-xs text-[#5e88ad]">Aucun nodetype.</li>}
      {live.map((e) => {
        const meta = NT_KIND[e.kind] || NT_KIND.component
        const isOpen = open.has(e.id)
        const hasViews = e.views.length > 0
        const local = e.id.split(':').pop() || e.name
        return (
          <li key={e.id}>
            <div className="flex items-center gap-1.5 rounded px-1.5 py-1 hover:bg-[#0a2942]">
              {hasViews ? (
                <button onClick={() => onToggle(e.id)} className="grid h-[15px] w-[15px] shrink-0 place-items-center rounded border border-[#1c4a70] text-[13px] font-bold leading-none text-[#7fd1ff] hover:bg-[#0a3252]">
                  {isOpen ? '−' : '+'}
                </button>
              ) : (
                <span className="w-[15px] shrink-0" />
              )}
              <span style={{ color: meta.color }} className="shrink-0 text-[11px]">●</span>
              <span
                className="truncate font-mono text-[12px] font-medium text-gray-100"
                title={e.name !== local ? `${ns}:${local}  ·  libellé : ${e.name}` : `${ns}:${local}`}
              >
                {ns}:{local}
              </span>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-[#5e88ad]">{meta.label}</span>
              <span className="ml-auto shrink-0 text-[10px] text-[#5e88ad]">{e.instances}× · {e.pageCount}p</span>
              <button
                onClick={() => onDelete(e)}
                title="Supprimer ce nodetype sur tout le site"
                className="shrink-0 rounded px-1 text-[#b04a4a] hover:bg-[#3a1414] hover:text-red-300"
              >
                🗑
              </button>
            </div>
            {isOpen && (
              <div className="ml-5 border-l border-[#0a3252] pl-2">
                {e.contentFree && <div className="py-0.5 text-[10px] text-[#5e88ad]">content-free (déco)</div>}
                {e.isContainer && e.childType && (
                  <div className="py-0.5 text-[10px] text-[#5e88ad]">enfants : {e.childType}</div>
                )}
                {e.views.length === 0 && (
                  <div className="py-0.5 text-[10px] text-[#5e88ad]">structural — pas de code propre</div>
                )}
                {e.views.map((v) => (
                  <button
                    key={v.name}
                    onClick={() => onViewCode(e, v)}
                    className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[12px] text-[#a8c1d6] hover:bg-[#0a2942] hover:text-white"
                  >
                    <span className="text-[#5e88ad]">📄</span>
                    <span className="truncate">{v.name}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-[#5e88ad]">{v.instances}× · {v.chars}c</span>
                  </button>
                ))}
                {e.variantsTotal > e.views.length && (
                  <div className="py-0.5 text-[10px] text-[#5e88ad]">
                    +{e.variantsTotal - e.views.length} variante(s) non listée(s) · {e.variantsTotal} au total
                  </div>
                )}
              </div>
            )}
          </li>
        )
      })}
      {dead.length > 0 && (
        <li className="mt-2 border-t border-[#0a3252] px-2 pt-2 text-[10px] uppercase tracking-wide text-[#5e88ad]">
          Supprimés ({dead.length}) — verbatim au prochain Appliquer
        </li>
      )}
      {dead.map((e) => (
        <li key={e.id} className="flex items-center gap-1.5 px-2 py-0.5 text-[12px] text-[#5e6b7a] line-through">
          <span className="w-4" />
          {e.name}
        </li>
      ))}
    </ul>
  )
}
