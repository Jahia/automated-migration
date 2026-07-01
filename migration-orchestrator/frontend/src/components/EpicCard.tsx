import { useState } from 'react'
import StoryCard from './StoryCard'
import RectificationPanel from './RectificationPanel'
import ReviewHistory from './ReviewHistory'
import { restartEpic } from '../api'
import type { EpicState } from '../types'

interface Props {
  epic: EpicState
  runId: string
  index: number
}

const statusColors: Record<string, string> = {
  pending: 'border-gray-700',
  running: 'border-blue-500',
  reviewing: 'border-orange-500',
  waiting_approval: 'border-yellow-500',
  approved: 'border-green-500',
  failed: 'border-red-500',
}

const statusBadges: Record<string, string> = {
  pending: 'bg-gray-700 text-gray-300',
  running: 'bg-blue-900 text-blue-300',
  reviewing: 'bg-orange-900 text-orange-300',
  waiting_approval: 'bg-yellow-900 text-yellow-300',
  approved: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
}

export default function EpicCard({ epic, runId, index }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [restarting, setRestarting] = useState(false)

  const onRestart = async () => {
    if (!confirm(`Restart Epic ${index + 1} "${epic.title}"?\n\nThis resets the epic and ALL its stories/steps to pending and re-runs them. Earlier approved epics are untouched.`)) return
    setRestarting(true)
    try {
      await restartEpic(runId, epic.id)
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div className={`border rounded-lg ${statusColors[epic.status] || 'border-gray-700'}`}>
      <div className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-900/50 transition">
        <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-3 flex-1 text-left">
          <span className="text-gray-500 text-sm font-mono w-6">{expanded ? '▼' : '▶'}</span>
          <span className="font-semibold flex-1">
            Epic {index + 1}: {epic.title}
          </span>
        </button>
        <span className={`px-2 py-0.5 rounded text-xs ${statusBadges[epic.status] || ''}`}>
          {epic.status}
          {epic.review_round > 0 && ` (round ${epic.review_round})`}
        </span>
        {epic.status !== 'pending' && (
          <button
            onClick={onRestart}
            disabled={restarting}
            title="Reset this epic and all its stories to pending and re-run"
            className="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50"
          >
            {restarting ? '…' : '↻ Restart'}
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-4 pb-4">
          <p className="text-gray-400 text-sm mb-3 ml-9">{epic.goal}</p>

          {epic.pending_proposal && (
            <div className="mb-4 ml-9">
              <RectificationPanel proposal={epic.pending_proposal} runId={runId} epicId={epic.id} />
            </div>
          )}

          {epic.review_history.length > 0 && (
            <div className="mb-4 ml-9">
              <ReviewHistory history={epic.review_history} />
            </div>
          )}

          <div className="space-y-3 ml-6">
            {epic.stories.map((story, si) => (
              <StoryCard key={story.id} story={story} runId={runId} epicId={epic.id} index={si} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
