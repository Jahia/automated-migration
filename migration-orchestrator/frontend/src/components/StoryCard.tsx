import { useState, useEffect } from 'react'
import StepCard from './StepCard'
import { restartStory } from '../api'
import type { StoryState } from '../types'

interface Props {
  story: StoryState
  runId: string
  epicId: string
  index: number
}

const statusBadges: Record<string, string> = {
  pending: 'bg-gray-700 text-gray-300',
  running: 'bg-blue-900 text-blue-300',
  approved: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
}

const statusIcons: Record<string, string> = {
  pending: '⏳',
  running: '🔄',
  approved: '✅',
  failed: '❌',
}

export default function StoryCard({ story, runId, epicId, index }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [restarting, setRestarting] = useState(false)

  useEffect(() => {
    if (story.status === 'running') {
      setExpanded(true)
    }
  }, [story.status])

  const onRestart = async () => {
    if (!confirm(`Restart Story ${index + 1} "${story.title}"?\n\nThis resets the story (and any stories depending on it) to pending and re-runs them; the epic re-reviews afterward. Approved sibling stories are kept.`)) return
    setRestarting(true)
    try {
      await restartStory(runId, epicId, story.id)
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div className="border border-gray-800 rounded-lg bg-gray-900/30">
      <div className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-800/50 transition">
        <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-3 flex-1 text-left">
          <span className="text-gray-500 text-xs font-mono w-4">{expanded ? '▼' : '▶'}</span>
          <span className="text-sm font-mono text-gray-500 w-6 text-center">{statusIcons[story.status]}</span>
          <span className="font-medium flex-1 text-sm">
            Story {index + 1}: {story.title}
          </span>
        </button>
        <span className={`px-2 py-0.5 rounded text-xs ${statusBadges[story.status] || ''}`}>
          {story.status}
        </span>
        {story.status !== 'pending' && (
          <button
            onClick={onRestart}
            disabled={restarting}
            title="Reset this story (and its dependents) to pending and re-run"
            className="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50"
          >
            {restarting ? '…' : '↻'}
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-3 pb-3">
          <p className="text-gray-400 text-xs mb-2 ml-10">{story.description}</p>
          {story.acceptance_criteria.length > 0 && (
            <ul className="text-xs text-gray-500 mb-3 ml-10 list-disc list-inside">
              {story.acceptance_criteria.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
          <div className="space-y-2 ml-7">
            {story.steps.map((step, si) => (
              <StepCard key={step.id} step={step} runId={runId} index={si} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
