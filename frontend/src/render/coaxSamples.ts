// Display sampling of the coaxial TEM fields (pure functions; unit-tested in coaxSamples.test.ts).
//
// Every vector here is an engine value placed at the engine's sample radius: E_r, H_φ and S_z
// come from the snapshot (stations: [station][ring]; cross-section: ring-major samples). This
// module only chooses which samples are drawn (by view and density) and maps physical
// cylindrical components to display axes. The display map is a proper rotation plus a radial
// magnification k: (x, y, z) → (z − L/2, k y, −k x), so a radial vector stays radial, an
// azimuthal one azimuthal and an axial one axial.
import type { CoaxSnapshot } from '@/api/types'

export type CoaxCamera = 'iso' | 'side' | 'section'
export type CoaxDensity = 'low' | 'medium' | 'high'

export const STATIONS: Record<CoaxDensity, number> = { low: 17, medium: 33, high: 65 }
/** Rays per field (E, H, S) in the 2D cross-section. */
export const SECTION_RAYS: Record<CoaxDensity, number> = { low: 6, medium: 8, high: 12 }

/** Cut-away wedge (physical φ centre and half-width) of each 3D view. */
export const CUT: Record<CoaxCamera, { phi: number; half: number }> = {
  iso: { phi: Math.atan2(-1.45, -0.8), half: (55 * Math.PI) / 180 },
  side: { phi: -Math.PI / 2, half: Math.PI / 2 }, // the front half removed: the x–z mid-plane
  section: { phi: 0, half: 0 }, // full rings; the cable ends at the inspected cross-section
}

export type V3 = [number, number, number]

export function toDisplay(x: number, y: number, z: number, k: number, L: number): V3 {
  return [z - L / 2, k * y, -k * x]
}

/** Display direction of r̂(φ), φ̂(φ) and ẑ (unit vectors; the radial magnification does not
 *  change directions because x and y are scaled equally). */
export const rHat = (phi: number): V3 => toDisplay(Math.cos(phi), Math.sin(phi), 0, 1, 0)
export const phiHat = (phi: number): V3 => toDisplay(-Math.sin(phi), Math.cos(phi), 0, 1, 0)
export const zHat: V3 = [1, 0, 0]

export interface ArrowSet {
  points: Float32Array
  vectors: Float32Array
  magnitudes: Float32Array
  /** Physical sample positions (r, φ, z) and the engine component, for tests and probes. */
  samples: { r: number; phi: number; z: number; value: number }[]
}

function pack(list: { p: V3; d: V3; value: number; r: number; phi: number; z: number }[]): ArrowSet {
  const points = new Float32Array(3 * list.length)
  const vectors = new Float32Array(3 * list.length)
  const magnitudes = new Float32Array(list.length)
  list.forEach((s, i) => {
    points.set(s.p, 3 * i)
    vectors.set([s.d[0] * s.value, s.d[1] * s.value, s.d[2] * s.value], 3 * i)
    magnitudes[i] = Math.abs(s.value)
  })
  return { points, vectors, magnitudes, samples: list.map(({ r, phi, z, value }) => ({ r, phi, z, value })) }
}

/** The one fixed scale per field type: its largest magnitude over the playback range, at the
 *  innermost sample ring (E, H ∝ 1/r and S ∝ 1/r², so every other ring is shorter). */
export function fieldScales(d: CoaxSnapshot, rMin: number) {
  const ln = d.params.ln_b_over_a
  return {
    E: d.scale_V / (rMin * ln),
    H: d.scale_I / (2 * Math.PI * rMin),
    S: (d.scale_V * d.scale_I) / (2 * Math.PI * rMin * rMin * ln),
  }
}

export interface StationArrows {
  E: ArrowSet
  H: ArrowSet
  S: ArrowSet
  /** H as ⊙/⊗ glyphs on the cut plane (side view: H points out of / into the screen there). */
  Hglyphs: { p: V3; value: number }[]
  rings: number[]
}

/** 3D arrows at the stations along the cable, laid out per view so E, H and S do not overlap:
 *  iso — an E ray, an S ray and H arcs (two rings) inside the cut-away wedge at every station;
 *  side — E (in the cut plane) at even stations, H glyphs and S at odd stations;
 *  section — none along the cable (the inspected cross-section is drawn instead). */
export function stationArrows(d: CoaxSnapshot, view: CoaxCamera, k: number, L: number): StationArrows | null {
  const st = d.stations
  const rings = st.rings_m ?? []
  if (!rings.length || !st.E_r_rings?.length) return null
  const E: Parameters<typeof pack>[0] = []
  const H: Parameters<typeof pack>[0] = []
  const S: Parameters<typeof pack>[0] = []
  const glyphs: { p: V3; value: number }[] = []
  const at = (r: number, phi: number, z: number) => toDisplay(r * Math.cos(phi), r * Math.sin(phi), z, k, L)
  const c = CUT[view].phi
  st.z_m.forEach((z, j) => {
    const er = st.E_r_rings![j]!
    const hp = st.H_phi_rings![j]!
    const sz = st.S_z_rings![j]!
    if (view === 'iso') {
      const phE = c - 0.62
      rings.forEach((r, i) => E.push({ p: at(r, phE, z), d: rHat(phE), value: er[i]!, r, phi: phE, z }))
      for (const i of [1, 3].filter((q) => q < rings.length)) {
        for (const off of [0.2, 0.45, 0.7]) {
          const ph = c + off
          H.push({ p: at(rings[i]!, ph, z), d: phiHat(ph), value: hp[i]!, r: rings[i]!, phi: ph, z })
        }
      }
      // S keeps a margin from both conductors: the outer three rings (all inside [a + m, b − m]).
      rings.slice(1).forEach((r, q) => S.push({ p: at(r, c - 0.15, z), d: zHat, value: sz[q + 1]!, r, phi: c - 0.15, z }))
    } else if (view === 'side') {
      for (const ph of [0, Math.PI]) {
        if (j % 2 === 0) rings.forEach((r, i) => E.push({ p: at(r, ph, z), d: rHat(ph), value: er[i]!, r, phi: ph, z }))
        else {
          rings.forEach((r, i) => {
            if (i % 2 === 0) glyphs.push({ p: at(r, ph, z), value: (ph === 0 ? 1 : -1) * hp[i]! })
            else S.push({ p: at(r, ph, z), d: zHat, value: sz[i]!, r, phi: ph, z })
          })
        }
      }
    }
  })
  return { E: pack(E), H: pack(H), S: pack(S), Hglyphs: glyphs, rings }
}

/** Cross-section samples (2D view and the 3D section view): interleaved E, H and S rays. The
 *  engine's samples are ring-major with n_angles per ring; rays are chosen by density. */
export function sectionRays(cs: CoaxSnapshot['cross_section'], density: CoaxDensity) {
  const n = cs.n_angles ?? 0
  const rings = cs.rings_m ?? []
  const rays = Math.min(SECTION_RAYS[density], Math.max(1, Math.floor(n / 3)))
  const stride = n / rays
  const pick = (offset: number) => Array.from({ length: rays }, (_, q) => Math.round(q * stride + offset) % n)
  return {
    rings,
    E: pick(0),
    H: pick(stride / 3),
    S: pick((2 * stride) / 3),
    index: (ring: number, angle: number) => ring * n + angle,
  }
}
