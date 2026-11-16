import { describe, expect, it } from 'vitest'
import type { SimulationResult } from '@/api/container'
import type { ArrayEntry, PlaneGridSampling, ResultHeader } from '@/api/types'
import { formatNumber, formatSI, formatVector } from '@/lib/format'
import { partitionVectors, sourceMarkers } from './calculus'
import { heatImage, scalarSamples, UNDEFINED_COLOR, ZERO_COLOR } from './fieldImages'

const grid = (id: string, u: [number, number, number], v: [number, number, number], center: [number, number, number] = [0, 0, 0]): PlaneGridSampling => ({
  kind: 'plane_grid', id, center_m: center, u_dir: u, v_dir: v, u_extent_m: 2, v_extent_m: 2, nu: 3, nv: 3,
})

function entry(name: string, unit: string, components: number, shape: number[]): ArrayEntry {
  const [sampling_id, quantity] = name.split('.') as [string, string]
  return { name, sampling_id, quantity, symbol: quantity, unit, components, kind: 'field', stats: { min: 0, max: 0, non_finite_count: 0 }, dtype: '<f4', shape, offset: 0, byte_length: 0 }
}

/** A minimal result: a nonzero E on the vector grid and engine-provided divergence/curl. */
function fakeResult(div: number[], curl: number[], sources: ResultHeader['point_sources'] = [], heat = grid('heat', [1, 0, 0], [0, 1, 0])): SimulationResult {
  const arrows = grid('arrows', [1, 0, 0], [0, 1, 0])
  const e = new Float32Array(27).map((_, i) => 1 + i) // never zero
  const arrays = {
    'arrows.E': { entry: entry('arrows.E', 'V/m', 3, [3, 3, 3]), data: e },
    'arrows.div_E': { entry: entry('arrows.div_E', 'V/m^2', 1, [3, 3]), data: new Float32Array(div) },
    'arrows.curl_E': { entry: entry('arrows.curl_E', 'V/m^2', 3, [3, 3, 3]), data: new Float32Array(curl) },
  }
  const header = { samplings: [heat, arrows], point_sources: sources, arrays: Object.values(arrays).map((a) => a.entry) } as unknown as ResultHeader
  return { header, arrays, byteLength: 0 }
}

const zeros = (n: number) => Array.from({ length: n }, () => 0)

describe('divergence and curl maps are read from the engine, never derived from E', () => {
  it('an exactly zero divergence is painted in the zero colour although E is nonzero', () => {
    const img = heatImage(fakeResult(zeros(9), zeros(27)), 'div_E')!
    expect(img.grid.id).toBe('arrows')
    expect(img.nearest).toBe(true)
    expect(img.legend.zeroAware).toEqual({ exactZero: 9, nonzero: 0, undefined: 0 })
    for (let i = 0; i < 9; i++) expect(Array.from(img.pixels.slice(4 * i, 4 * i + 3))).toEqual([...ZERO_COLOR])
  })

  it('a sample on a charge is "undefined", not a spike', () => {
    const div = zeros(9)
    div[4] = NaN
    const img = heatImage(fakeResult(div, zeros(27)), 'div_E')!
    expect(img.legend.zeroAware).toEqual({ exactZero: 8, nonzero: 0, undefined: 1 })
    expect(Array.from(img.pixels.slice(16, 19))).toEqual([...UNDEFINED_COLOR])
    expect(img.legend.max).toBe(0) // no artificial colour range is invented
  })

  it('genuinely nonzero values (e.g. a future model) are coloured and counted, not hidden', () => {
    const div = zeros(9)
    div[0] = -2e-20
    div[8] = 3
    const img = heatImage(fakeResult(div, zeros(27)), 'div_E')!
    expect(img.legend.zeroAware).toEqual({ exactZero: 7, nonzero: 2, undefined: 0 })
    expect(Array.from(img.pixels.slice(0, 3))).not.toEqual([...ZERO_COLOR])
  })

  it('the curl-magnitude map is the magnitude of the engine curl vectors', () => {
    const curl = zeros(27)
    curl.splice(3, 3, 0, 3, 4)
    const s = scalarSamples(fakeResult(zeros(9), curl), 'curl_E')!
    expect(Array.from(s.values)).toEqual([0, 5, 0, 0, 0, 0, 0, 0, 0])
    expect(s.unit).toBe('V/m^2')
  })
})

describe('curl glyphs', () => {
  it('separates exact zero vectors, nonzero vectors and undefined samples', () => {
    const vectors = new Float32Array([0, 0, 0, 0, -0, 0, 1e-30, 0, 0, NaN, NaN, NaN])
    const parts = partitionVectors({ points: new Float32Array(12), vectors, cell: 1 })
    expect(parts).toEqual({ zero: [0, 1], nonzero: [2], undef: 1 })
  })
})

describe('source markers in the 2D cross-section', () => {
  const src = (object_id: string, q: number, pos: [number, number, number], d: number, inPlane: boolean) => ({
    object_id, position_m: pos, charge_C: q, div_E_weight_V_m: q / 8.8541878128e-12, div_D_weight_C: q,
    plane_distance_m: { heat: d }, in_plane: { heat: inPlane },
  })

  it('in-slice charges are normal markers; off-slice charges are projected ghosts with their offset', () => {
    const r = fakeResult(zeros(9), zeros(27), [src('a', 1e-9, [0.2, 0, 0], 0, true), src('b', -2e-9, [0.5, 0.1, 0.7], 0.7, false)])
    const [a, b] = sourceMarkers(r, '2d', { a: 'q1' })
    expect(a).toMatchObject({ name: 'q1', ghost: false, shownAt: [0.2, 0, 0] })
    expect(b).toMatchObject({ name: 'b', ghost: true, axis: 'z', delta: 0.7, divDWeight: -2e-9 })
    expect(b!.shownAt).toEqual([0.5, 0.1, 0]) // projected onto the slice
    expect(b!.position).toEqual([0.5, 0.1, 0.7]) // the true position is kept
  })

  it('uses the slice normal u × v for xz slices (normal −y)', () => {
    const heat = grid('heat', [1, 0, 0], [0, 0, 1], [0, 0.2, 0])
    const r = fakeResult(zeros(9), zeros(27), [src('b', 1e-9, [0.1, 0.5, 0.3], -0.3, false)], heat)
    const [b] = sourceMarkers(r, '2d', {})
    expect(b!.axis).toBe('y')
    expect(b!.delta).toBeCloseTo(0.3) // y_charge − y_slice
    expect(b!.shownAt[1]).toBeCloseTo(0.2)
  })

  it('in 3D every source is drawn at its true position', () => {
    const r = fakeResult(zeros(9), zeros(27), [src('b', 1e-9, [0.5, 0.1, 0.7], 0.7, false)])
    expect(sourceMarkers(r, '3d', {})[0]).toMatchObject({ ghost: false, shownAt: [0.5, 0.1, 0.7] })
  })
})

describe('near-zero formatting', () => {
  it('shows exact zeros as 0 and never rounds small nonzero values to 0', () => {
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(-0)).toBe('0')
    expect(formatNumber(1.234e-22)).toBe('1.234e-22')
    expect(formatVector([0, 0, 0])).toBe('(0, 0, 0)')
    expect(formatVector([0, 2.5e-13, 0])).toBe('(0, 2.500e-13, 0)')
    expect(formatSI(0, 'V/m²')).toBe('0 V/m²')
    expect(formatSI(3e-15, 'C')).not.toMatch(/^0 /)
  })
})
