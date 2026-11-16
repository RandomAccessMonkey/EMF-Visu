// Turns engine arrays into colours. Visualization only: values are mapped, never altered.
import type { SimulationResult } from '@/api/container'
import type { PlaneGridSampling } from '@/api/types'
import { absQuantile, diverging, logT, sequential, symlogT, type LogScale } from './colormaps'

export interface Legend {
  kind: 'sequential' | 'diverging'
  symbol: string
  unit: string
  min: number
  max: number
  scale: 'log' | 'symlog'
}

export interface HeatImage {
  pixels: Uint8ClampedArray
  width: number
  height: number
  grid: PlaneGridSampling
  legend: Legend
}

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

const UNDEFINED_COLOR = [20, 26, 40] as const

export function heatImage(result: SimulationResult, kind: 'phi' | 'E'): HeatImage | null {
  const grid = sampling<PlaneGridSampling>(result, 'heat')
  const field = result.arrays[kind === 'phi' ? 'heat.phi' : 'heat.E']
  if (!grid || !field) return null
  const n = grid.nu * grid.nv
  const pixels = new Uint8ClampedArray(n * 4)
  let legend: Legend
  let values: Float32Array // one scalar per pixel; non-finite = undefined (singular point)
  let colorAt: (i: number) => void
  if (kind === 'phi') {
    values = field.data
    const limit = absQuantile(values, 0.98)
    legend = { kind: 'diverging', symbol: 'φ', unit: field.entry.unit, min: -limit, max: limit, scale: 'symlog' }
    colorAt = (i) => diverging(symlogT(values[i]!, limit), pixels, 4 * i)
  } else {
    values = magnitudes(field.data)
    const scale = magnitudeScale(values)
    legend = { kind: 'sequential', symbol: '|E|', unit: field.entry.unit, ...scale, scale: 'log' }
    colorAt = (i) => sequential(logT(values[i]!, scale), pixels, 4 * i)
  }
  for (let i = 0; i < n; i++) {
    if (Number.isFinite(values[i]!)) colorAt(i)
    else pixels.set(UNDEFINED_COLOR, 4 * i)
    pixels[4 * i + 3] = 255
  }
  return { pixels, width: grid.nu, height: grid.nv, grid, legend }
}
