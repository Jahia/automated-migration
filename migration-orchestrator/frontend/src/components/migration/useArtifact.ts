import { useEffect, useState } from 'react'
import { artifactUrl } from '../fidelity/api'

export type ArtifactStatus = 'loading' | 'ok' | 'missing'

/** Fetch a JSON artifact from the run's workflow-output. `missing` = not produced yet (404). */
export function useJsonArtifact<T>(runId: string, path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [status, setStatus] = useState<ArtifactStatus>('loading')
  useEffect(() => {
    let alive = true
    setStatus('loading')
    fetch(artifactUrl(runId, path))
      .then((r) => (r.ok ? (r.json() as Promise<T>) : Promise.reject(r.status)))
      .then((d) => alive && (setData(d), setStatus('ok')))
      .catch(() => alive && setStatus('missing'))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, path, ...deps])
  return { data, status }
}

/** Fetch a text artifact (SUMMARY.md, redirects.map …). */
export function useTextArtifact(runId: string, path: string, deps: unknown[] = []) {
  const [text, setText] = useState<string | null>(null)
  const [status, setStatus] = useState<ArtifactStatus>('loading')
  useEffect(() => {
    let alive = true
    setStatus('loading')
    fetch(artifactUrl(runId, path))
      .then((r) => (r.ok ? r.text() : Promise.reject(r.status)))
      .then((t) => alive && (setText(t), setStatus('ok')))
      .catch(() => alive && setStatus('missing'))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, path, ...deps])
  return { text, status }
}
