import { describe, expect, it } from 'vitest'
import type { CurrentSourceInfo, Scene, SceneObject } from '@/api/types'
import { currentCrossings, effectiveContribution } from '@/render/MagneticLayers'
import { directionOfRotation, EMPTY_SCENE, makeObject, rotationForDirection } from '@/state/sceneStore'
import { DEFAULT_VIEW, sanitizeView } from '@/state/viewStore'
import { buildMagneticRequest, buildRequest, fieldKinds, fieldScene, physicsKey, requestKind } from './request'

const charge = (id: string, x: number): SceneObject => ({
  ...makeObject(EMPTY_SCENE, 'positive_charge', id),
  id,
  transform: { position_m: [x, 0, 0], rotation_euler_xyz_rad: [0, 0, 0], scale: [1, 1, 1] },
})
const wireAt = (id: string, x: number, current = 10): SceneObject => ({
  ...makeObject(EMPTY_SCENE, 'wire', id),
  id,
  source: { type: 'infinite_wire', current_A: current },
  transform: { position_m: [x, 0, 0], rotation_euler_xyz_rad: [0, 0, 0], scale: [1, 1, 1] },
})
const scene = (...objects: SceneObject[]): Scene => ({ ...EMPTY_SCENE, objects })
const settings = { plane: 'xy' as const, offset: 0, mode: '2d' as const }

describe('electric and magnetic requests', () => {
  it('builds a magnetic request with B, H, per-source contributions and B lines, no equipotentials', () => {
    const req = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal')
    expect(requestKind(req)).toBe('magnetic')
    expect(req.samplings.map((s) => s.quantities)).toEqual([['B', 'H'], ['B', 'H', 'div_B', 'div_H']])
    expect(req.source_contributions).toEqual(['arrows'])
    expect(req.field_lines?.seeding).toBe('planar')
    expect(req.equipotentials ?? null).toBeNull()
    expect(requestKind(buildRequest(EMPTY_SCENE.domain, settings, 'normal'))).toBe('electric')
  })

  it('decides which fields a scene needs', () => {
    expect(fieldKinds(scene())).toEqual(['electric'])
    expect(fieldKinds(scene(charge('q', 0)))).toEqual(['electric'])
    expect(fieldKinds(scene(wireAt('w', 0)))).toEqual(['magnetic'])
    expect(fieldKinds(scene(charge('q', 0), wireAt('w', 1)))).toEqual(['electric', 'magnetic'])
  })

  it('keeps the electric and magnetic cache keys independent', () => {
    const e = buildRequest(EMPTY_SCENE.domain, settings, 'normal')
    const m = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal')
    const base = scene(charge('q', 0), wireAt('w', 1))
    const movedCharge = scene(charge('q', 0.5), wireAt('w', 1))
    const movedWire = scene(charge('q', 0), wireAt('w', 1.5))
    const reversed = scene(charge('q', 0), wireAt('w', 1, -10))
    expect(physicsKey(movedCharge, m)).toBe(physicsKey(base, m))
    expect(physicsKey(movedWire, e)).toBe(physicsKey(base, e))
    expect(physicsKey(movedCharge, e)).not.toBe(physicsKey(base, e))
    expect(physicsKey(movedWire, m)).not.toBe(physicsKey(base, m))
    expect(physicsKey(reversed, m)).not.toBe(physicsKey(base, m))
    expect(fieldScene(base, 'electric').objects.map((o) => o.id)).toEqual(['q'])
    expect(fieldScene(base, 'magnetic').objects.map((o) => o.id)).toEqual(['w'])
  })
})

describe('source geometry helpers', () => {
  it('round-trips a direction through the stored rotation', () => {
    for (const d of [[0, 0, 1], [1, 0, 0], [0, 1, 0], [0.3, -0.5, 0.81], [-1, 2, -2]] as [number, number, number][]) {
      const n = Math.hypot(...d)
      const back = directionOfRotation(rotationForDirection(d))
      back.forEach((v, i) => expect(v).toBeCloseTo(d[i]! / n, 12))
    }
  })

  it('marks where currents cross the 2D slice, out of (⊙) or into (⊗) the screen', () => {
    const wire: CurrentSourceInfo = {
      object_id: 'w', kind: 'infinite_wire', current_A: 10, point_m: [0.5, 0, 0], direction: [0, 0, 1],
      radius_m: null, turns: 1, turns_geometry: [], plane_crossing_m: { heat: [0.5, 0, 0] }, plane_crossing_sign: { heat: 1 }, plane_distance_m: {},
    }
    expect(currentCrossings([wire], [0, 0, 0], [0, 0, 1], 'heat')).toEqual([{ key: 'w', p: [0.5, 0, 0], sign: 1, label: '10.0 A' }])
    // Loop of radius 0.5 in the xy plane, counter-clockwise about +z, seen in the xz slice
    // (normal -y): at x = -a the current flows along -y, towards the viewer.
    const loop: CurrentSourceInfo = {
      object_id: 'l', kind: 'circular_loop', current_A: 10, point_m: [0, 0, 0], direction: [0, 0, 1],
      radius_m: 0.5, turns: 1, turns_geometry: [], plane_crossing_m: {}, plane_crossing_sign: {}, plane_distance_m: { heat: 0 },
    }
    const xs = currentCrossings([loop], [0, 0, 0], [0, -1, 0], 'heat')
    expect(xs).toHaveLength(2)
    const left = xs.find((c) => c.p[0] < 0)!
    const right = xs.find((c) => c.p[0] > 0)!
    expect(left.p[0]).toBeCloseTo(-0.5, 12)
    expect(left.sign).toBe(1)
    expect(right.sign).toBe(-1)
    expect(currentCrossings([{ ...loop, current_A: -10 }], [0, 0, 0], [0, -1, 0], 'heat').find((c) => c.p[0] < 0)!.sign).toBe(-1)
    // A loop lying in the slice plane does not cross it.
    expect(currentCrossings([loop], [0, 0, 0], [0, 0, 1], 'heat')).toEqual([])
  })

  it('falls back to the total field when a saved contribution no longer fits the scene', () => {
    expect(effectiveContribution('all', ['a', 'b'])).toBe('all')
    expect(effectiveContribution('all', ['a'])).toBe('total')
    expect(effectiveContribution('b', ['a', 'b'])).toBe('b')
    expect(effectiveContribution('gone', ['a'])).toBe('total')
  })

  it('accepts only valid magnetic view settings from a saved project', () => {
    const v = sanitizeView({ magneticField: 'E', showBLines: 'yes', contribution: 'w1', heatmap: 'B', showCurrents: false })
    expect(v.magneticField).toBeUndefined()
    expect(v.showBLines).toBeUndefined()
    expect(v.contribution).toBe('w1')
    expect(v.heatmap).toBe('B')
    expect(v.showCurrents).toBe(false)
    expect(DEFAULT_VIEW.magneticField).toBe('B')
  })
})
