import { describe, expect, it } from 'vitest'
import type { CircuitResult, PassiveFilament } from '@/api/types'
import { EMPTY_SCENE, circuitFrom, makeSlidingRod, useSceneStore } from '@/state/sceneStore'
import { buildMagneticRequest } from './request'
import { circuitKey, passiveAt, sampleIndex } from './useCircuits'

const fil: PassiveFilament = { id: 'C1', kind: 'circle', center_m: [0, 0, 0.04], normal: [0, 0, 1], u: [1, 0, 0], radius_m: 0.04, vertices_m: [], turns: 1, current_A: 0, rate_A_per_s: 0, moving: false, wire_radius_m: 0.001 }

describe('Phase 4C passive circuits', () => {
  it('maps the simulation time to the solution sample at or before it', () => {
    const t = [0, 0.01, 0.02, 0.03]
    expect(sampleIndex(t, 0.025, 0, 0.01)).toBe(2)
    expect(sampleIndex(t, 0.03, 0, 0.01)).toBe(3)
    expect(sampleIndex(t, 9, 0, 0.01)).toBe(3) // a stopped solution keeps its last sample
    expect(sampleIndex(t, -1, 0, 0.01)).toBe(0)
    expect(sampleIndex([], 0.1, 0, 0.01)).toBe(-1)
  })

  it('builds the induced-current snapshot from the engine solution only', () => {
    const res = { series: { t_s: [0, 1], current_A: [[0, 2.5]], dI_dt_A_per_s: [[1, -3]], filaments: [[fil]] } } as unknown as CircuitResult
    const p = passiveAt(res, 1)
    expect(p).toHaveLength(1)
    expect(p[0]).toMatchObject({ id: 'C1', current_A: 2.5, rate_A_per_s: -3 })
    expect(passiveAt(res, 5)).toEqual([])
    expect(passiveAt(undefined, 0)).toEqual([])
  })

  it('field requests carry the snapshot and ask for prescribed and induced fields', () => {
    const settings = { plane: 'xz' as const, offset: 0, mode: '2d' as const }
    const plain = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal')
    expect(plain.passive).toBeUndefined()
    const req = buildMagneticRequest(EMPTY_SCENE.domain, settings, 'normal', { timeS: 0.2, timeDependent: false, playing: false }, [fil])
    expect(req.passive).toEqual([fil])
    expect(req.time_s).toBe(0.2)
    expect(req.samplings[0]!.quantities).toEqual(['B', 'H', 'dB_dt', 'E_ind', 'B_prescribed', 'B_passive'])
  })

  it('circuits are created explicitly from measurement surfaces; keys ignore names', () => {
    const rod = makeSlidingRod([], 'rod', EMPTY_SCENE.domain)
    const c = circuitFrom(rod, [], 'R')
    expect(c.electrical!.resistance_ohm).toBeGreaterThan(0)
    expect(c.electrical!.self_inductance?.mode).toBe('user')
    expect(c.mechanics?.mode).toBe('dynamic')
    const st = useSceneStore.getState()
    st.setFluxSurfaces([])
    st.addFlux('circle', 'disk')
    const f = useSceneStore.getState().fluxSurfaces[0]!
    st.setCircuits([])
    st.convertFluxToCircuit(f.id, 'loop')
    const made = useSceneStore.getState().circuits[0]!
    expect(made.path.shape).toEqual(f.shape)
    expect(made.electrical!.self_inductance?.mode).toBe('thin_loop')
    expect(useSceneStore.getState().fluxSurfaces).toHaveLength(1) // the surface stays a surface
    const k = circuitKey(EMPTY_SCENE, [made], [], [0, 1, 0.01])
    expect(circuitKey(EMPTY_SCENE, [{ ...made, name: 'other' }], [], [0, 1, 0.01])).toBe(k)
    expect(circuitKey(EMPTY_SCENE, [{ ...made, initial_current_A: 1 }], [], [0, 1, 0.01])).not.toBe(k)
    expect(circuitKey(EMPTY_SCENE, [made], [], [0, 2, 0.01])).not.toBe(k)
  })
})
