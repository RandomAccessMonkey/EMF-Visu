import { describe, expect, it } from 'vitest'
import type { GaussSurface, SurfaceFlux } from '@/api/types'
import { fluxColors, FLUX_COLORS } from '@/render/gaussColors'
import { EMPTY_SCENE, makeObject, makeSurface } from '@/state/sceneStore'
import { buildFluxBody, crossSection, explanationFacts, fluxKey, surfacePhysics } from './gauss'
import * as THREE from 'three'

/** The 12 triangles of an axis-aligned box of half-size h (as the engine builds it). */
function boxTriangles(h: [number, number, number]): Float32Array {
  const c = (x: number, y: number, z: number) => [x * h[0], y * h[1], z * h[2]]
  const quads = [
    [c(-1, -1, -1), c(-1, 1, -1), c(-1, 1, 1), c(-1, -1, 1)], [c(1, -1, -1), c(1, 1, -1), c(1, 1, 1), c(1, -1, 1)],
    [c(-1, -1, -1), c(1, -1, -1), c(1, -1, 1), c(-1, -1, 1)], [c(-1, 1, -1), c(1, 1, -1), c(1, 1, 1), c(-1, 1, 1)],
    [c(-1, -1, -1), c(1, -1, -1), c(1, 1, -1), c(-1, 1, -1)], [c(-1, -1, 1), c(1, -1, 1), c(1, 1, 1), c(-1, 1, 1)],
  ]
  return new Float32Array(quads.flatMap(([a, b, cc, d]) => [...a!, ...b!, ...cc!, ...a!, ...cc!, ...d!]))
}

describe('2D cross-section of a 3D surface', () => {
  it('a box cut at z = 0 gives its rectangular outline', () => {
    const cut = crossSection(boxTriangles([0.6, 0.4, 0.5]), [0, 0, 0], [0, 0, 1])
    const xs = cut.points.filter((_, i) => i % 3 === 0)
    const ys = cut.points.filter((_, i) => i % 3 === 1)
    const zs = cut.points.filter((_, i) => i % 3 === 2)
    expect(Math.max(...xs.map(Math.abs))).toBeCloseTo(0.6, 6)
    expect(Math.max(...ys.map(Math.abs))).toBeCloseTo(0.4, 6)
    expect(zs.every((z) => z === 0)).toBe(true)
    // Perimeter of the 1.2 × 0.8 rectangle.
    let length = 0
    for (let i = 0; i < cut.points.length; i += 6) {
      length += Math.hypot(cut.points[i + 3]! - cut.points[i]!, cut.points[i + 4]! - cut.points[i + 1]!)
    }
    expect(length).toBeCloseTo(4.0, 5)
  })

  it('a slice above the surface cuts nothing; a shifted slice follows the offset', () => {
    expect(crossSection(boxTriangles([0.6, 0.4, 0.5]), [0, 0, 0.7], [0, 0, 1]).points).toEqual([])
    const cut = crossSection(boxTriangles([0.6, 0.4, 0.5]), [0, 0.1, 0], [0, -1, 0])
    expect(cut.points.filter((_, i) => i % 3 === 1).every((y) => Math.abs(y - 0.1) < 1e-6)).toBe(true)
  })
})

describe('flux request and cache key', () => {
  const scene = { ...EMPTY_SCENE, objects: [makeObject(EMPTY_SCENE, 'positive_charge', 'q')] }
  const s: GaussSurface = makeSurface([], 'sphere', 'Sphere 1')

  it('strips names and display metadata from the request', () => {
    const body = buildFluxBody(scene, [s], 'final')
    expect(body.flux.surfaces[0]).toEqual({ ...surfacePhysics(s) })
    expect(body.flux.surfaces[0]!.display).toBeNull()
    expect(body.flux.surfaces[0]!.name).toBe('')
  })

  it('visual-only edits keep the key; physical edits and the mesh quality change it', () => {
    const base = fluxKey(scene, [s], 'final')
    const restyled = { ...s, name: 'other', display: { visible: false, opacity: 0.9, show_normals: true, color_by_flux: false } }
    expect(fluxKey(scene, [restyled], 'final')).toBe(base)
    expect(fluxKey(scene, [{ ...s, center_m: [0.1, 0, 0] }], 'final')).not.toBe(base)
    expect(fluxKey(scene, [{ ...s, orientation: 'inward' }], 'final')).not.toBe(base)
    expect(fluxKey(scene, [{ ...s, shape: { type: 'sphere', radius_m: 0.5 } }], 'final')).not.toBe(base)
    expect(fluxKey(scene, [s], 'preview')).not.toBe(base)
    const moved = { ...scene, objects: scene.objects.map((o) => ({ ...o, transform: { ...o.transform, position_m: [1, 0, 0] as [number, number, number] } })) }
    expect(fluxKey(moved, [s], 'final')).not.toBe(base)
  })
})

describe('guided explanation facts come from the engine result', () => {
  it('counts enclosed, external and near-boundary charges', () => {
    const res = {
      status: 'ok', orientation_sign: 1, flux_E_V_m: 112.9, volume_integral_E_V_m: 112.9,
      enclosed: { positive_count: 1, negative_count: 0, positive_C: 1e-9, negative_C: 0, total_C: 1e-9, external_count: 2, boundary_count: 0 },
      charges: [
        { object_id: 'a', state: 'inside', near_boundary: true, flux_E_V_m: 112.9 },
        { object_id: 'b', state: 'outside', near_boundary: false, flux_E_V_m: 1e-15 },
        { object_id: 'c', state: 'outside', near_boundary: false, flux_E_V_m: -2e-15 },
      ],
    } as unknown as SurfaceFlux
    const f = explanationFacts(res)
    expect(f).toMatchObject({ npos: 1, nneg: 0, qenc: 1e-9, nexternal: 2, nearIds: ['a'], flux: 112.9 })
    expect(Math.abs(f.externalNet)).toBeLessThan(1e-14)
  })
})

describe('surface colours encode the sign of E·n', () => {
  it('outward, inward and approximately zero patches get distinct colours', () => {
    const colors = fluxColors(new Float32Array([5, -5, 1e-6]), new Float32Array([1, -1, 0]), true)
    const hex = (i: number) => new THREE.Color(colors[9 * i]!, colors[9 * i + 1]!, colors[9 * i + 2]!).getHexString()
    expect(`#${hex(0)}`).toBe(FLUX_COLORS.outward)
    expect(`#${hex(1)}`).toBe(FLUX_COLORS.inward)
    expect(`#${hex(2)}`).toBe(FLUX_COLORS.zero)
    const plain = fluxColors(new Float32Array([5]), new Float32Array([1]), false)
    expect(`#${new THREE.Color(plain[0]!, plain[1]!, plain[2]!).getHexString()}`).toBe(FLUX_COLORS.neutral)
  })
})
