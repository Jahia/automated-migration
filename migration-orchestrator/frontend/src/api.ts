import type { ContentProgress, ProjectArtifactsReport, RunProvenance, RunState, RunSummary, SSEEvent } from './types'

const BASE = ''

/**
 * Per-step artifact provenance for the step-honesty view (one batched call per
 * run). Flags steps whose primary workflow-output JSON was produced by a
 * DIFFERENT run (reused, not re-done this run). Throws on error so the caller can
 * degrade gracefully (an older engine has no such endpoint → no honesty chips).
 */
export async function fetchRunProvenance(runId: string): Promise<RunProvenance> {
  const resp = await fetch(`${BASE}/runs/${runId}/provenance`)
  if (!resp.ok) throw new Error(`provenance unavailable (${resp.status})`)
  return resp.json()
}

/**
 * Read-only content-load progress for a project (the content_watch.sh ticker +
 * a light integrity-report summary). Pure file read on the engine — no Jahia call.
 * Throws on 404 / network error so the caller can degrade gracefully (the belt
 * endpoint only exists after the next engine restart).
 */
export async function fetchContentProgress(project: string, limit = 50): Promise<ContentProgress> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/content-progress?limit=${limit}`)
  if (!resp.ok) throw new Error(`content-progress unavailable (${resp.status})`)
  return resp.json()
}

/**
 * Per-project artifact provenance + staleness (P3b) — one call covers every
 * known pipeline artifact (see artifact_provenance.py's DAG registry). Throws
 * on error so callers degrade gracefully (an older engine has no such endpoint,
 * or the project directory doesn't exist yet → no staleness chips, no crash).
 */
export async function fetchProjectArtifacts(project: string): Promise<ProjectArtifactsReport> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/artifacts`)
  if (!resp.ok) throw new Error(`project artifacts unavailable (${resp.status})`)
  return resp.json()
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const resp = await fetch(`${BASE}/runs`)
  return resp.json()
}

export async function fetchRun(runId: string): Promise<RunState> {
  const resp = await fetch(`${BASE}/runs/${runId}`)
  return resp.json()
}

export async function fetchSchema(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE}/schema`)
  return resp.json()
}

// ── Manual zoning inspector (project-scoped; served by src/routes/manual.py) ──
export interface ZoningPage { slug: string; decisions: number }

export async function fetchZoningProjects(): Promise<{ project: string; pages: number }[]> {
  const resp = await fetch(`${BASE}/zoning/projects`)
  if (!resp.ok) throw new Error(`zoning projects unavailable (${resp.status})`)
  return (await resp.json()).projects
}

export async function fetchZoningPages(project: string): Promise<ZoningPage[]> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/pages`)
  if (!resp.ok) throw new Error(`zoning pages unavailable (${resp.status})`)
  return (await resp.json()).pages
}

/** Re-run the deterministic engine so manual decisions land in the content-load. */
export async function applyZoning(project: string): Promise<{ ok: boolean; summary: string | null; head: string | null }> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/apply`, { method: 'POST' })
  if (!resp.ok) throw new Error(`apply failed (${resp.status})`)
  return resp.json()
}

// ── Single-source component model (Nodetypes tab; seeded by the engine) ──
export interface NodeTypeView { name: string; file: string; instances: number; chars: number }
export interface NodeTypeEntry {
  id: string
  name: string
  kind: 'component' | 'container' | 'zone' | 'absolute' | 'passthrough'
  contentFree: boolean
  isContainer: boolean
  childType: string | null
  instances: number
  pages: string[]
  pageCount: number
  views: NodeTypeView[]
  variantsTotal: number
  origin: string
}

export async function fetchNodetypes(project: string): Promise<{ entries: NodeTypeEntry[]; seeded: boolean }> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/nodetypes`)
  if (!resp.ok) throw new Error(`nodetypes unavailable (${resp.status})`)
  return resp.json()
}

export async function fetchViewCode(project: string, file: string): Promise<{ file: string; code: string }> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/view?file=${encodeURIComponent(file)}`)
  if (!resp.ok) throw new Error(`view unavailable (${resp.status})`)
  return resp.json()
}

export async function fetchDecisions(project: string): Promise<Array<Record<string, unknown>>> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/decisions`)
  if (!resp.ok) return []
  return (await resp.json()).decisions || []
}

