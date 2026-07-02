// Domain types for the Fidelity gate — mirrors the JSON written by
// orchestration/lib/reconstruct_probe.mjs (workflow-output/reconstruct/reconstruct.json).

export interface OrphanSample {
  tag: string
  cls: string
  text: string
  ignorable: boolean // cookie-consent / a11y chrome — not an extraction failure
}

export interface ReconstructPage {
  slug: string
  url: string
  ok: boolean
  error?: string
  nComps?: number
  contentCoverage?: number // GATE metric: % of visible text captured by components
  realOrphanChars?: number
  ignorableChars?: number
  pixelSimilarity?: number // components-only render vs source (template/asset gap = 100 - this)
  dims?: string
  pass?: boolean
  orphanSamples?: OrphanSample[]
  local?: boolean          // rendered from the local mirror (offline)
  reconHtml?: string       // workflow-output-relative path to the interactive reconstruction
  mirrorPage?: string | null // workflow-output-relative path to the faithful local page
}

export interface ReconstructReport {
  project: string
  threshold: number
  pages: ReconstructPage[]
}
