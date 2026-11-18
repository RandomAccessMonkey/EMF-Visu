import { describe, expect, it } from 'vitest'
import type { CoaxSnapshot } from '@/api/types'
import { CUT, fieldScales, phiHat, rHat, sectionRays, stationArrows, toDisplay, type CoaxCamera } from './coaxSamples'

// Geometry of presets 30/31 and the engine's ring layout (8 % margin, 4 equal segments).
const a = 0.5e-3
const b = 1.67e-3
const L = 2
const k = 120
const ln = Math.log(b / a)
const margin = 0.08 * (b - a)
const seg = (b - a - 2 * margin) / 4
const rings = [0, 1, 2, 3].map((i) => a + margin + (i + 0.5) * seg)
// Mixed signs along the cable: a negative voltage / current and a reflected (backward) part.
const V = [0.8, -0.6, 1.2, -0.05, 0.3]
const I = [0.016, 0.012, -0.024, 0.001, -0.006]
const z = V.map((_, j) => (j * L) / (V.length - 1))
const Er = (j: number, r: number) => V[j]! / (r * ln)
const Hp = (j: number, r: number) => I[j]! / (2 * Math.PI * r)

const snap = {
  scale_V: 2,
  scale_I: 0.04,
  params: { ln_b_over_a: ln },
  stations: {
    z_m: z,
    rings_m: rings,
    segment_m: seg,
    E_r_rings: z.map((_, j) => rings.map((r) => Er(j, r))),
    H_phi_rings: z.map((_, j) => rings.map((r) => Hp(j, r))),
    S_z_rings: z.map((_, j) => rings.map((r) => Er(j, r) * Hp(j, r))),
  },
} as unknown as CoaxSnapshot

const dot = (p: ArrayLike<number>, i: number, q: number[]) => p[3 * i]! * q[0]! + p[3 * i + 1]! * q[1]! + p[3 * i + 2]! * q[2]!
const norm = (p: ArrayLike<number>, i: number) => Math.hypot(p[3 * i]!, p[3 * i + 1]!, p[3 * i + 2]!)
// Arrow buffers are Float32Array: compare relative to float32 precision.
const F32 = 1e-6
const close = (x: number, y: number) => expect(Math.abs(x - y)).toBeLessThanOrEqual(F32 * Math.max(Math.abs(x), Math.abs(y)) + 1e-30)

