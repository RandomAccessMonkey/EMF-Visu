import { describe, expect, it } from 'vitest'
import { formatPlain } from './format'

describe('formatPlain (derived units without SI prefixes)', () => {
  it('never puts a prefix in front of m², m³ or m⁻¹', () => {
    expect(formatPlain(0.0072, 'm²')).toBe('0.0072 m²')
    expect(formatPlain(100, 'm⁻¹')).toBe('100 m⁻¹')
    expect(formatPlain(1000, 'm⁻¹')).toBe('1000 m⁻¹')
    expect(formatPlain(2.5e-6, 'm²')).toBe('2.500e-6 m²')
    expect(formatPlain(3e7, 'm⁻¹', 3)).toBe('3.00e+7 m⁻¹')
  })

  it('handles zero and non-finite values', () => {
    expect(formatPlain(0, 'm²')).toBe('0 m²')
    expect(formatPlain(Number.NaN, 'm²')).toBe('—')
    expect(formatPlain(null, 'm²')).toBe('—')
  })
})
