// Turns engine arrays into colours. Visualization only: values are mapped, never altered.
import type { SimulationResult } from '@/api/container'
import type { PlaneGridSampling } from '@/api/types'
import { absQuantile, diverging, logT, magneticSequential, sequential, symlogT, type LogScale } from './colormaps'

export interface Legend {
  kind: 'sequential' | 'diverging' | 'magnetic'
  symbol: string
  unit: string
  min: number
  max: number
  scale: 'log' | 'symlog'
  /** Divergence/curl maps: counts that let the legend state exact zeros explicitly. */
  zeroAware?: { exactZero: number; nonzero: number; undefined: number }
  samplingId: string
}

export interface HeatImage {
  pixels: Uint8ClampedArray
  width: number
  height: number
  grid: PlaneGridSampling
  legend: Legend
  /** Discrete maps are drawn without interpolation so no value is invented between samples. */
  nearest: boolean
}

export type ScalarKind = 'phi' | 'E' | 'div_E' | 'curl_E' | 'div_D' | 'curl_D' | 'B' | 'H' | 'div_B' | 'dB_dt' | 'E_ind' | 'B_prescribed' | 'B_passive'
export const isMagneticKind = (k: string) => k === 'B' || k === 'H' || k === 'div_B' || k === 'dB_dt' || k === 'E_ind' || k === 'B_prescribed' || k === 'B_passive'

export function sampling<T>(result: SimulationResult, id: string): T | undefined {
  return result.header.samplings.find((s) => s['id'] === id) as T | undefined
}

export function magnitudes(vectors: Float32Array): Float32Array {
  const n = vectors.length / 3
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    out[i] = Math.hypot(vectors[3 * i]!, vectors[3 * i + 1]!, vectors[3 * i + 2]!)
  }
  return out
}

/** Robust display range for magnitudes: 2nd..98th percentile, so the singular neighbourhood of
 *  a point charge does not flatten the rest of the picture. Values outside are clamped. */
export function magnitudeScale(mag: Float32Array): LogScale {
  const max = absQuantile(mag, 0.98, true)
  const min = Math.max(absQuantile(mag, 0.02, true), max * 1e-6)
  return { min, max }
}

export const UNDEFINED_COLOR = [20, 26, 40] as const
/** Colour of an exact zero in divergence and curl maps: distinct from "undefined" and from the
 *  background, so that "zero" is never read as "no data". */
export const ZERO_COLOR = [38, 70, 86] as const
export const ZERO_CSS = `rgb(${ZERO_COLOR.join(',')})`

const SYMBOLS: Record<ScalarKind, string> = {
  phi: 'φ', E: '|E|', div_E: '∇·E', curl_E: '|∇×E|', div_D: '∇·D', curl_D: '|∇×D|',
  B: '|B|', H: '|H|', div_B: '∇·B', dB_dt: '|∂B/∂t|', E_ind: '|E_ind|',
  B_prescribed: '|B_prescribed|', B_passive: '|B_passive|',
}

/** Per-sample scalar values of a map, read from the engine's arrays (never derived from E):
 *  φ, |E|, |B|, |H| from the fine slice grid, divergence and curl magnitude from the vector grid.
 *  With `contribution` (a current source id), |Bᵢ| or |Hᵢ| of that source alone, which the engine
 *  returns on the vector grid. */
export function scalarSamples(result: SimulationResult, kind: ScalarKind, samplingId?: string, contribution?: string): { values: Float32Array; unit: string; samplingId: string } | null {
  // 'all' shows the arrows of every source; a colour map can only show the total there.
  const single = contribution && contribution !== 'total' && contribution !== 'all' && (kind === 'B' || kind === 'H')
  const fine = kind === 'phi' || kind === 'E' || kind === 'B' || kind === 'H' || kind === 'dB_dt' || kind === 'E_ind' || kind === 'B_prescribed' || kind === 'B_passive'
  const id = samplingId ?? (single ? 'arrows' : fine ? 'heat' : 'arrows')
  const field = result.arrays[single ? `${id}.${kind}@${contribution}` : `${id}.${kind}`]
  if (!field) return null
  const vector = field.entry.components === 3
  return { values: vector ? magnitudes(field.data) : field.data, unit: field.entry.unit, samplingId: id }
}

