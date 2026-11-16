// Colours of the Gaussian-surface layers (display only; no value is changed).
import * as THREE from 'three'

export const FLUX_COLORS = { outward: '#fbbf24', inward: '#22d3ee', zero: '#a1a1aa', neutral: '#c4b5fd' } as const
export const CLASS_COLORS = { inside: '#34d399', outside: '#94a3b8', boundary: '#f87171', near: '#fbbf24' } as const

/** Per-vertex colours (3 vertices per triangle) from the E·n sign class and magnitude. */
export function fluxColors(en: Float32Array, cls: Float32Array, colorByFlux: boolean): Float32Array {
  const out = new Float32Array(en.length * 9)
  const c = new THREE.Color()
  let max = 0
  for (const v of en) if (Number.isFinite(v)) max = Math.max(max, Math.abs(v))
  for (let t = 0; t < en.length; t++) {
    if (!colorByFlux) c.set(FLUX_COLORS.neutral)
    else {
      const k = cls[t]!
      c.set(k > 0 ? FLUX_COLORS.outward : k < 0 ? FLUX_COLORS.inward : FLUX_COLORS.zero)
      if (k !== 0 && max > 0) {
        // Brightness follows log |E·n| over three decades (a display scale only).
        const t01 = Math.max(0, Math.min(1, 1 + Math.log10(Math.abs(en[t]!) / max) / 3))
        c.multiplyScalar(0.35 + 0.65 * t01)
      }
    }
    for (let v = 0; v < 3; v++) out.set([c.r, c.g, c.b], 9 * t + 3 * v)
  }
  return out
}

