import type { ReconstructReport } from './types'

// Same-origin as the engine (matches src/api.ts convention: BASE = '').
const BASE = ''

/**
 * URL of a file under a run's workflow-output. The engine must serve the
 * project's workflow-output dir at this path (see MIGRATION_PROFILE.md,
 * "Artifact serving"). Example: artifactUrl(id, 'reconstruct/home.source.png').
 */
export function artifactUrl(runId: string, path: string): string {
  return `${BASE}/runs/${runId}/artifacts/${path}`
}

export async function fetchReconstructReport(runId: string): Promise<ReconstructReport> {
  const resp = await fetch(artifactUrl(runId, 'reconstruct/reconstruct.json'))
  if (!resp.ok) throw new Error(`fidelity report not available (${resp.status})`)
  return resp.json()
}

/**
 * Approve the fidelity HALT gate → resume the run into templatization.
 * The engine forces the halted step to done on resume (see orchestrator.py).
 */
export async function approveFidelityGate(runId: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/resume`, { method: 'POST' })
}

/** Reject the gate: flag the run so the operator fixes an extraction gap first. */
export async function rejectFidelityGate(runId: string, reason: string): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

/**
 * Re-run the reconstruction probe on a chosen sample (typed migration action —
 * see MIGRATION_PROFILE.md). `pages` empty → the step's default sample.
 */
export async function rerunFidelity(runId: string, pages: string[] = []): Promise<void> {
  await fetch(`${BASE}/runs/${runId}/fidelity/rerun`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages }),
  })
}
