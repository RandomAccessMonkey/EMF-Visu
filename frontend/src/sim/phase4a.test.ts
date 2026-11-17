import { describe, expect, it } from 'vitest'
import type { Scene, SceneObject } from '@/api/types'
import { gridTime, stepIndex } from '@/panels/TimeBar'
import { EMPTY_SCENE, makeObject, useSceneStore } from '@/state/sceneStore'
import { sanitizeView } from '@/state/viewStore'
import { buildMagneticRequest, buildRequest, isTimeDependent, physicsKey } from './request'
import { inductionKey } from './useInduction'

const scene = (...objects: SceneObject[]): Scene => ({ ...EMPTY_SCENE, objects })
const settings = { plane: 'xy' as const, offset: 0, mode: '2d' as const }
const loopObj = (): SceneObject => ({ ...makeObject(EMPTY_SCENE, 'loop', 'l'), id: 'l' })
const driven = (): SceneObject => {
  const o = loopObj()
  return { ...o, source: { type: 'circular_loop', current_A: 0, profile: { type: 'sinusoidal', dc_A: 0, peak_A: 2, frequency_Hz: 1, phase_rad: 0 } } }
}

describe('Phase 4A requests', () => {
  it('leaves static scenes exactly as before (no time, no time quantities)', () => {
    const req = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal')
    expect(req.time_s).toBe(0)
    expect(req.samplings.map((s) => s.quantities)).toEqual([['B', 'H'], ['B', 'H', 'div_B', 'div_H']])
    expect(req.field_lines).toBeDefined()
    expect(isTimeDependent(scene(loopObj()))).toBe(false)
  })

  it('asks for dB/dt and E_ind at the simulation time for time-dependent scenes', () => {
    expect(isTimeDependent(scene(driven()))).toBe(true)
    const req = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal', { timeS: 0.3, timeDependent: true, playing: false })
    expect(req.time_s).toBe(0.3)
    expect(req.samplings[0]!.quantities).toEqual(['B', 'H', 'dB_dt', 'E_ind'])
    expect(req.field_lines).toBeDefined()
    const playing = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal', { timeS: 0.3, timeDependent: true, playing: true })
    expect(playing.field_lines).toBeUndefined() // lines are computed when paused
  })

  it('a time change re-solves the magnetic field only', () => {
    const s = scene(driven())
    const m = (t: number) => physicsKey(s, buildMagneticRequest(s.domain, settings, 'normal', { timeS: t, timeDependent: true, playing: false }))
    expect(m(0.1)).not.toBe(m(0.2))
    const e = buildRequest(s.domain, settings, 'normal')
    expect(e.time_s).toBe(0)
    expect(physicsKey(s, e)).toBe(physicsKey(scene(), e)) // profiles never reach the electric key
  })
})

describe('deterministic playback', () => {
  it('maps indices to exact grid times without accumulation', () => {
    const start = 0
    const step = 0.01
    const end = 2
    let t = start
    for (let k = 0; k < 150; k++) t = gridTime(stepIndex(t, start, step) + 1, start, end, step)
    expect(t).toBe(gridTime(150, start, end, step))
    expect(t).toBe(start + 150 * step)
    expect(gridTime(1000, start, end, step)).toBe(end)
    expect(stepIndex(0.30000000000000004, 0, 0.1)).toBe(3)
  })
})

describe('measurement surfaces and profiles in the store', () => {
  it('adds surfaces with the surface shown, and sets or clears a profile', () => {
    const st = useSceneStore.getState()
    st.load(scene(loopObj()))
    st.setFluxSurfaces([])
    st.addFlux('circle', 'disk')
    const f = useSceneStore.getState().fluxSurfaces[0]!
    expect(f.id).toBe('F1')
    expect(f.display?.show_surface).toBe(true)
    st.setProfile('l', { type: 'ramp', start_A: 0, slope_A_per_s: 5, t_start_s: 0, t_end_s: 1 })
    expect(isTimeDependent(useSceneStore.getState().scene)).toBe(true)
    st.setProfile('l', null)
    expect(isTimeDependent(useSceneStore.getState().scene)).toBe(false)
  })

  it('the induction key ignores names and display settings but not geometry or time', () => {
    const st = useSceneStore.getState()
    st.addFlux('rectangle', 'r')
    const surf = useSceneStore.getState().fluxSurfaces[0]!
    const s = scene(driven())
    const k = inductionKey(s, [surf], 0.1)
    expect(inductionKey(s, [{ ...surf, name: 'other', display: { visible: false, show_normal: false, show_crossings: false, show_surface: false } }], 0.1)).toBe(k)
    expect(inductionKey(s, [{ ...surf, reversed: true }], 0.1)).not.toBe(k)
    expect(inductionKey(s, [surf], 0.2)).not.toBe(k)
  })

  it('accepts saved time settings and rejects invalid ones', () => {
    expect(sanitizeView({ timeS: 0.4, timeStart: 0, timeEnd: 2, timeStep: 0.01, magneticField: 'E_ind' })).toMatchObject({ timeS: 0.4, timeEnd: 2, magneticField: 'E_ind' })
    const bad = sanitizeView({ timeStart: 3, timeEnd: 1, timeStep: -1, magneticField: 'X' })
    expect(bad.timeStart).toBeUndefined()
    expect(bad.timeStep).toBeUndefined()
    expect(bad.magneticField).toBeUndefined()
  })
})
