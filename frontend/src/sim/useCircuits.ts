// Passive-circuit solution (Phase 4C): one engine solve over the playback grid
// t_k = t_start + k Δt; every induced current shown anywhere (field, probe, viewport, plots)
// is read from it. The sample of the current simulation time is the grid point at or before t
// (playback only visits grid points); nothing is interpolated on the client.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { create } from 'zustand'
import { api } from '@/api/client'
import type { CircuitResult, EddyDisk, PassiveCircuit, PassiveFilament, Scene } from '@/api/types'
import { stepIndex } from '@/panels/TimeBar'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { fieldScene, scenePhysics } from './request'

export type CircuitData = CircuitResult & { cache: 'hit' | 'miss' }
export const MAX_CIRCUIT_SAMPLES = 2001

const physics = (c: PassiveCircuit) => ({ ...c, name: '', display: null, path: { ...c.path, name: '', display: null } })
const diskPhysics = (d: EddyDisk) => ({ ...d, name: '', display: null })

export function circuitKey(scene: Scene, circuits: PassiveCircuit[], disks: EddyDisk[], grid: [number, number, number]): string {
  return JSON.stringify({ s: scenePhysics(fieldScene(scene, 'magnetic')), c: circuits.map(physics), d: disks.map(diskPhysics), g: grid })
}

/** Index of the solution sample for simulation time t (grid point at or before t). */
export function sampleIndex(times: number[], t: number, start: number, step: number): number {
  if (times.length === 0) return -1
  return Math.min(times.length - 1, Math.max(0, stepIndex(t, start, step)))
}

/** The passive circuits' state at sample k, as sent back with field and probe requests. */
export function passiveAt(res: CircuitResult | undefined, k: number): PassiveFilament[] {
  const s = res?.series
  if (!s || k < 0 || k >= s.t_s.length) return []
  return s.filaments.map((f, i) => ({
    ...(f.length > 1 ? f[k]! : f[0]!),
    current_A: s.current_A[i]![k]!,
    rate_A_per_s: s.dI_dt_A_per_s[i]![k]!,
  }))
}

interface PassiveState {
  passive: PassiveFilament[]
  sampleTime: number | null
  /** The circuit solution for the current inputs is not known yet: the field waits for it. */
  pending: boolean
  set: (p: PassiveFilament[], t: number | null, pending: boolean) => void
}

/** The induced-current snapshot of the current simulation time (read by the field solve). */
export const usePassiveState = create<PassiveState>((set) => ({
  passive: [],
  sampleTime: null,
  pending: false,
  set: (passive, sampleTime, pending) => set({ passive, sampleTime, pending }),
}))

export function useCircuits() {
  const scene = useSceneStore((s) => s.scene)
  const circuits = useSceneStore((s) => s.circuits)
  const disks = useSceneStore((s) => s.eddyDisks)
  const dragging = useViewStore((s) => s.dragging)
  const start = useViewStore((s) => s.timeStart)
  const end = useViewStore((s) => s.timeEnd)
  const step = useViewStore((s) => s.timeStep)
  const timeS = useViewStore((s) => s.timeS)
  const any = circuits.length + disks.length > 0
  const samples = Math.floor((end - start) / step + 1e-9) + 1
  const tooMany = samples > MAX_CIRCUIT_SAMPLES
  const key = useMemo(() => circuitKey(scene, circuits, disks, [start, end, step]), [scene, circuits, disks, start, end, step])
  const query = useQuery({
    queryKey: ['circuits', key],
    queryFn: ({ signal }): Promise<CircuitData> => api.circuits(fieldScene(scene, 'magnetic'), { circuits, disks, start_s: start, end_s: end, step_s: step }, signal),
    enabled: any && !dragging && !tooMany && end > start,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  const data = any ? query.data : undefined
  const k = data?.series ? sampleIndex(data.series.t_s, timeS, start, step) : -1
  const fresh = !query.isPlaceholderData
  const passive = useMemo(() => (fresh ? passiveAt(data, k) : []), [data, k, fresh])
  // The snapshot is "ready" for these inputs once their solution (or its failure) is known, or
  // when nothing is to be solved; until then the magnetic field waits for it.
  const ready = !any || tooMany || !(end > start) || query.isError || (data !== undefined && fresh)
  useEffect(() => {
    usePassiveState.getState().set(ready ? passive : [], k >= 0 && data?.series ? data.series.t_s[k]! : null, !ready)
  }, [passive, k, data, ready])
  return {
    data,
    k,
    error: query.error,
    tooMany,
    samples,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData,
  }
}

export type CircuitsData = ReturnType<typeof useCircuits>

/** Whether the circuit solution of the current inputs is known (always true without circuits). */
export function usePassiveReady(): boolean {
  const none = useSceneStore((s) => s.circuits.length + s.eddyDisks.length === 0)
  const pending = usePassiveState((s) => s.pending)
  return none || !pending
}

/** The snapshot for the current inputs ([] while their solution is pending or absent). */
export function useCurrentPassive(): PassiveFilament[] {
  const none = useSceneStore((s) => s.circuits.length + s.eddyDisks.length === 0)
  const st = usePassiveState()
  return none || st.pending ? EMPTY : st.passive
}

const EMPTY: PassiveFilament[] = []
