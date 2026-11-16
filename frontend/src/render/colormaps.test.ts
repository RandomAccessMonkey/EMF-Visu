import { describe, expect, it } from 'vitest'
import { absQuantile, logT, symlogT } from './colormaps'
import { magnitudes, magnitudeScale } from './fieldImages'

describe('display scales (visualization only)', () => {
  it('symlog is odd, monotonic and centred on zero', () => {
    expect(symlogT(0, 10)).toBe(0.5)
    expect(symlogT(10, 10)).toBeCloseTo(1)
    expect(symlogT(-10, 10)).toBeCloseTo(0)
    expect(symlogT(3, 10) - 0.5).toBeCloseTo(0.5 - symlogT(-3, 10))
    expect(symlogT(2, 10)).toBeLessThan(symlogT(3, 10))
    expect(symlogT(1e9, 10)).toBe(1)
  })
  it('log scale maps the range ends to 0 and 1', () => {
    expect(logT(1, { min: 1, max: 100 })).toBe(0)
    expect(logT(10, { min: 1, max: 100 })).toBeCloseTo(0.5)
    expect(logT(0, { min: 1, max: 100 })).toBe(0)
  })
  it('quantiles ignore undefined (NaN) samples and never alter the data', () => {
    const a = new Float32Array([1, NaN, 3, 2, Infinity, 4])
    const copy = Array.from(a)
    expect(absQuantile(a, 1)).toBe(4)
    expect(absQuantile(a, 0)).toBe(1)
    expect(Array.from(a)).toEqual(copy)
  })
  it('magnitudes are Euclidean norms and the scale is ordered', () => {
    const m = magnitudes(new Float32Array([3, 4, 0, 0, 0, 2, NaN, 0, 0]))
    expect(m[0]).toBe(5)
    expect(m[1]).toBe(2)
    expect(Number.isNaN(m[2]!)).toBe(true)
    const s = magnitudeScale(m)
    expect(s.min).toBeLessThanOrEqual(s.max)
  })
})
