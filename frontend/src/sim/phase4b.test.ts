import { describe, expect, it } from 'vitest'
import type { FluxSurface, TrajectorySample } from '@/api/types'
import { DEFAULT_TEST_CHARGE, EMPTY_SCENE, isMovingSurface, makeSlidingRod, useSceneStore } from '@/state/sceneStore'
import { sanitizeView } from '@/state/viewStore'
import { inductionKey, inductionUsesTime, useInductionHistory } from './useInduction'
import { lorentzKey, particleKey, sampleAt } from './useLorentz'

const disk: FluxSurface = { id: 'F1', name: 'd', shape: { type: 'circle', radius_m: 0.03 }, center_m: [0, 0, 0], rotation_euler_xyz_rad: [0, 0, 0], reversed: false, rtol: 1e-4, turns: 1 }

describe('Phase 4B moving surfaces', () => {
  it('detects moving surfaces and makes time matter for them only', () => {
    const rod = makeSlidingRod([], 'rod', EMPTY_SCENE.domain)
    expect(rod.shape.type).toBe('sliding_rod')
    expect(isMovingSurface(rod)).toBe(true)
    expect(isMovingSurface(disk)).toBe(false)
    const spun = { ...disk, motion: { translation: { type: 'stationary' as const }, rotation: { type: 'constant_angular_velocity' as const, axis: [1, 0, 0] as [number, number, number], omega_rad_per_s: 1, t0_s: 0 } } }
    expect(isMovingSurface(spun)).toBe(true)
    expect(inductionUsesTime(EMPTY_SCENE, [disk])).toBe(false)
    expect(inductionUsesTime(EMPTY_SCENE, [spun])).toBe(true)
  })

  it('the induction key depends on the velocity convention and the motion', () => {
    const rod = makeSlidingRod([], 'rod', EMPTY_SCENE.domain)
    const k = inductionKey(EMPTY_SCENE, [rod], 0.3)
    expect(inductionKey(EMPTY_SCENE, [rod], 0.3, 'left')).not.toBe(k)
    expect(inductionKey(EMPTY_SCENE, [{ ...rod, name: 'renamed' }], 0.3)).toBe(k)
    expect(inductionKey(EMPTY_SCENE, [{ ...rod, turns: 5 }], 0.3)).not.toBe(k)
  })

  it('records only computed times and restarts the history when the physics changes', () => {
    const h = useInductionHistory.getState()
    h.clear()
    const r = { surface_id: 'F1', time_s: 0.1, flux_Wb: 1, dflux_dt_V: 2, emf_V: 0, emf_motional_V: -2, emf_total_V: -2, moving: true } as never
    h.record('a', [r])
    h.record('a', [{ ...(r as object), time_s: 0.05 } as never])
    h.record('a', [r])
    expect(useInductionHistory.getState().bySurface.F1!.map((p) => p.t)).toEqual([0.05, 0.1])
    h.record('b', [r])
    expect(useInductionHistory.getState().bySurface.F1!.length).toBe(1)
  })

  it('adds a sliding rod through the store and keeps the velocity convention valid', () => {
    const st = useSceneStore.getState()
    st.setFluxSurfaces([])
    st.addFlux('sliding_rod', 'Rod')
    expect(useSceneStore.getState().fluxSurfaces[0]!.shape.type).toBe('sliding_rod')
    expect(sanitizeView({ velocityConvention: 'left' }).velocityConvention).toBe('left')
    expect(sanitizeView({ velocityConvention: 'sideways' }).velocityConvention).toBeUndefined()
  })
})

describe('Phase 4B test charge', () => {
  const s = (t: number): TrajectorySample => ({ t_s: t, position_m: [t, 0, 0], velocity_m_per_s: [1, 0, 0], speed_m_per_s: 1, kinetic_energy_J: 1 })

  it('selects the computed sample at or before t, never interpolating', () => {
    const samples = [s(0), s(1), s(2), s(4)]
    expect(sampleAt(samples, 3)!.t_s).toBe(2)
    expect(sampleAt(samples, 2)!.t_s).toBe(2)
    expect(sampleAt(samples, -1)!.t_s).toBe(0)
    expect(sampleAt(samples, 9)!.t_s).toBe(4)
    expect(sampleAt([], 1)).toBeUndefined()
  })

  it('probe and trajectory keys ignore display options but not physics', () => {
    const tc = DEFAULT_TEST_CHARGE
    expect(particleKey(EMPTY_SCENE, { ...tc, trajectory: { ...tc.trajectory, show_trail: false } })).toBe(particleKey(EMPTY_SCENE, tc))
    expect(particleKey(EMPTY_SCENE, { ...tc, mass_kg: 2 * tc.mass_kg })).not.toBe(particleKey(EMPTY_SCENE, tc))
    expect(lorentzKey(EMPTY_SCENE, tc, 0)).not.toBe(lorentzKey(EMPTY_SCENE, { ...tc, charge_C: -tc.charge_C }, 0))
    expect(lorentzKey(EMPTY_SCENE, tc, 0)).not.toBe(lorentzKey(EMPTY_SCENE, tc, 1))
  })
})
