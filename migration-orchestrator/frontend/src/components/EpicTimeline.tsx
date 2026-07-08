import EpicCard from './EpicCard'
import type { RunState, StepProvenance } from '../types'

interface Props {
  run: RunState
  provenance?: Record<string, StepProvenance>
}

export default function EpicTimeline({ run, provenance }: Props) {
  return (
    <div className="space-y-6">
      {run.epics.map((epic, i) => (
        <EpicCard key={epic.id} epic={epic} runId={run.run_id} index={i} provenance={provenance} />
      ))}
    </div>
  )
}
