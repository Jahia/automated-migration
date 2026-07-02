import { useCallback, useRef, useState } from 'react'

interface Props {
  before: string // SOURCE image url (revealed on the left)
  after: string // RECONSTRUCTION image url (underneath)
  beforeLabel?: string
  afterLabel?: string
}

/**
 * Drag-to-compare slider: SOURCE (top layer, clipped from the left) over
 * RECONSTRUCTION (bottom layer). The reconstruction image is in normal flow so
 * the container takes the image's FULL scaled height (whole page, not a cropped
 * viewport); the source overlays it pixel-for-pixel and a clip-path reveals
 * `pos%`. Pointer-driven, keyboard-accessible via the range input.
 */
export function BeforeAfterSlider({
  before,
  after,
  beforeLabel = 'source',
  afterLabel = 'reconstruction',
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState(50)
  const [drag, setDrag] = useState(false)

  const moveTo = useCallback((clientX: number) => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos(Math.max(2, Math.min(98, ((clientX - r.left) / r.width) * 100)))
  }, [])

  return (
    <div
      ref={ref}
      className="relative overflow-hidden select-none cursor-ew-resize bg-[#e7ecf1]"
      onPointerDown={(e) => {
        setDrag(true)
        moveTo(e.clientX)
        try {
          ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
        } catch {
          /* noop */
        }
      }}
      onPointerMove={(e) => drag && moveTo(e.clientX)}
      onPointerUp={() => setDrag(false)}
    >
      {/* reconstruction in normal flow → defines the full (scaled) page height */}
      <img src={after} alt={afterLabel} draggable={false} className="block w-full" />
      {/* source on top, clipped to reveal the left `pos%` */}
      <img
        src={before}
        alt={beforeLabel}
        draggable={false}
        className="absolute left-0 top-0 block w-full"
        style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
      />

      {/* divider handle */}
      <div
        className="absolute top-0 bottom-0 z-10 w-0.5 bg-[#0077bf]"
        style={{ left: `${pos}%`, boxShadow: '0 0 8px #0077bf' }}
        aria-hidden
      >
        <span className="absolute top-1/2 left-1/2 grid h-6 w-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#0077bf] text-[11px] font-bold text-white">
          ↔
        </span>
      </div>

      <span className="absolute left-1.5 top-1.5 z-20 rounded bg-white/85 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-[#001932]">
        {beforeLabel}
      </span>
      <span className="absolute right-1.5 top-1.5 z-20 rounded bg-[#0077bf] px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider text-white">
        {afterLabel}
      </span>

      {/* accessible control */}
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        aria-label="Compare source and reconstruction"
        onChange={(e) => setPos(Number(e.target.value))}
        className="absolute inset-x-0 bottom-0 z-20 w-full opacity-0"
      />
    </div>
  )
}
