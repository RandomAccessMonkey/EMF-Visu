import { beforeEach, describe, expect, it } from 'vitest'
import { dipoleInfo, EMPTY_SCENE, useSceneStore } from './sceneStore'

const store = () => useSceneStore.getState()

describe('dipole editing (two real point charges under a group)', () => {
  beforeEach(() => store().load(EMPTY_SCENE))

  it('adds +q and −q a distance d apart', () => {
    store().addDipole('Dipole 1')
    const { scene, selectedId } = store()
    expect(scene.objects.map((o) => o.primitive.type)).toEqual(['group', 'point', 'point'])
    const info = dipoleInfo(scene, selectedId!)!
    expect(info.charge_C).toBe(1e-9)
    expect(info.negative.source!.charge_C).toBe(-1e-9)
    expect(info.separation_m).toBe(1)
    expect(info.balanced).toBe(true)
  })

  it('changes magnitude and separation together, keeping the midpoint and the axis', () => {
    store().addDipole('d')
    const id = store().selectedId!
    store().setDipole(id, 5e-9, 0.4)
    const info = dipoleInfo(store().scene, id)!
    expect(info.charge_C).toBe(5e-9)
    expect(info.negative.source!.charge_C).toBe(-5e-9)
    expect(info.separation_m).toBeCloseTo(0.4, 12)
    expect(info.positive.transform.position_m[0]).toBeCloseTo(-0.2, 12)
    expect(info.negative.transform.position_m[0]).toBeCloseTo(0.2, 12)
    store().setDipole(id, -1, 0) // invalid values are ignored
    expect(dipoleInfo(store().scene, id)!.charge_C).toBe(5e-9)
  })

  it('reports an unbalanced pair and a broken dipole honestly', () => {
    store().addDipole('d')
    const id = store().selectedId!
    const info = dipoleInfo(store().scene, id)!
    store().update(info.negative.id, { source: { type: 'point_charge', charge_C: -3e-9 } })
    expect(dipoleInfo(store().scene, id)!.balanced).toBe(false)
    store().update(info.negative.id, { source: { type: 'point_charge', charge_C: 3e-9 } })
    expect(dipoleInfo(store().scene, id)).toBeNull()
  })

  it('removing the group removes its charges', () => {
    store().add('positive_charge', 'free')
    store().addDipole('d')
    store().remove(store().selectedId!)
    expect(store().scene.objects.map((o) => o.name)).toEqual(['free'])
  })
})
