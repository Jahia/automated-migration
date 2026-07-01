import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import RunList from './components/RunList'
import RunDetail from './components/RunDetail'
import SchemaViewer from './components/SchemaViewer'
import TokenCounter from './components/TokenCounter'

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-6">
          <Link to="/" className="text-lg font-bold text-blue-400 hover:text-blue-300">
            Orchestration Loop
          </Link>
          <Link to="/schema" className="text-sm text-gray-400 hover:text-gray-200">
            API Schema
          </Link>
          <div className="ml-auto">
            <TokenCounter />
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<RunList />} />
            <Route path="/runs/:runId" element={<RunDetail />} />
            <Route path="/schema" element={<SchemaViewer />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
