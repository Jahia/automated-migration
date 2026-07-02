import type { RunState, StepState } from '../../types'
import { FidelityGate } from '../fidelity/FidelityGate'
import { ComponentModelView } from './ComponentModelView'
import { ScopeGate } from './ScopeGate'
import { ContentGate } from './ContentGate'
import { GoLiveGate } from './GoLiveGate'

/**
 * The right-hand cockpit panel. When a step is HALTed for review, its `gate_type`
 * selects the typed gate; otherwise the component model is the default view.
 */
export function MigrationStage({
  run,
  gateStep,
  onApproved,
}: {
  run: RunState
  gateStep?: StepState
  onApproved: () => void
}) {
  const id = run.run_id
  switch (gateStep?.gate_type) {
    case 'scope':
      return <ScopeGate runId={id} onApproved={onApproved} />
    case 'fidelity':
      return <FidelityGate runId={id} stepId={gateStep.id} onApproved={onApproved} />
    case 'content':
      return <ContentGate runId={id} onApproved={onApproved} />
    case 'golive':
      return <GoLiveGate runId={id} onApproved={onApproved} />
    case 'model':
    default:
      return <ComponentModelView runId={id} />
  }
}
