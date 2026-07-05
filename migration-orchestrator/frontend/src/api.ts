import type { ContentProgress, RunState, SSEEvent } from './types'

const BASE = ''

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

export async function fetchRuns(): Promise<{ run_id: string; goal: string; status: string; created_at: number }[]> {
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
