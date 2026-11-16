import { describe, expect, it } from 'vitest'
import type { PlaneGridSampling, Scene } from '@/api/types'
import { EMPTY_SCENE, makeObject } from '@/state/sceneStore'
import { DEFAULT_VIEW, sanitizeView } from '@/state/viewStore'
import {
  ARROW_DENSITIES,
  buildRequest,
  LATTICE_DENSITIES,
  latticePoints,
  physicsKey,
  planeGridPoints,
  subsampleLattice,
  subsamplePlane,
  type SamplingSettings,
} from './request'

const settings: SamplingSettings = { plane: 'xy', offset: 0.5, mode: '3d' }
const withCharge = (): Scene => ({ ...EMPTY_SCENE, objects: [makeObject(EMPTY_SCENE, 'positive_charge', 'q')] })

describe('buildRequest', () => {
  it('places the slice at the offset along the plane normal', () => {
    const req = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
    const heat = req.samplings[0]!
    expect(heat.kind).toBe('plane_grid')
    if (heat.kind !== 'plane_grid') return
    expect(heat.center_m).toEqual([0, 0, 0.5])
    expect([heat.nu, heat.nv]).toEqual([193, 193])
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

  it('takes every sampling region from the scene domain and keeps its aspect ratio', () => {
    const domain = { ...EMPTY_SCENE.domain, min_m: [-4, -1, -1] as [number, number, number], max_m: [4, 1, 1] as [number, number, number] }
    const req = buildRequest(domain, { ...settings, mode: '2d' }, 'preview')
    const heat = req.samplings[0]!
    if (heat.kind !== 'plane_grid') throw new Error('expected plane grid')
    expect([heat.nu, heat.nv, heat.u_extent_m, heat.v_extent_m]).toEqual([65, 17, 8, 2])
    expect(req.samplings).toHaveLength(2)
    const iso = buildRequest(domain, settings, 'normal').isosurfaces!.lattice
    expect(iso.min_m).toEqual([-4, -1, -1])
    expect(iso.max_m).toEqual([4, 1, 1])
  })

  it('asks for planar lines in 2D and spherical lines plus isosurfaces in 3D', () => {
    const two = buildRequest(EMPTY_SCENE.domain, { ...settings, mode: '2d' }, 'normal')
    const three = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
    expect(two.field_lines?.seeding).toBe('planar')
    expect(two.isosurfaces ?? null).toBeNull()
    expect(two.equipotentials?.sampling_id).toBe('heat')
    expect(three.field_lines?.seeding).toBe('spherical')
    expect(three.isosurfaces?.lattice.nx).toBe(41)
    // D is requested where vectors are drawn, so showing D needs no extra solve.
    expect(two.samplings[1]!.quantities).toEqual(['E', 'D'])
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

describe('display density is a subsample of the cached arrays', () => {
  const grid = buildRequest(EMPTY_SCENE.domain, settings, 'normal').samplings[1] as PlaneGridSampling
  // Encode each sample's (row, column) in its vector so the picked samples can be identified.
  const vectors = new Float32Array(grid.nu * grid.nv * 3)
  for (let j = 0; j < grid.nv; j++) for (let i = 0; i < grid.nu; i++) vectors.set([i, j, 0], 3 * (j * grid.nu + i))

  it('every offered arrow density divides the base grid and keeps the centre sample', () => {
    for (const density of ARROW_DENSITIES) {
      const sub = subsamplePlane(grid, vectors, density)
      expect(sub.vectors.length / 3).toBe(density * density)
      const cols = new Set<number>()
      for (let k = 0; k < sub.vectors.length; k += 3) cols.add(sub.vectors[k]!)
      expect(cols.has(24)).toBe(true)
      const sorted = [...cols].sort((a, b) => a - b)
      expect(sorted[0]).toBe(0)
      expect(sorted[sorted.length - 1]).toBe(48)
    }
  })

  it('subsampled points are the engine sample points of the picked vectors', () => {
    const sub = subsamplePlane(grid, vectors, 13)
    const all = planeGridPoints(grid)
    for (let k = 0; k < sub.vectors.length; k += 3) {
      const src = 3 * (sub.vectors[k + 1]! * grid.nu + sub.vectors[k]!)
      expect(Array.from(sub.points.slice(k, k + 3))).toEqual(Array.from(all.slice(src, src + 3)))
    }
    expect(sub.cell).toBeCloseTo((4 * grid.u_extent_m) / 48)
  })

  it('lattice densities divide the base lattice', () => {
    const lattice = buildRequest(EMPTY_SCENE.domain, settings, 'normal').samplings[2]!
    if (lattice.kind !== 'lattice') throw new Error('expected lattice')
    const data = new Float32Array(lattice.nx * lattice.ny * lattice.nz * 3)
    for (const density of LATTICE_DENSITIES) {
      expect(subsampleLattice(lattice, data, density).points.length / 3).toBe(density ** 3)
    }
  })
})

describe('physicsKey (selective recomputation)', () => {
  const req = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
  it('ignores display-only attributes', () => {
    const a = withCharge()
    const b: Scene = { ...a, objects: a.objects.map((o) => ({ ...o, name: 'renamed' })) }
    expect(physicsKey(a, req)).toBe(physicsKey(b, req))
  })
  it('changes with charge magnitude, polarity, position, charge count, domain and slice', () => {
    const a = withCharge()
    const edit = (f: (o: Scene['objects'][number]) => Scene['objects'][number]): Scene => ({ ...a, objects: a.objects.map(f) })
    const base = physicsKey(a, req)
    expect(physicsKey(edit((o) => ({ ...o, source: { type: 'point_charge', charge_C: 2e-9 } })), req)).not.toBe(base)
    expect(physicsKey(edit((o) => ({ ...o, source: { type: 'point_charge', charge_C: -1e-9 } })), req)).not.toBe(base)
    expect(physicsKey(edit((o) => ({ ...o, transform: { ...o.transform, position_m: [0.1, 0, 0] } })), req)).not.toBe(base)
    expect(physicsKey({ ...a, objects: [...a.objects, makeObject(a, 'negative_charge', 'q2')] }, req)).not.toBe(base)
    const domain = { ...a.domain, max_m: [3, 2, 2] as [number, number, number] }
    expect(physicsKey({ ...a, domain }, buildRequest(domain, settings, 'normal'))).not.toBe(base)
    expect(physicsKey(a, buildRequest(a.domain, { ...settings, offset: 0 }, 'normal'))).not.toBe(base)
  })
  it('cannot depend on visual-only view settings: they are not inputs of the request', () => {
    // SamplingSettings has exactly these keys; visibility, densities, colour maps, vector field,
    // arrow style and camera never reach buildRequest.
    const keys: (keyof SamplingSettings)[] = ['plane', 'offset', 'mode']
    expect(Object.keys(settings).sort()).toEqual([...keys].sort())
    const visual = Object.keys(DEFAULT_VIEW).filter((k) => !keys.includes(k as keyof SamplingSettings))
    expect(visual).toEqual(expect.arrayContaining(['showArrows', 'showFieldLines', 'lineDensity', 'showContours', 'showIsosurfaces', 'arrowDensity', 'latticeDensity', 'arrowScale', 'arrowLength', 'heatmap', 'vectorField']))
  })
})

describe('saved view settings', () => {
  it('maps densities from older projects onto the offered values', () => {
    const v = sanitizeView({ arrowDensity: 21, latticeDensity: 9, lineDensity: 7, vectorField: 'B', bogus: 1 })
    expect(v.arrowDensity).toBe(17)
    expect(LATTICE_DENSITIES).toContain(v.latticeDensity)
    expect(v.lineDensity).toBe(2)
    expect(v.vectorField).toBeUndefined()
    expect('bogus' in v).toBe(false)
  })
})
