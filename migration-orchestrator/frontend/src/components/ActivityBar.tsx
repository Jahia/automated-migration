import { useEffect, useState } from 'react'
import type { RunState, StepState, EpicState, StoryState } from '../types'

interface Props {
  run: RunState
}

export default function ActivityBar({ run }: Props) {
  const [startedAt] = useState(Date.now())
  const [elapsed, setElapsed] = useState('0s')

  useEffect(() => {
    const interval = setInterval(() => {
      const diff = Date.now() - startedAt
      const s = Math.floor(diff / 1000)
      if (s < 60) setElapsed(`${s}s`)
      else if (s < 3600) setElapsed(`${Math.floor(s / 60)}m ${s % 60}s`)
      else setElapsed(`${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`)
    }, 1000)
    return () => clearInterval(interval)
  }, [startedAt])

  const currentEpic = run.epics.find(e => e.id === run.current_epic_id)
  const currentStory = currentEpic?.stories.find(s => s.id === run.current_story_id)

  const isIdle = run.status === 'created' || run.status === 'completed' || run.status === 'failed' || run.status === 'aborted'

  if (isIdle) return null
  
  const runningStep = findRunningStep(run)

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 mb-4">
      <div className="flex items-center gap-4">
        {run.status === 'running' && (
          <span className="w-3 h-3 rounded-full bg-blue-500 animate-pulse shrink-0" />
        )}
        {run.status === 'paused' && (
          <span className="w-3 h-3 rounded-full bg-yellow-500 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          {run.status === 'running' && runningStep && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-blue-300 font-medium">▶ {runningStep.task_type}</span>
              <span className="text-gray-500">@</span>
              <span className="text-purple-400">{runningStep.agent}</span>
              {runningStep.title && (
                <>
                  <span className="text-gray-600">—</span>
                  <span className="text-gray-400 truncate">{runningStep.title}</span>
                </>
              )}
            </div>
          )}
          {run.status === 'running' && !runningStep && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-blue-300">Démarrage...</span>
            </div>
          )}
          {run.status === 'paused' && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-yellow-300">⏸ En pause</span>
              {currentStory && (
                <span className="text-gray-400">— story: {currentStory.title}</span>
              )}
            </div>
          )}
          <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
            {currentEpic && <span>epic: {currentEpic.title}</span>}
            {currentStory && <span>story: {currentStory.title}</span>}
            <span>⏱ {elapsed}</span>
          </div>
        </div>
        <div className="text-xs text-gray-500 shrink-0 text-right">
          <div>step: {run.current_step_id || '-'}</div>
          <div className="mt-0.5">statut: {run.status}</div>
        </div>
      </div>
    </div>
  )
}

function findRunningStep(run: RunState): StepState | undefined {
  for (const epic of run.epics) {
    for (const story of epic.stories) {
      for (const step of story.steps) {
        if (step.status === 'running' || step.status === 'verifying') return step
      }
    }
  }
  return undefined
}
