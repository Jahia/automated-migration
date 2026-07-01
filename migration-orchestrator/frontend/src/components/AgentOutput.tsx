import { useEffect, useRef } from 'react'
import type { StepState } from '../types'

interface Props {
  step: StepState
}

export default function AgentOutput({ step }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const showStreaming = step.status === 'running' || step.status === 'verifying'
  const isEmpty = !step.streaming_text && !step.agent_result

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [step.streaming_text, step.agent_result])

  return (
    <div className="bg-gray-900 border border-gray-800 rounded p-3 mt-1">
      {step.streaming_text && (
        <div ref={scrollRef} className="max-h-96 overflow-y-auto">
          <pre className="text-xs font-mono text-gray-200 whitespace-pre-wrap leading-relaxed">
            {step.streaming_text}
            {step.status === 'running' && <span className="animate-pulse text-blue-400">▌</span>}
          </pre>
        </div>
      )}
      {isEmpty && showStreaming && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          En attente de la réponse du LLM...
        </div>
      )}
      {isEmpty && !showStreaming && step.agent_result && (
        <div className="max-h-96 overflow-y-auto">
          <pre className="text-xs font-mono text-gray-400 whitespace-pre-wrap">{step.agent_result.summary}</pre>
        </div>
      )}
      {step.agent_result?.modified_files && step.agent_result.modified_files.length > 0 && (
        <div className="mt-2 text-xs text-gray-500 border-t border-gray-800 pt-2">
          Fichiers: {step.agent_result.modified_files.join(', ')}
        </div>
      )}
      {step.agent_result?.risks && step.agent_result.risks.length > 0 && (
        <div className="mt-1 text-xs text-yellow-600">
          Risques: {step.agent_result.risks.join(', ')}
        </div>
      )}
    </div>
  )
}