export interface ScalarColoring {
  legend: Legend
  colorAt: (v: number, out: Uint8ClampedArray | number[], o: number) => void
}

/** Colour scale for a scalar map. Exact zeros of divergence/curl get ZERO_COLOR; there is no
 *  stretching of a zero field into an artificial gradient. */
export function scalarColoring(kind: ScalarKind, values: Float32Array, unit: string, samplingId: string): ScalarColoring {
  const put = (c: readonly number[], out: Uint8ClampedArray | number[], o: number) => {
    out[o] = c[0]!
    out[o + 1] = c[1]!
    out[o + 2] = c[2]!
  }
  const finiteAction = (fn: (v: number, out: Uint8ClampedArray | number[], o: number) => void) =>
    (v: number, out: Uint8ClampedArray | number[], o: number) => (Number.isFinite(v) ? fn(v, out, o) : put(UNDEFINED_COLOR, out, o))
  if (kind === 'phi') {
    const limit = absQuantile(values, 0.98)
    return {
      legend: { kind: 'diverging', symbol: SYMBOLS[kind], unit, min: -limit, max: limit, scale: 'symlog', samplingId },
      colorAt: finiteAction((v, out, o) => diverging(symlogT(v, limit), out, o)),
    }
  }
  if (kind === 'B' || kind === 'H' || kind === 'dB_dt' || kind === 'E_ind' || kind === 'B_prescribed' || kind === 'B_passive') {
    const scale = magnitudeScale(values)
    return {
      legend: { kind: 'magnetic', symbol: SYMBOLS[kind], unit, ...scale, scale: 'log', samplingId },
      colorAt: finiteAction((v, out, o) => magneticSequential(logT(v, scale), out, o)),
    }
  }
  if (kind === 'E') {
    const scale = magnitudeScale(values)
    return {
      legend: { kind: 'sequential', symbol: SYMBOLS[kind], unit, ...scale, scale: 'log', samplingId },
      colorAt: finiteAction((v, out, o) => sequential(logT(v, scale), out, o)),
    }
  }
  let exactZero = 0
  let nonzero = 0
  let undef = 0
  let maxAbs = 0
  for (const v of values) {
    if (!Number.isFinite(v)) undef++
    else if (v === 0) exactZero++
    else {
      nonzero++
      maxAbs = Math.max(maxAbs, Math.abs(v))
    }
  }
  const signed = kind === 'div_E' || kind === 'div_D' || kind === 'div_B'
  return {
    legend: {
      kind: signed ? 'diverging' : 'sequential',
      symbol: SYMBOLS[kind],
      unit,
      min: signed ? -maxAbs : 0,
      max: maxAbs,
      scale: signed ? 'symlog' : 'log',
      zeroAware: { exactZero, nonzero, undefined: undef },
      samplingId,
    },
    colorAt: finiteAction((v, out, o) => {
      if (v === 0) put(ZERO_COLOR, out, o)
      else if (signed) diverging(symlogT(v, maxAbs), out, o)
      else sequential(logT(v, { min: maxAbs * 1e-6, max: maxAbs }), out, o)
    }),
  }
}

export function heatImage(result: SimulationResult, kind: ScalarKind, contribution?: string): HeatImage | null {
  const samples = scalarSamples(result, kind, undefined, contribution)
  if (!samples) return null
  const grid = sampling<PlaneGridSampling>(result, samples.samplingId)
  if (!grid) return null
  const { legend, colorAt } = scalarColoring(kind, samples.values, samples.unit, samples.samplingId)
  const n = grid.nu * grid.nv
  const pixels = new Uint8ClampedArray(n * 4)
  for (let i = 0; i < n; i++) {
    colorAt(samples.values[i]!, pixels, 4 * i)
    pixels[4 * i + 3] = 255
  }
  return { pixels, width: grid.nu, height: grid.nv, grid, legend, nearest: legend.zeroAware !== undefined }
}
