import EpicCard from './EpicCard'
import type { RunState } from '../types'

interface Props {
  run: RunState
}

export default function EpicTimeline({ run }: Props) {
  return (
    <div className="space-y-6">
      {run.epics.map((epic, i) => (
        <EpicCard key={epic.id} epic={epic} runId={run.run_id} index={i} />
      ))}
    </div>
  )
}
