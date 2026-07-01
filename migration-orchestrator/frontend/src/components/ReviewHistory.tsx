interface ReviewEntry {
  round: number
  result: Record<string, unknown>
  timestamp: number
}

interface Props {
  history: ReviewEntry[]
}

export default function ReviewHistory({ history }: Props) {
  if (history.length === 0) return null

  return (
    <div className="border-l-2 border-orange-700 pl-3">
      <p className="text-xs font-semibold text-orange-400 mb-1">Historique des reviews</p>
      <div className="space-y-1">
        {history.map((entry, i) => {
          const action = entry.result.action as string
          const isApproved = action === 'approved'
          return (
            <div key={i} className="text-xs">
              <span className="text-gray-500">Round {entry.round}:</span>{' '}
              <span className={isApproved ? 'text-green-400' : 'text-yellow-400'}>
                {action}
              </span>
              {action === 'rectify' && (
                <span className="text-gray-500 ml-2">
                  {(entry.result.new_stories as { id: string }[] || entry.result.new_steps as { id: string }[] || []).length} stories ajoutées
                </span>
              )}
              {action === 'approved' && (
                <span className="text-gray-500 ml-2">
                  {(entry.result.summary as string || '').slice(0, 100)}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
