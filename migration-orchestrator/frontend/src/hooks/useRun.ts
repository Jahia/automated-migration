import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchRun } from '../api'
import { useSSE } from './useSSE'
import type { RunState, SSEEvent, StepStatus, StoryStatus, EpicStatus, AgentResult, HumanQuestion, RectificationProposal } from '../types'

export function useRun(runId: string | null) {
  const [run, setRun] = useState<RunState | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastPollRef = useRef<number>(0)
  const isActiveRef = useRef(false)

  const loadRun = useCallback(async () => {
    if (!runId) return
    isActiveRef.current = true
    lastPollRef.current = Date.now()
    try {
      const data = await fetchRun(runId)
      if (isActiveRef.current) {
        setRun(data)
        setError(null)
      }
    } catch (e) {
      if (isActiveRef.current) setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    isActiveRef.current = true
    loadRun()
    const interval = setInterval(loadRun, 3000)
    return () => {
      isActiveRef.current = false
      clearInterval(interval)
    }
  }, [loadRun])

  const handleSSE = useCallback((event: SSEEvent) => {
    setRun((prev) => {
      if (!prev) return prev
      return applySSEEvent(prev, event)
    })
  }, [])

  useSSE(runId, handleSSE)

  return { run, loading, error, reload: loadRun }
}

function applySSEEvent(run: RunState, event: SSEEvent): RunState {
  const next = { ...run }

  switch (event.type) {
    case 'run_status':
      next.status = event.data.status as RunStatus
      break

    case 'step_streaming':
      if (event.step_id) {
        next.epics = next.epics.map(epic => ({
          ...epic,
          stories: epic.stories.map(story => ({
            ...story,
            steps: story.steps.map(step =>
              step.id === event.step_id
                ? { ...step, streaming_text: event.data.text as string || step.streaming_text + (event.data.delta || '') }
                : step
            ),
          })),
        }))
      }
      break

    case 'step_status':
      if (event.step_id) {
        next.epics = next.epics.map(epic => ({
          ...epic,
          stories: epic.stories.map(story => ({
            ...story,
            steps: story.steps.map(step =>
              step.id === event.step_id ? { ...step, status: event.data.status as StepStatus } : step
            ),
          })),
        }))
      }
      break

    case 'step_completed':
      if (event.step_id) {
        next.epics = next.epics.map(epic => ({
          ...epic,
          stories: epic.stories.map(story => ({
            ...story,
            steps: story.steps.map(step =>
              step.id === event.step_id ? { ...step, agent_result: event.data.result as AgentResult } : step
            ),
          })),
        }))
      }
      break

    case 'story_status':
      if (event.story_id) {
        next.epics = next.epics.map(epic => ({
          ...epic,
          stories: epic.stories.map(story =>
            story.id === event.story_id ? { ...story, status: event.data.status as StoryStatus } : story
          ),
        }))
      }
      break

    case 'epic_status':
      if (event.epic_id) {
        next.epics = next.epics.map(epic =>
          epic.id === event.epic_id ? { ...epic, status: event.data.status as EpicStatus } : epic
        )
      }
      break

    case 'human_question':
      if (event.step_id) {
        next.epics = next.epics.map(epic => ({
          ...epic,
          stories: epic.stories.map(story => ({
            ...story,
            steps: story.steps.map(step =>
              step.id === event.step_id
                ? { ...step, question: event.data.question as HumanQuestion, status: 'waiting_human' as StepStatus }
                : step
            ),
          })),
        }))
      }
      break

    case 'rectification_proposed':
      if (event.epic_id) {
        next.epics = next.epics.map(epic =>
          epic.id === event.epic_id
            ? { ...epic, pending_proposal: event.data.proposal as RectificationProposal, status: 'waiting_approval' as EpicStatus }
            : epic
        )
      }
      break

    case 'rectification_decided':
      if (event.epic_id) {
        next.epics = next.epics.map(epic =>
          epic.id === event.epic_id ? { ...epic, pending_proposal: null } : epic
        )
      }
      break

    case 'run_paused':
      next.status = 'paused' as RunStatus
      break

    case 'run_resumed':
      next.status = 'running' as RunStatus
      break
  }

  return next
}

type RunStatus = 'created' | 'running' | 'paused' | 'completed' | 'failed' | 'aborted'
