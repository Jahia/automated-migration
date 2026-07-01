import { useEffect, useState } from 'react'

interface Stats {
  input: number
  output: number
  reasoning: number
  cache_read: number
  cache_write: number
  cost: number
  sessions: number
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

export default function TokenCounter() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    const load = () => {
      fetch('/stats')
        .then((r) => r.json())
        .then(setStats)
        .catch(() => {})
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  if (!stats) return null

  return (
    <div className="flex items-center gap-4 text-xs font-mono text-gray-400">
      <span title="Input tokens">IN: <span className="text-blue-400">{formatNum(stats.input)}</span></span>
      <span title="Output tokens">OUT: <span className="text-green-400">{formatNum(stats.output)}</span></span>
      <span title="Cache hits">CACHE: <span className="text-purple-400">{formatNum(stats.cache_read)}</span></span>
      <span title="Coût total">${stats.cost.toFixed(2)}</span>
    </div>
  )
}
