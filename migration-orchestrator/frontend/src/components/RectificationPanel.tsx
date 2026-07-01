import { approveProposal, rejectProposal } from '../api'
import type { RectificationProposal } from '../types'

interface Props {
  proposal: RectificationProposal
  runId: string
  epicId: string
}

export default function RectificationPanel({ proposal, runId, epicId }: Props) {
  const handleApprove = async () => {
    await approveProposal(runId, epicId)
  }

  const handleReject = async () => {
    await rejectProposal(runId, epicId)
  }

  const result = proposal.result

  return (
    <div className="bg-yellow-900/20 border border-yellow-700 rounded p-4">
      <h4 className="text-yellow-200 font-semibold text-sm mb-2">
        Sous-plan de rectification proposé (round {proposal.round})
      </h4>

      <div className="mb-3">
        <p className="text-yellow-300 text-xs font-semibold">Diagnostic:</p>
        <p className="text-gray-300 text-xs">{result.diagnosis}</p>
      </div>

      <div className="mb-3">
        <p className="text-yellow-300 text-xs font-semibold mb-1">
          Nouvelles stories proposées ({result.new_stories.length}):
        </p>
        <div className="space-y-2">
          {result.new_stories.map((story, i) => (
            <div key={i} className="bg-gray-800/50 rounded p-2">
              <p className="text-sm font-medium">{story.title}</p>
              <p className="text-xs text-gray-400">{story.description}</p>
              <p className="text-xs text-yellow-600 mt-1">Raison: {story.reason}</p>
              {story.steps && story.steps.length > 0 && (
                <div className="mt-1 ml-2">
                  <p className="text-xs text-gray-500">Steps:</p>
                  {story.steps.map((step, si) => (
                    <p key={si} className="text-xs text-gray-400">
                      → {step.title} ({step.task_type}{step.agent ? ` @${step.agent}` : ''})
                    </p>
                  ))}
                </div>
              )}
              {story.depends_on.length > 0 && (
                <p className="text-xs text-gray-500">Dépend de: {story.depends_on.join(', ')}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          className="px-4 py-1.5 bg-green-700 hover:bg-green-600 rounded text-sm"
        >
          Approuver
        </button>
        <button
          onClick={handleReject}
          className="px-4 py-1.5 bg-red-700 hover:bg-red-600 rounded text-sm"
        >
          Rejeter
        </button>
      </div>
    </div>
  )
}
