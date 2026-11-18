import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { create } from 'zustand'
import { api, ApiError, type SimulationResponse } from '@/api/client'
import type { FieldKind, JobStatus, Scene, SolveRequest } from '@/api/types'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { useCurrentPassive, usePassiveReady } from './useCircuits'
import { buildMagneticRequest, buildRequest, fieldKinds, isTimeDependent, physicsKey, type Quality } from './request'

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

export interface Bundle {
  kind: FieldKind
  key: string
  scene: Scene
  request: SolveRequest
}

function useBundle(kind: FieldKind, quality: Quality): Bundle {
  const scene = useSceneStore((s) => s.scene)
  const plane = useViewStore((s) => s.plane)
  const offset = useViewStore((s) => s.offset)
  const mode = useViewStore((s) => s.mode)
  const timeS = useViewStore((s) => s.timeS)
  const playing = useViewStore((s) => s.playing)
  // Phase 4C: the solved induced currents at this time (from the circuit solution).
  const passive = useCurrentPassive()
  return useMemo(() => {
    const settings = { plane, offset, mode }
    const time = { timeS, timeDependent: isTimeDependent(scene), playing }
    const request = kind === 'electric' ? buildRequest(scene.domain, settings, quality) : buildMagneticRequest(scene.domain, settings, quality, time, passive)
    return { kind, key: physicsKey(scene, request), scene, request }
  }, [kind, scene, plane, offset, mode, quality, timeS, playing, passive])
}

// --- High-accuracy solves run as cancellable jobs on the solver's worker service -------------
// One job per field kind present (electric and/or magnetic), so both layers are refined.

export interface HighJob {
  key: string // physics key of the request the job was started for
  status: JobStatus | null
  result: SimulationResponse | null
  error: string | null
}

interface HighState {
  jobs: Partial<Record<FieldKind, HighJob>>
  run: (bundles: Bundle[]) => Promise<void>
  cancel: () => Promise<void>
}

export const useHighAccuracy = create<HighState>((set, get) => {
  const patch = (kind: FieldKind, key: string, p: Partial<HighJob>) => {
    const cur = get().jobs[kind]
    if (cur?.key !== key) return // a newer job for this kind replaced this one
    set({ jobs: { ...get().jobs, [kind]: { ...cur, ...p } } })
  }
  const runOne = async ({ kind, key, scene, request }: Bundle) => {
    const mine = () => get().jobs[kind]?.key === key
    try {
      const { job_id } = await api.createJob(scene, request)
      if (!mine()) return void api.cancelJob(job_id)
      patch(kind, key, { status: { job_id, state: 'queued', progress: 0, message: '' } })
      const final = await api.watchJob(job_id, (status) => patch(kind, key, { status }))
      if (!mine()) return
      if (final.state === 'succeeded') patch(kind, key, { result: await api.jobResult(job_id), status: final })
      else patch(kind, key, { status: final, error: final.failure_reason ?? null })
    } catch (e) {
      patch(kind, key, { error: e instanceof Error ? e.message : String(e), status: null })
    }
  }
  return {
    jobs: {},
    run: async (bundles) => {
      const jobs: Partial<Record<FieldKind, HighJob>> = {}
      for (const b of bundles) jobs[b.kind] = { key: b.key, status: null, result: null, error: null }
      set({ jobs })
      await Promise.all(bundles.map(runOne))
    },
    cancel: async () => {
      await Promise.all(
        Object.values(get().jobs).map((j) => (j?.status?.job_id ? api.cancelJob(j.status.job_id) : undefined)),
      )
    },
  }
})

export interface FieldSimulation {
  result: SimulationResponse | undefined
  source: 'interactive' | 'high'
  error: ApiError | Error | null
  isFetching: boolean
  /** True while the displayed result belongs to an older physical state than the scene. */
  isStale: boolean
  /** Whether this field is solved for the current scene at all. */
  active: boolean
}

export interface Simulation extends FieldSimulation {
  /** The magnetic field (Phase 3A). The top-level fields describe the electric field. */
  magnetic: FieldSimulation
  kinds: FieldKind[]
  /** High-resolution requests of every active field kind. */
  highBundles: Bundle[]
}

function useField(kind: FieldKind, active: boolean): FieldSimulation & { highBundle: Bundle } {
  const dragging = useViewStore((s) => s.dragging)
  const live = useBundle(kind, dragging ? 'preview' : 'normal')
  const highBundle = useBundle(kind, 'high')
  const bundle = useDebounced(live, dragging ? 25 : 90)
  // Phase 4C: with passive circuits, the magnetic field waits for their solution, so the field
  // shown always includes the induced currents of the same authoritative solution.
  const passiveReady = usePassiveReady()
  const waiting = kind === 'magnetic' && !passiveReady
  const query = useQuery({
    queryKey: ['simulation', kind, bundle.key],
    queryFn: ({ signal }) => api.simulate(bundle.scene, bundle.request, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
    retry: false,
    enabled: active && !waiting,
  })
  const high = useHighAccuracy((s) => s.jobs[kind])
  const useHigh = !dragging && !!high?.result && high.key === highBundle.key
  return {
    result: !active ? undefined : useHigh ? high.result! : query.data,
    source: useHigh ? 'high' : 'interactive',
    error: active ? query.error : null,
    isFetching: active && (query.isFetching || waiting),
    isStale: active && (query.isPlaceholderData || bundle.key !== live.key || waiting),
    active,
    highBundle,
  }
}

/** The results to display. Physics-relevant changes trigger a debounced solve (coarser while
 *  dragging) of the affected field only; visual-only changes never reach the query keys. */
export function useSimulation(): Simulation {
  const scene = useSceneStore((s) => s.scene)
  const kinds = useMemo(() => fieldKinds(scene), [scene])
  const electric = useField('electric', kinds.includes('electric'))
  const magnetic = useField('magnetic', kinds.includes('magnetic'))
  const { highBundle: eHigh, ...e } = electric
  const { highBundle: mHigh, ...m } = magnetic
  return {
    ...e,
    magnetic: m,
    kinds,
    highBundles: [...(e.active ? [eHigh] : []), ...(m.active ? [mHigh] : [])],
  }
}
