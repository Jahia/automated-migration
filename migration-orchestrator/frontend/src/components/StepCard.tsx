import { useState, useEffect } from 'react'
import AgentOutput from './AgentOutput'
import QuestionPanel from './QuestionPanel'
import type { StepState } from '../types'

interface Props {
  step: StepState
  runId: string
  index: number
}

const statusIcons: Record<string, string> = {
  pending: '⏳',
  ready: '⏳',
  running: '🔄',
  verifying: '🔄',
  done: '✅',
  failed: '❌',
  blocked: '🚫',
  waiting_human: '❓',
  halted: '🚨',
}

const statusBadges: Record<string, string> = {
  pending: 'bg-gray-800 text-gray-400',
  ready: 'bg-gray-800 text-gray-300',
  running: 'bg-blue-900 text-blue-300',
  verifying: 'bg-orange-900 text-orange-300',
  done: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
  blocked: 'bg-red-950 text-red-400',
  waiting_human: 'bg-yellow-900 text-yellow-300',
  halted: 'bg-red-950 text-red-300',
}

const taskTypeColors: Record<string, string> = {
  analyze: 'border-purple-700',
  implement: 'border-blue-700',
  review: 'border-orange-700',
  test: 'border-green-700',
  refactor: 'border-cyan-700',
  security_check: 'border-red-700',
}

export default function StepCard({ step, runId, index }: Props) {
  const [expanded, setExpanded] = useState(step.status === 'running' || step.status === 'waiting_human')
  const hasOutput = step.streaming_text || step.agent_result
  const isActive = step.status === 'running' || step.status === 'verifying'
  const borderColor = taskTypeColors[step.task_type] || 'border-gray-700'

  useEffect(() => {
    if (step.status === 'running' || step.status === 'waiting_human') {
      setExpanded(true)
    }
  }, [step.status])

  return (
    <div className={`border-l-2 pl-3 py-1 ${borderColor}`}>
      <div className="flex items-center gap-2">
        <span className="text-sm">{statusIcons[step.status]}</span>
        <span className="text-xs font-mono text-gray-400">{step.task_type}</span>
        {step.agent !== 'code' && (
          <span className="text-xs text-purple-400">@{step.agent}</span>
        )}
        <span className={`px-1.5 py-0.5 rounded text-xs ${statusBadges[step.status] || 'text-gray-500'}`}>
          {step.status}
        </span>
        {step.attempt > 0 && (
          <span className="text-xs text-gray-500">(attempt {step.attempt})</span>
        )}
        <span className="text-xs text-gray-600 truncate flex-1">{step.title}</span>
        {isActive && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-500 hover:text-gray-300 ml-auto"
          >
            {expanded ? '[-]' : '[+]'}
          </button>
        )}
        {!isActive && hasOutput && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-500 hover:text-gray-300 ml-auto"
          >
            {expanded ? '[-]' : '[+]'}
          </button>
        )}
      </div>

      {/* Résumé toujours visible pour les steps terminées */}
      {step.status === 'done' && step.agent_result && step.agent_result.summary && (
        <div className="mt-1 text-xs text-gray-400 ml-6 border-l-2 border-green-800/50 pl-2 italic">
          {step.agent_result.summary.length > 300
            ? step.agent_result.summary.slice(0, 300) + '...'
            : step.agent_result.summary}
          {step.tokens_in > 0 && (
            <div className="mt-1 text-gray-500 not-italic">
              IN: {(step.tokens_in/1000).toFixed(1)}K · OUT: {(step.tokens_out/1000).toFixed(1)}K
              {step.tokens_cache > 0 && ` · CACHE: ${(step.tokens_cache/1000).toFixed(1)}K`}
              {' · '}${step.cost.toFixed(4)}
            </div>
          )}
        </div>
      )}

      {step.status === 'failed' && step.agent_result && step.agent_result.summary && (
        <div className="mt-1 text-xs text-red-400 ml-6 border-l-2 border-red-800/50 pl-2 italic">
          {step.agent_result.summary.length > 200
            ? step.agent_result.summary.slice(0, 200) + '...'
            : step.agent_result.summary}
        </div>
      )}

      {expanded && step.status === 'waiting_human' && step.question && (
        <div className="mt-2">
          <QuestionPanel question={step.question} runId={runId} />
        </div>
      )}

      {(expanded && (hasOutput || isActive)) && step.status !== 'waiting_human' && step.status !== 'done' && (
        <div className="mt-2">
          <AgentOutput step={step} />
        </div>
      )}

      {expanded && step.status === 'done' && hasOutput && (
        <div className="mt-2">
          <AgentOutput step={step} />
        </div>
      )}
    </div>
  )
}
