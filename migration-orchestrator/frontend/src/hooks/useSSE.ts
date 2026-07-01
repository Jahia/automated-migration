import { useEffect, useRef, useCallback } from 'react'
import { createSSE } from '../api'
import type { SSEEvent } from '../types'

export function useSSE(runId: string | null, onEvent: (event: SSEEvent) => void) {
  const esRef = useRef<EventSource | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!runId) return
    const es = createSSE(runId, (event) => onEventRef.current(event))
    esRef.current = es
    return () => {
      es.close()
      esRef.current = null
    }
  }, [runId])
}
