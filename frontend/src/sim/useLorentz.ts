// Lorentz force on the test charge at the simulation time, and its optional trajectory
// (Phase 4B). Every value comes from the engine; the client only selects which computed
// trajectory sample belongs to the current simulation time.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { LorentzResult, Scene, TestCharge, TrajectoryResult, TrajectorySample } from '@/api/types'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { isTimeDependent, scenePhysics } from './request'

export function lorentzKey(scene: Scene, tc: TestCharge, t: number): string {
  return JSON.stringify({ s: scenePhysics(scene), q: tc.charge_C, v: tc.velocity_m_per_s, p: tc.position_m, t })
}

export function particleKey(scene: Scene, tc: TestCharge): string {
  const { start_s, end_s, tolerance, max_steps } = tc.trajectory
  return JSON.stringify({ s: scenePhysics(scene), q: tc.charge_C, m: tc.mass_kg, v: tc.velocity_m_per_s, p: tc.position_m, traj: [start_s, end_s, tolerance, max_steps] })
}

/** The computed sample at or before t (the last one after the end); never interpolated. */
export function sampleAt(samples: TrajectorySample[], t: number): TrajectorySample | undefined {
  if (samples.length === 0) return undefined
  let lo = 0
  let hi = samples.length - 1
  if (t <= samples[0]!.t_s) return samples[0]
  if (t >= samples[hi]!.t_s) return samples[hi]
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (samples[mid]!.t_s <= t) lo = mid
    else hi = mid
  }
  return samples[lo]
}

export function useLorentz() {
  const scene = useSceneStore((s) => s.scene)
  const tc = useSceneStore((s) => s.testCharge)
  const timeS = useViewStore((s) => s.timeS)
  const dragging = useViewStore((s) => s.dragging)
  const t = isTimeDependent(scene) ? timeS : 0
  const on = !!tc && tc.enabled
  const probe = useQuery({
    queryKey: ['lorentz', on && tc ? lorentzKey(scene, tc, t) : null],
    queryFn: ({ signal }): Promise<LorentzResult> =>
      api.lorentz(scene, { charge_C: tc!.charge_C, velocity_m_per_s: tc!.velocity_m_per_s, point_m: tc!.position_m, time_s: t }, signal),
    enabled: on && !dragging,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  const trajOn = on && !!tc?.trajectory.enabled
  const traj = useQuery({
    queryKey: ['particle', trajOn && tc ? particleKey(scene, tc) : null],
    queryFn: ({ signal }): Promise<TrajectoryResult> =>
      api.particle(
        scene,
        {
          charge_C: tc!.charge_C,
          mass_kg: tc!.mass_kg,
          position_m: tc!.position_m,
          velocity_m_per_s: tc!.velocity_m_per_s,
          start_s: tc!.trajectory.start_s,
          end_s: tc!.trajectory.end_s,
          tolerance: tc!.trajectory.tolerance,
          max_steps: tc!.trajectory.max_steps,
        },
        signal,
      ),
    enabled: trajOn && !dragging,
    staleTime: Infinity,
    retry: false,
  })
  return {
    probe: on ? probe.data : undefined,
    probeError: probe.error,
    trajectory: trajOn ? traj.data : undefined,
    trajectoryError: traj.error,
    trajectoryFetching: traj.isFetching,
    current: trajOn && traj.data ? sampleAt(traj.data.samples, timeS) : undefined,
  }
}

export type LorentzData = ReturnType<typeof useLorentz>
