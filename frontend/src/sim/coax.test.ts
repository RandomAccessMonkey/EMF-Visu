import { describe, expect, it } from 'vitest'
import type { CoaxSpec } from '@/api/types'
import { divergingColor, radialScale } from '@/render/CoaxLayer'
import { sanitizeView } from '@/state/viewStore'
import { coaxProbe, DEFAULT_COAX, validateCoax } from './coax'

const withGeo = (g: Partial<CoaxSpec['geometry']>): CoaxSpec => ({ ...DEFAULT_COAX, geometry: { ...DEFAULT_COAX.geometry, ...g } })
const keys = (s: CoaxSpec, start = 0, end = 25e-9) => validateCoax(s, start, end).map((i) => i.key)

describe('coaxial cable validation', () => {
  it('accepts the default cable (preset geometry)', () => {
    expect(keys(DEFAULT_COAX)).toEqual([])
  })
  it('enforces 0 < a < b < c and L > 0', () => {
    expect(keys(withGeo({ inner_radius_m: 2e-3 }))).toContain('coax.err.ab')
    expect(keys(withGeo({ inner_radius_m: 1.67e-3 }))).toContain('coax.err.ab')
    expect(keys(withGeo({ shield_outer_radius_m: 1.67e-3 }))).toContain('coax.err.bc')
    expect(keys(withGeo({ inner_radius_m: 0 }))).toEqual(['coax.err.positive'])
    expect(keys(withGeo({ length_m: -1 }))).toEqual(['coax.err.positive'])
    expect(keys(withGeo({ length_m: Number.NaN }))).toEqual(['coax.err.positive'])
    expect(keys(withGeo({ inner_radius_m: 1.67e-3 * (1 - 1e-9) }))).toContain('coax.err.ratio')
  })
  it('enforces positive εr, μr and meaningful excitation parameters', () => {
    expect(keys({ ...DEFAULT_COAX, material: { relative_permittivity: 0, relative_permeability: 1 } })).toEqual(['coax.err.material'])
    expect(keys({ ...DEFAULT_COAX, material: { relative_permittivity: 2, relative_permeability: -1 } })).toEqual(['coax.err.material'])
    expect(keys({ ...DEFAULT_COAX, excitation: { type: 'sinusoidal', amplitude_V: 1, frequency_Hz: 0 } })).toEqual(['coax.err.frequency'])
    expect(keys({ ...DEFAULT_COAX, excitation: { type: 'gaussian', amplitude_V: 1, center_s: 1e-9, width_s: 0 } })).toEqual(['coax.err.pulse'])
    expect(keys({ ...DEFAULT_COAX, excitation: { type: 'gaussian', amplitude_V: Number.POSITIVE_INFINITY, center_s: 1e-9, width_s: 1e-9 } })).toEqual(['coax.err.amplitude'])
  })
  it('requires a non-empty time range', () => {
    expect(keys(DEFAULT_COAX, 1e-9, 1e-9)).toEqual(['coax.err.time'])
    expect(keys(DEFAULT_COAX, 2e-9, 1e-9)).toEqual(['coax.err.time'])
  })
})

describe('coaxial cable display helpers', () => {
  it('probes only in the 2D cross-section', () => {
    expect(coaxProbe('2d', [1e-3, 2e-4, 0])).toEqual([1e-3, 2e-4])
    expect(coaxProbe('3d', [1e-3, 2e-4, 0])).toBeNull()
    expect(coaxProbe('2d', null)).toBeNull()
  })
  it('colours V(z) on a symmetric diverging scale', () => {
    const pos = divergingColor(1, 1)
    const neg = divergingColor(-1, 1)
    const zero = divergingColor(0, 1)
    expect(pos.r).toBeGreaterThan(pos.b)
    expect(neg.b).toBeGreaterThan(neg.r)
    expect(divergingColor(5, 1).equals(pos)).toBe(true) // clamped
    expect(divergingColor(0.3, 0).equals(zero)).toBe(true) // no scale: neutral
  })
  it('states the radial magnification of the 3D view', () => {
    expect(radialScale(DEFAULT_COAX.geometry)).toBeCloseTo(120, 9)
    expect(radialScale({ ...DEFAULT_COAX.geometry, length_m: 0.01 })).toBe(1)
  })
  it('loads saved cross-section positions within the cable', () => {
    expect(sanitizeView({ coaxZFraction: 3 }).coaxZFraction).toBe(1)
    expect(sanitizeView({ coaxZFraction: -1 }).coaxZFraction).toBe(0)
    expect(sanitizeView({ coaxShowPoynting: 'yes' }).coaxShowPoynting).toBeUndefined()
  })
})
