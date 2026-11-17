import { describe, expect, it } from 'vitest'
import type { CurrentSourceInfo, Scene, SceneObject } from '@/api/types'
import { localOutline, outlineNormal } from '@/render/AmpereLayer'
import { solenoidTurnZ, toroidTurnAngles } from '@/render/CoilBodies'
import { currentCrossings } from '@/render/MagneticLayers'
import { EMPTY_SCENE, makeObject, makePath, toroidWithModel } from '@/state/sceneStore'
import { axisSamples } from '@/panels/AxisProfile'
import { buildMagneticRequest, buildRequest, fieldKinds, fieldScene, physicsKey } from './request'
import { ampereKey } from './useAmpere'

const at = (o: SceneObject, x: number): SceneObject => ({ ...o, transform: { ...o.transform, position_m: [x, 0, 0] } })
const obj = (kind: Parameters<typeof makeObject>[1], id: string, x = 0): SceneObject => at({ ...makeObject(EMPTY_SCENE, kind, id), id }, x)
const scene = (...objects: SceneObject[]): Scene => ({ ...EMPTY_SCENE, objects })
const settings = { plane: 'xz' as const, offset: 0, mode: '2d' as const }

describe('Phase 3B sources in the request bookkeeping', () => {
  it('creates well-formed solenoid, toroid and magnet objects', () => {
    const s = obj('solenoid', 's')
    expect(s.primitive).toEqual({ type: 'coil', radius_m: 0.04, length_m: 0.2, turns: 20 })
    expect(s.source).toEqual({ type: 'solenoid', current_A: 1 })
    const t = obj('toroid', 't')
    expect(t.primitive.type).toBe('torus')
    expect(t.source?.type).toBe('toroid_finite')
    const m = obj('magnet', 'm')
    expect(m.role).toBe('magnetic_material')
    expect(m.source).toEqual({ type: 'permanent_magnet', magnetization_A_per_m: 5e5 })
  })

  it('treats magnets as magnetic sources and drops them from the electric subscene', () => {
    expect(fieldKinds(scene(obj('magnet', 'm')))).toEqual(['magnetic'])
    expect(fieldKinds(scene(obj('positive_charge', 'q'), obj('solenoid', 's')))).toEqual(['electric', 'magnetic'])
    const sc = scene(obj('positive_charge', 'q'), obj('solenoid', 's'), obj('toroid', 't'), obj('magnet', 'm'))
    expect(fieldScene(sc, 'electric').objects.map((o) => o.id)).toEqual(['q'])
    expect(fieldScene(sc, 'magnetic').objects.map((o) => o.id)).toEqual(['s', 't', 'm'])
  })

  it('keeps a scaled coil in the electric subscene (the engine refuses it, so must the key)', () => {
    const s = obj('solenoid', 's')
    const scaled = { ...s, transform: { ...s.transform, scale: [1, 1, 2] as [number, number, number] } }
    expect(fieldScene(scene(scaled), 'electric').objects.map((o) => o.id)).toEqual(['s'])
  })

  it('moving a magnet never changes the electric key; it changes the magnetic key', () => {
    const q = obj('positive_charge', 'q')
    const e = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
    const b = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal')
    const a = scene(q, obj('magnet', 'm', 0))
    const moved = scene(q, obj('magnet', 'm', 0.3))
    expect(physicsKey(a, e)).toBe(physicsKey(moved, e))
    expect(physicsKey(a, b)).not.toBe(physicsKey(moved, b))
  })
})

describe('toroid model switch', () => {
  it('keeps both radii and restores the core permeability', () => {
    const t = obj('toroid', 't')
    const ideal = toroidWithModel(t, 'toroid_ideal')
    expect(ideal.source).toEqual({ type: 'toroid_ideal', current_A: 1, relative_permeability: 1 })
    expect(ideal.primitive).toEqual(t.primitive)
    const tuned = { ...ideal, source: { type: 'toroid_ideal' as const, current_A: 2, relative_permeability: 500 } }
    const finite = toroidWithModel(tuned, 'toroid_finite')
    expect(finite.source).toEqual({ type: 'toroid_finite', current_A: 2 })
    expect(toroidWithModel(finite, 'toroid_ideal').source).toEqual({ type: 'toroid_ideal', current_A: 2, relative_permeability: 500 })
  })
})

