// Colour mapping is a visualization aid: it maps engine-computed values to colours and never
// changes them. Scales are stated in the legend with their numeric range and unit.

type RGB = [number, number, number]

const SEQUENTIAL: RGB[] = [
  [10, 16, 40], [40, 30, 110], [70, 60, 190], [40, 130, 230], [50, 200, 230], [170, 245, 220],
  [255, 250, 200],
]
const DIVERGING: RGB[] = [
  [120, 200, 255], [56, 140, 248], [30, 70, 170], [12, 18, 34], [150, 50, 40], [240, 110, 70],
  [255, 215, 150],
]

function sample(stops: RGB[], t: number, out: Uint8ClampedArray | number[], o: number): void {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const a = stops[i]!
  const b = stops[i + 1]!
  out[o] = a[0] + (b[0] - a[0]) * f
  out[o + 1] = a[1] + (b[1] - a[1]) * f
  out[o + 2] = a[2] + (b[2] - a[2]) * f
}

export const sequential = (t: number, out: Uint8ClampedArray | number[], o = 0) =>
  sample(SEQUENTIAL, t, out, o)
export const diverging = (t: number, out: Uint8ClampedArray | number[], o = 0) =>
  sample(DIVERGING, t, out, o)

export const cssGradient = (kind: 'sequential' | 'diverging') =>
  `linear-gradient(to right, ${(kind === 'sequential' ? SEQUENTIAL : DIVERGING)
    .map((c) => `rgb(${c.join(',')})`)
    .join(', ')})`

/** q-quantile of the finite values of |a| (subsampled for speed). Used only to pick a display
 *  range that is not dominated by the singular neighbourhood of a point charge. */
export function absQuantile(a: Float32Array, q: number, minPositive = false): number {
  const step = Math.max(1, Math.floor(a.length / 20000))
  const vals: number[] = []
  for (let i = 0; i < a.length; i += step) {
    const v = Math.abs(a[i]!)
    if (Number.isFinite(v) && (!minPositive || v > 0)) vals.push(v)
  }
  if (vals.length === 0) return 0
  vals.sort((x, y) => x - y)
  return vals[Math.min(vals.length - 1, Math.floor(q * (vals.length - 1)))]!
}

export interface LogScale {
  min: number
  max: number
}

/** Map a positive magnitude to 0..1 on a log scale. */
export function logT(v: number, s: LogScale): number {
  if (!(v > 0) || s.max <= s.min) return 0
  return Math.log(v / s.min) / Math.log(s.max / s.min)
}

/** Symmetric-log map of a signed value to 0..1 (0.5 = zero); linear within ±limit/1000. */
export function symlogT(v: number, limit: number): number {
  if (limit <= 0) return 0.5
  const lin = limit * 1e-3
  const t = Math.log1p(Math.abs(v) / lin) / Math.log1p(limit / lin)
  return 0.5 + 0.5 * Math.sign(v) * Math.min(1, t)
}
