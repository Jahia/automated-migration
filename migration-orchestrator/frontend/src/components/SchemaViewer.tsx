import { useEffect, useState } from 'react'
import { fetchSchema } from '../api'

export default function SchemaViewer() {
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSchema().then((data) => {
      setSchema(data)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="text-gray-400">Chargement...</div>
  if (!schema) return <div className="text-gray-500">Erreur de chargement</div>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">API Schema</h1>
      <p className="text-gray-400 text-sm mb-4">
        Contrat d'interface pour l'endpoint <code>POST /runs</code>.
        Ce JSON peut être envoyé à un LLM pour qu'il génère des plans conformes.
      </p>
      <pre className="bg-gray-900 border border-gray-800 rounded p-4 text-xs text-gray-300 overflow-auto max-h-[80vh]">
        {JSON.stringify(schema, null, 2)}
      </pre>
    </div>
  )
}