describe('coax 3D arrows', () => {
  for (const view of ['iso', 'side'] as CoaxCamera[]) {
    const s = stationArrows(snap, view, k, L)!
    it(`${view}: E is radial (no axial or azimuthal part) with the engine's magnitude and sign`, () => {
      expect(s.E.samples.length).toBeGreaterThan(0)
      s.E.samples.forEach((p, i) => {
        expect(Math.abs(s.E.vectors[3 * i]!)).toBe(0) // display x = cable axis
        expect(Math.abs(dot(s.E.vectors, i, phiHat(p.phi)))).toBeLessThan(F32 * norm(s.E.vectors, i) + 1e-30)
        close(dot(s.E.vectors, i, rHat(p.phi)), p.value) // signed radial component
        const j = z.indexOf(p.z)
        close(p.value, Er(j, p.r))
      })
    })
    it(`${view}: S is axial with the sign of V·I`, () => {
      s.S.samples.forEach((p, i) => {
        expect(Math.abs(s.S.vectors[3 * i + 1]!)).toBe(0)
        expect(Math.abs(s.S.vectors[3 * i + 2]!)).toBe(0)
        const j = z.indexOf(p.z)
        expect(Math.sign(s.S.vectors[3 * i]!)).toBe(Math.sign(V[j]! * I[j]!))
        close(p.value, Er(j, p.r) * Hp(j, p.r))
      })
    })
    it(`${view}: Poynting samples keep a margin from both conductors`, () => {
      s.S.samples.forEach((p) => {
        expect(p.r).toBeGreaterThan(a + margin)
        expect(p.r).toBeLessThan(b - margin)
      })
      // Their display position is at the sample radius (the map scales x and y by k only).
      s.S.samples.forEach((p, i) => {
        const q = toDisplay(p.r * Math.cos(p.phi), p.r * Math.sin(p.phi), p.z, k, L)
        expect(Array.from(s.S.points.slice(3 * i, 3 * i + 3))).toEqual(q.map((x) => Math.fround(x)))
      })
    })
  }
  it('iso: H is azimuthal (no radial or axial part), forming arcs at two radii', () => {
    const s = stationArrows(snap, 'iso', k, L)!
    s.H.samples.forEach((p, i) => {
      expect(Math.abs(s.H.vectors[3 * i]!)).toBe(0)
      expect(Math.abs(dot(s.H.vectors, i, rHat(p.phi)))).toBeLessThan(F32 * norm(s.H.vectors, i) + 1e-30)
      close(dot(s.H.vectors, i, phiHat(p.phi)), p.value)
      close(p.value, Hp(z.indexOf(p.z), p.r))
    })
    expect(new Set(s.H.samples.map((p) => p.r)).size).toBe(2)
  })
  it('side: H glyphs carry the component normal to the cut plane (sign of I flips them)', () => {
    const s = stationArrows(snap, 'side', k, L)!
    expect(s.Hglyphs.length).toBeGreaterThan(0)
    // At φ = 0 the glyph value is +H_φ, at φ = π it is −H_φ (φ̂ = ±ŷ there).
    const j = 1
    const zz = z[j]!
    const at0 = s.Hglyphs.filter((g) => Math.abs(g.p[0] - (zz - L / 2)) < 1e-12 && g.p[2] < 0)
    at0.forEach((g) => expect(Math.sign(g.value)).toBe(Math.sign(I[j]!)))
  })
  it('one scale per field: radial dependence 1/r (E, H) and 1/r² (S) is kept in the lengths', () => {
    const sc = fieldScales(snap, rings[0]!)
    expect(sc.E).toBeCloseTo(2 / (rings[0]! * ln), 6)
    const s = stationArrows(snap, 'iso', k, L)!
    const st0 = s.E.samples.map((p, i) => ({ ...p, m: s.E.magnitudes[i]! })).filter((p) => p.z === z[2])
    for (let i = 1; i < st0.length; i++) close(st0[i]!.m / st0[0]!.m, st0[0]!.r / st0[i]!.r)
    const ss = s.S.samples.map((p, i) => ({ ...p, m: s.S.magnitudes[i]! })).filter((p) => p.z === z[2])
    for (let i = 1; i < ss.length; i++) close(ss[i]!.m / ss[0]!.m, (ss[0]!.r / ss[i]!.r) ** 2)
    // Every magnitude is within its single scale.
    s.E.magnitudes.forEach((m) => expect(m).toBeLessThanOrEqual(sc.E * (1 + 1e-6)))
    s.H.magnitudes.forEach((m) => expect(m).toBeLessThanOrEqual(sc.H * (1 + 1e-6)))
    s.S.magnitudes.forEach((m) => expect(m).toBeLessThanOrEqual(sc.S * (1 + 1e-6)))
  })
  it('camera presets only change which samples are drawn, never the physical vectors', () => {
    const value = new Map<string, number>()
    for (const view of ['iso', 'side'] as CoaxCamera[]) {
      const s = stationArrows(snap, view, k, L)!
      s.E.samples.forEach((p) => {
        const key = `E|${p.z}|${p.r}`
        if (value.has(key)) expect(p.value).toBe(value.get(key))
        value.set(key, p.value)
      })
    }
    expect(stationArrows(snap, 'section', k, L)!.E.samples).toEqual([])
    expect(CUT.side.half).toBeCloseTo(Math.PI / 2, 12)
  })
  it('the display map is a proper rotation with radial magnification', () => {
    const [ex, ey, ez] = [toDisplay(1, 0, 0, 1, 0), toDisplay(0, 1, 0, 1, 0), toDisplay(0, 0, 1, 1, 0)]
    const det = ex[0] * (ey[1] * ez[2] - ey[2] * ez[1]) - ex[1] * (ey[0] * ez[2] - ey[2] * ez[0]) + ex[2] * (ey[0] * ez[1] - ey[1] * ez[0])
    expect(det).toBe(1)
  })
})

describe('coax cross-section rays', () => {
  it('E, H and S use disjoint rays; density changes only how many', () => {
    const cs = { n_angles: 48, rings_m: rings } as unknown as CoaxSnapshot['cross_section']
    for (const d of ['low', 'medium', 'high'] as const) {
      const r = sectionRays(cs, d)
      const all = [...r.E, ...r.H, ...r.S]
      expect(new Set(all).size).toBe(all.length)
      expect(r.E.length).toBe({ low: 6, medium: 8, high: 12 }[d])
    }
  })
})
