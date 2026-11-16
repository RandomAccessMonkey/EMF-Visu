import { describe, expect, it } from 'vitest'
import type { Scene } from '@/api/types'
import { EMPTY_SCENE, makeObject } from '@/state/sceneStore'
import { buildRequest, latticePoints, physicsKey, planeGridPoints, type SamplingSettings } from './request'

const settings: SamplingSettings = {
  plane: 'xy', offset: 0.5, arrowDensity: 21, latticeDensity: 5, lattice: true, heatResolution: 192,
}
const withCharge = (): Scene => ({ ...EMPTY_SCENE, objects: [makeObject(EMPTY_SCENE, 'positive_charge', 'q')] })

describe('buildRequest', () => {
  it('places the slice at the offset along the plane normal', () => {
    const req = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
    const heat = req.samplings[0]!
    expect(heat.kind).toBe('plane_grid')
    if (heat.kind !== 'plane_grid') return
    expect(heat.center_m).toEqual([0, 0, 0.5])
    expect([heat.nu, heat.nv]).toEqual([192, 192])
    expect(req.samplings.map((s) => s.id)).toEqual(['heat', 'arrows', 'vol'])
  })

  it('uses a right-handed basis for every slice plane', () => {
    for (const plane of ['xy', 'xz', 'yz'] as const) {
      const g = buildRequest(EMPTY_SCENE.domain, { ...settings, plane }, 'normal').samplings[0]!
      if (g.kind !== 'plane_grid') throw new Error('expected plane grid')
      const dot = g.u_dir[0] * g.v_dir[0] + g.u_dir[1] * g.v_dir[1] + g.u_dir[2] * g.v_dir[2]
      expect(dot).toBe(0)
    }
  })

  it('keeps aspect ratio for non-cubic domains and omits the lattice in 2D', () => {
    const domain = { ...EMPTY_SCENE.domain, min_m: [-4, -1, -1] as [number, number, number], max_m: [4, 1, 1] as [number, number, number] }
    const req = buildRequest(domain, { ...settings, lattice: false }, 'preview')
    const heat = req.samplings[0]!
    if (heat.kind !== 'plane_grid') throw new Error('expected plane grid')
    expect(heat.nu).toBe(192)
    expect(heat.nv).toBe(49)
    expect(req.samplings).toHaveLength(2)
  })
})

describe('sample point layout matches the engine (row-major v,u and z,y,x)', () => {
  it('plane grid', () => {
    const pts = planeGridPoints({
      kind: 'plane_grid', id: 'g', center_m: [1, 2, 3], u_dir: [1, 0, 0], v_dir: [0, 0, 1],
      u_extent_m: 2, v_extent_m: 4, nu: 3, nv: 5,
    })
    expect(Array.from(pts.slice(0, 3))).toEqual([0, 2, 1])
    expect(Array.from(pts.slice(6, 9))).toEqual([2, 2, 1])
    expect(Array.from(pts.slice(12 * 3, 12 * 3 + 3))).toEqual([0, 2, 5])
  })
  it('lattice', () => {
    const pts = latticePoints({ kind: 'lattice', id: 'l', min_m: [0, 0, 0], max_m: [1, 2, 3], nx: 2, ny: 3, nz: 4 })
    expect(Array.from(pts.slice(3, 6))).toEqual([1, 0, 0])
    expect(Array.from(pts.slice(-3))).toEqual([1, 2, 3])
  })
})

describe('physicsKey (selective recomputation)', () => {
  const req = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
  it('ignores display-only attributes', () => {
    const a = withCharge()
    const b: Scene = { ...a, objects: a.objects.map((o) => ({ ...o, name: 'renamed' })) }
    expect(physicsKey(a, req)).toBe(physicsKey(b, req))
  })
  it('changes when a physical parameter or the sampling changes', () => {
    const a = withCharge()
    const b: Scene = { ...a, objects: a.objects.map((o) => ({ ...o, source: { type: 'point_charge', charge_C: 2e-9 } })) }
    expect(physicsKey(a, req)).not.toBe(physicsKey(b, req))
    expect(physicsKey(a, req)).not.toBe(physicsKey(a, buildRequest(EMPTY_SCENE.domain, { ...settings, offset: 0 }, 'normal')))
  })
})
