import { useState } from 'react'
import { answerQuestion } from '../api'
import type { HumanQuestion } from '../types'

interface Props {
  question: HumanQuestion
  runId: string
}

export default function QuestionPanel({ question, runId }: Props) {
  const [customAnswer, setCustomAnswer] = useState('')
  const [sending, setSending] = useState(false)

  const handleAnswer = async (answer: string) => {
    setSending(true)
    try {
      await answerQuestion(runId, question.step_id, answer)
    } finally {
      setSending(false)
    }
  }

  const handleCustomSubmit = () => {
    if (customAnswer.trim()) {
      handleAnswer(customAnswer.trim())
      setCustomAnswer('')
    }
  }

  return (
    <div className="bg-yellow-900/20 border border-yellow-700 rounded p-3">
      <p className="text-yellow-200 text-sm mb-2">{question.question}</p>

      {question.options.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {question.options.map((opt, i) => (
            <button
              key={i}
              onClick={() => handleAnswer(opt.value)}
              disabled={sending}
              className="px-3 py-1 bg-yellow-800 hover:bg-yellow-700 disabled:opacity-40 rounded text-xs"
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={customAnswer}
          onChange={(e) => setCustomAnswer(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCustomSubmit()}
          placeholder="Réponse libre..."
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
        />
        <button
          onClick={handleCustomSubmit}
          disabled={sending || !customAnswer.trim()}
          className="px-3 py-1 bg-yellow-700 hover:bg-yellow-600 disabled:opacity-40 rounded text-xs"
        >
          Envoyer
        </button>
      </div>
    </div>
  )
}
