import { BrowserRouter, Routes, Route, Link, NavLink } from 'react-router-dom'
import { useState } from 'react'
import RunList from './components/RunList'
import RunDetail from './components/RunDetail'
import SchemaViewer from './components/SchemaViewer'
import Zoning from './components/Zoning'
import TokenCounter from './components/TokenCounter'
import { ErrorBoundary } from './components/ErrorBoundary'

// The real light Jahia wordmark (from jahia.com). Falls back to a text wordmark offline.
const JAHIA_LOGO = 'https://cdfoqfniea.cloudimg.io/https://www.jahia.com/modules/jahiacom/dist/assets/jahia-light-kFJWkPOB.svg'

function Logo() {
  const [broken, setBroken] = useState(false)
  if (broken) return <span className="text-lg font-extrabold tracking-tight text-white">JAHIA</span>
  return <img src={JAHIA_LOGO} alt="Jahia" className="h-[22px] w-auto" onError={() => setBroken(true)} />
}

function navClass({ isActive }: { isActive: boolean }) {
  return `text-sm font-medium transition ${isActive ? 'text-white' : 'text-[#a8c1d6] hover:text-white'}`
}

export default function App() {
  return (
    <BrowserRouter basename="/app">
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="flex items-center gap-5 border-b border-[#0a3252] bg-[#001932] px-6 py-3">
          <Link to="/" className="flex items-center gap-3">
            <Logo />
            <span className="hidden text-[11px] font-bold uppercase tracking-[2px] text-[#5e88ad] sm:inline">
              Migration Cockpit
            </span>
          </Link>
          <span className="h-5 w-px bg-[#0a3252]" />
          <NavLink to="/" end className={navClass}>Runs</NavLink>
          <NavLink to="/zoning" className={navClass}>Zoning</NavLink>
          <NavLink to="/schema" className={navClass}>API Schema</NavLink>
          <div className="ml-auto">
            <TokenCounter />
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-6">
          <Routes>
            <Route path="/" element={<ErrorBoundary label="Run list"><RunList /></ErrorBoundary>} />
            <Route path="/runs/:runId" element={<ErrorBoundary label="Run detail"><RunDetail /></ErrorBoundary>} />
            <Route path="/zoning" element={<ErrorBoundary label="Zoning"><Zoning /></ErrorBoundary>} />
            <Route path="/schema" element={<ErrorBoundary label="Schema"><SchemaViewer /></ErrorBoundary>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
