const PREFIXES: [number, string][] = [
  [1e12, 'T'], [1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''], [1e-3, 'm'], [1e-6, 'µ'],
  [1e-9, 'n'], [1e-12, 'p'], [1e-15, 'f'],
]

/** Format an SI value with a metric prefix, e.g. 8987.55 V/m -> "8.99 kV/m". */
export function formatSI(value: number | null | undefined, unit: string, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value === 0) return `0 ${unit}`
  const abs = Math.abs(value)
  // Compound units with exponents (C/m^2, …) read badly with prefixes: use scientific notation.
  if (unit.includes('^') || abs >= 1e15 || abs < 1e-15) {
    return `${value.toExponential(digits - 1)} ${unit}`
  }
  const [factor, prefix] = PREFIXES.find(([f]) => abs >= f) ?? PREFIXES[PREFIXES.length - 1]!
  return `${(value / factor).toPrecision(digits)} ${prefix}${unit}`
}

export const prettyUnit = (unit: string) => unit.replace(/\^2/g, '²').replace(/\^3/g, '³')

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

/** A single number in scientific notation, with exact zero shown as "0". Never rounds a small
 *  nonzero value to zero. */
/** A value in a derived unit that must not take an SI prefix (m², m³, m⁻¹: "k" or "m" in front
 *  of them would be read as part of the base unit, e.g. km⁻¹ = (km)⁻¹). Plain decimal for
 *  moderate magnitudes, scientific notation otherwise. */
export function formatPlain(value: number | null | undefined, unit: string, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value === 0) return `0 ${unit}`
  const abs = Math.abs(value)
  const text = abs >= 1e-3 && abs < 1e5 ? String(Number(value.toPrecision(digits))) : value.toExponential(digits - 1)
  return `${text} ${unit}`
}

export function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value === 0) return '0'
  return value.toExponential(digits - 1)
}

/** A vector as (x, y, z) with exact zeros shown as "0". */
export const formatVector = (v: number[], digits = 4) => `(${v.map((c) => formatNumber(c, digits)).join(', ')})`
