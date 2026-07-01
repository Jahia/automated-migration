import type { RunState, SSEEvent } from './types'

const BASE = ''

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

export async function createRun(plan: Record<string, unknown>): Promise<{ run_id: string }> {
  const resp = await fetch(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
  })
  return resp.json()
}

export async function pauseRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/pause`, { method: 'POST' })
}

export async function resumeRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/resume`, { method: 'POST' })
}

export async function startRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/start`, { method: 'POST' })
}

export async function abortRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/abort`, { method: 'POST' })
}

export async function restartRun(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/restart`, { method: 'POST' })
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

export async function jumpToStep(runId: string, stepId: string, resetDependents = true): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE}/runs/${runId}/jump`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step_id: stepId, reset_dependents: resetDependents }),
  })
  return resp.json()
}

export async function restartEpic(runId: string, epicId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE}/runs/${runId}/epics/${epicId}/restart`, { method: 'POST' })
  return resp.json()
}

export async function restartStory(runId: string, epicId: string, storyId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE}/runs/${runId}/epics/${epicId}/stories/${storyId}/restart`, { method: 'POST' })
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