/** Delete a nodetype site-wide = a suppress decision (id keyed on the nodeType). */
export async function suppressNodeType(project: string, nodeType: string, name: string): Promise<void> {
  await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision: { action: 'suppress', nodeType, type: name, id: `suppress|${nodeType}` } }),
  })
}

export async function unsuppressNodeType(project: string, nodeType: string): Promise<void> {
  await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: `suppress|${nodeType}` }),
  })
}

/** The single JCR namespace prefix for this project's nodetypes (default 'custom'). */
export async function fetchNamespace(project: string): Promise<string> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/namespace`)
  if (!resp.ok) return 'custom'
  return (await resp.json()).namespace || 'custom'
}

export async function setNamespace(project: string, namespace: string): Promise<string> {
  const resp = await fetch(`${BASE}/projects/${encodeURIComponent(project)}/zoning/namespace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ namespace }),
  })
  if (!resp.ok) throw new Error(`namespace refusé (${resp.status})`)
  return (await resp.json()).namespace
}

// NOTE: launch/relaunch of runs is intentionally NOT exposed here. The cockpit
// is observability-only — runs are created, started, and restarted exclusively
// via the REST API (POST /migrations, /runs/{id}/start, /runs/{id}/restart,
// /runs/{id}/epics|stories .../restart, /runs/{id}/jump). See CONTROL-LOOP.md.
// The UI keeps only in-flight decision controls (pause / resume / abort) plus
// housekeeping (delete / prune) and the gate approve/reject/rerun surfaces.

export async function pauseRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/pause`, { method: 'POST' })
}

export async function resumeRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/resume`, { method: 'POST' })
}

export async function abortRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/abort`, { method: 'POST' })
}

export async function deleteRun(runId: string): Promise<void> {
  const resp = await fetch(`${BASE}/runs/${runId}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`delete failed: ${resp.status}`)
}

export async function pruneRuns(): Promise<{ deleted: string[]; count: number }> {
  const resp = await fetch(`${BASE}/runs/prune`, { method: 'POST' })
  if (!resp.ok) throw new Error(`prune failed: ${resp.status}`)
  return resp.json()
}

export async function answerQuestion(runId: string, stepId: string, answer: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/steps/${stepId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
}

export async function approveProposal(runId: string, epicId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/epics/${epicId}/proposal/approve`, { method: 'POST' })
}

export async function rejectProposal(runId: string, epicId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/epics/${epicId}/proposal/reject`, { method: 'POST' })
}

export function createSSE(runId: string, onEvent: (event: SSEEvent) => void): EventSource {
  const es = new EventSource(`${BASE}/runs/${runId}/events`)
  es.addEventListener('message', (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
    } catch {}
  })
  es.addEventListener('step_status', (e) => handleSSE(e, onEvent))
  es.addEventListener('step_streaming', (e) => handleSSE(e, onEvent))
  es.addEventListener('step_completed', (e) => handleSSE(e, onEvent))
  es.addEventListener('step_tool', (e) => handleSSE(e, onEvent))
  es.addEventListener('step_loop', (e) => handleSSE(e, onEvent))
  es.addEventListener('story_status', (e) => handleSSE(e, onEvent))
  es.addEventListener('epic_status', (e) => handleSSE(e, onEvent))
  es.addEventListener('review_result', (e) => handleSSE(e, onEvent))
  es.addEventListener('rectification_proposed', (e) => handleSSE(e, onEvent))
  es.addEventListener('human_question', (e) => handleSSE(e, onEvent))
  es.addEventListener('run_status', (e) => handleSSE(e, onEvent))
  es.addEventListener('run_paused', (e) => handleSSE(e, onEvent))
  es.addEventListener('run_resumed', (e) => handleSSE(e, onEvent))
  es.addEventListener('step_jumped', (e) => handleSSE(e, onEvent))
  es.addEventListener('epic_restarted', (e) => handleSSE(e, onEvent))
  es.addEventListener('story_restarted', (e) => handleSSE(e, onEvent))
  return es
}

function handleSSE(e: MessageEvent, onEvent: (event: SSEEvent) => void) {
  try {
    const data = JSON.parse(e.data)
    onEvent(data)
  } catch {}
}
