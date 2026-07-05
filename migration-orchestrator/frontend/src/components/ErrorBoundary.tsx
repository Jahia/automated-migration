import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * Defense-in-depth for the run UI: a single component reading `.length`/`.map`
 * off an undefined artifact field used to blank the ENTIRE page (observed live —
 * KpiBar on a manifest with no `templates`). This boundary contains the crash to
 * a fallback panel so the rest of the UI (nav, other runs) stays usable, and
 * re-throws to console.error so the Playwright smoke test still catches it.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // keep the signal visible to the smoke test + operator console
    console.error(`ErrorBoundary caught in ${this.props.label ?? 'UI'}:`, error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-4 rounded-lg border border-red-700 bg-red-900/30 p-4 text-sm text-red-200">
          <div className="mb-1 font-bold">Panneau non affichable</div>
          <div className="opacity-80">
            {this.props.label ? `${this.props.label}: ` : ''}
            {this.state.error.message}
          </div>
          <div className="mt-2 text-xs opacity-60">
            Le reste de l'interface reste utilisable. Détail dans la console.
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