describe('turn geometry for drawing', () => {
  it('matches the engine rules for turn positions', () => {
    expect(solenoidTurnZ(1, 0.5)).toEqual([0])
    const z = solenoidTurnZ(5, 0.2)
    expect(z[0]).toBeCloseTo(-0.1, 15)
    expect(z[4]).toBeCloseTo(0.1, 15)
    expect(z[1]! - z[0]!).toBeCloseTo(0.05, 15)
    const phi = toroidTurnAngles(4, 0.1)
    expect(phi.map((p) => p - 0.1)).toEqual([0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2])
  })

  it('marks each solenoid turn crossing the xz slice with opposite signs on the two sides', () => {
    const turns = solenoidTurnZ(3, 0.2).map((z) => ({ center_m: [0, 0, z], normal: [0, 0, 1], radius_m: 0.04 }))
    const info = {
      object_id: 's', kind: 'solenoid', current_A: 1, point_m: [0, 0, 0], direction: [0, 0, 1], radius_m: 0.04,
      turns: 3, turns_geometry: turns, plane_crossing_m: {}, plane_crossing_sign: {}, plane_distance_m: {},
    } as unknown as CurrentSourceInfo
    const xs = currentCrossings([info], [0, 0, 0], [0, -1, 0], 'heat')
    expect(xs).toHaveLength(6)
    for (const c of xs) expect(c.sign).toBe(c.p[0] < 0 ? 1 : -1)
    expect(new Set(xs.map((c) => c.key)).size).toBe(6)
    // Ideal toroid and magnet: no free-current filaments to mark.
    expect(currentCrossings([{ ...info, kind: 'toroid_ideal', turns_geometry: [] }, { ...info, kind: 'permanent_magnet', turns_geometry: [] }], [0, 0, 0], [0, -1, 0], 'heat')).toEqual([])
  })
})

describe('Ampère paths', () => {
  it('circle and rectangle run counter-clockwise about local +z; reversing flips the normal', () => {
    const p = makePath([], 'rectangle', 'R', EMPTY_SCENE.domain)
    expect(outlineNormal(localOutline(p)).toArray()).toEqual([0, 0, 1])
    expect(outlineNormal(localOutline({ ...p, reversed: true })).toArray()).toEqual([0, 0, -1])
    const c = makePath([p], 'circle', 'C', EMPTY_SCENE.domain)
    expect(c.id).toBe('A2')
    expect(outlineNormal(localOutline(c)).z).toBeCloseTo(1, 12)
  })

  it('a polygon normal follows its vertex order', () => {
    const p = makePath([], 'polygon', 'P', EMPTY_SCENE.domain)
    const verts = (p.shape as { vertices_m: [number, number, number][] }).vertices_m
    expect(outlineNormal(localOutline(p)).z).toBeCloseTo(1, 12)
    const cw = { ...p, shape: { type: 'polygon' as const, closed: true, vertices_m: [...verts].reverse() } }
    expect(outlineNormal(localOutline(cw)).z).toBeCloseTo(-1, 12)
  })

  it('the cache key ignores names, display settings and charges, but not geometry', () => {
    const path = makePath([], 'circle', 'C', EMPTY_SCENE.domain)
    const base = scene(obj('wire', 'w'))
    const k = ampereKey(base, [path])
    expect(ampereKey(scene(obj('wire', 'w'), obj('positive_charge', 'q', 0.5)), [path])).toBe(k)
    expect(ampereKey(base, [{ ...path, name: 'other', display: { visible: false, show_normal: false, show_crossings: false, show_surface: true } }])).toBe(k)
    expect(ampereKey(base, [{ ...path, reversed: true }])).not.toBe(k)
    expect(ampereKey(base, [{ ...path, center_m: [0.1, 0, 0] }])).not.toBe(k)
  })
})

describe('axis profile sampling', () => {
  it('samples symmetrically along the axis beyond both ends', () => {
    const info = { point_m: [1, 2, 3], direction: [0, 1, 0], radius_m: 0.04, length_m: 0.2 } as unknown as CurrentSourceInfo
    const { s, points, half } = axisSamples(info)
    expect(half).toBeCloseTo(0.1, 15)
    expect(s[0]).toBeCloseTo(-s[s.length - 1]!, 15)
    expect(-s[0]!).toBeGreaterThan(half)
    expect(points[(s.length - 1) / 2]).toEqual([1, 2, 3])
    expect(points[0]![0]).toBe(1)
  })
})
