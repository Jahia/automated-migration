import type { RunState, StepState } from '../../types'
import { FidelityGate } from '../fidelity/FidelityGate'
import { ComponentModelView } from './ComponentModelView'
import { ScopeGate } from './ScopeGate'
import { MirrorGate } from './MirrorGate'
import { ContentGate } from './ContentGate'
import { GoLiveGate } from './GoLiveGate'
import { EmptyArtifact } from './GateShell'
import { MIGRATION_PHASES } from './types'

type Panel = 'scope' | 'mirror' | 'model' | 'fidelity' | 'content' | 'golive' | null

function panelForPhase(key?: string | null): Panel {
  switch (key) {
    case 'capture':
    case 'analyze':
      return 'scope'
    case 'mirror':
      return 'mirror'
    case 'model':
    case 'implement':
      return 'model'
    case 'fidelity':
      return 'fidelity'
    case 'content':
      return 'content'
    case 'golive':
      return 'golive'
    default:
      return null
  }
}

function panelForGate(gt?: string | null): Panel {
  switch (gt) {
    case 'scope':
      return 'scope'
    case 'mirror':
      return 'mirror'
    case 'model':
      return 'model'
    case 'fidelity':
      return 'fidelity'
    case 'content':
      return 'content'
    case 'golive':
      return 'golive'
    default:
      return null
  }
}

function renderPanel(
  panel: Panel,
  o: { runId: string; project?: string | null; readOnly: boolean; stepId?: string; onApproved: () => void },
) {
  switch (panel) {
    case 'scope':
      return <ScopeGate runId={o.runId} project={o.project} onApproved={o.onApproved} readOnly={o.readOnly} />
    case 'mirror':
      return <MirrorGate runId={o.runId} project={o.project} onApproved={o.onApproved} readOnly={o.readOnly} />
    case 'model':
      return <ComponentModelView runId={o.runId} project={o.project} />
    case 'fidelity':
      return <FidelityGate runId={o.runId} project={o.project} stepId={o.stepId} onApproved={o.onApproved} readOnly={o.readOnly} />
    case 'content':
      return <ContentGate runId={o.runId} onApproved={o.onApproved} readOnly={o.readOnly} />
    case 'golive':
      return <GoLiveGate runId={o.runId} project={o.project} onApproved={o.onApproved} readOnly={o.readOnly} />
    default:
      return <EmptyArtifact label="No dedicated view for this phase." />
  }
}

/**
 * The right-hand cockpit panel. Three modes:
 *  - a phase explicitly selected in the rail → review that phase's artifacts
 *    (read-only, unless it is the currently-active gate → actionable);
 *  - else an active HALT gate → its typed gate (actionable);
 *  - else the component model (default).
 */
export function MigrationStage({
  run,
  gateStep,
  selectedPhase,
  onClearPhase,
  onApproved,
}: {
  run: RunState
  gateStep?: StepState
  selectedPhase?: string | null
  onClearPhase?: () => void
  onApproved: () => void
}) {
  const id = run.run_id
  const steps = run.epics.flatMap((e) => e.stories).flatMap((s) => s.steps)
  const fidelityStepId = steps.find((s) => s.gate_type === 'fidelity' || /reconstruct|fidelity/i.test(s.id))?.id
  const gatePanel = panelForGate(gateStep?.gate_type)

  if (selectedPhase) {
    const panel = panelForPhase(selectedPhase)
    const isLiveGate = !!gateStep && panel === gatePanel
    const phaseTitle = MIGRATION_PHASES.find((p) => p.key === selectedPhase)?.title ?? selectedPhase
    return (
      <div>
        {!isLiveGate && (
          <div className="mb-3 flex items-center justify-between rounded-md border border-[#c7d0da] bg-[#f6f9fb] px-3 py-2 text-[12px] text-[#3d556c]">
            <span>
              <b className="text-[#001932]">Revue · {phaseTitle}</b> · lecture seule
            </span>
            <button onClick={onClearPhase} className="font-semibold text-[#0077bf] hover:underline">
              {gateStep ? 'Revenir au gate actif' : 'Fermer'} ✕
            </button>
          </div>
        )}
        {renderPanel(panel, { runId: id, project: run.project, readOnly: !isLiveGate, stepId: fidelityStepId, onApproved })}
      </div>
    )
  }

  if (gateStep) {
    return renderPanel(gatePanel ?? 'model', { runId: id, project: run.project, readOnly: false, stepId: gateStep.id, onApproved })
  }
  return <ComponentModelView runId={id} project={run.project} />
}
