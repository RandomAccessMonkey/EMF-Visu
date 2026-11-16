import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { create } from 'zustand'
import { api, ApiError, type SimulationResponse } from '@/api/client'
import type { JobStatus, Scene, SolveRequest } from '@/api/types'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { buildRequest, HEAT_RESOLUTION, physicsKey, type Quality } from './request'

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

interface Bundle {
  key: string
  scene: Scene
  request: SolveRequest
}

function useBundle(quality: Quality): Bundle {
  const scene = useSceneStore((s) => s.scene)
  const plane = useViewStore((s) => s.plane)
  const offset = useViewStore((s) => s.offset)
  const arrowDensity = useViewStore((s) => s.arrowDensity)
  const latticeDensity = useViewStore((s) => s.latticeDensity)
  const lattice = useViewStore((s) => s.mode === '3d' && s.showLattice)
  return useMemo(() => {
    const request = buildRequest(
      scene.domain,
      { plane, offset, arrowDensity, latticeDensity, lattice, heatResolution: HEAT_RESOLUTION[quality] },
      quality,
    )
    return { key: physicsKey(scene, request), scene, request }
  }, [scene, plane, offset, arrowDensity, latticeDensity, lattice, quality])
}

// --- High-accuracy solves run as cancellable jobs on the solver's worker service -------------

interface HighState {
  key: string | null // physics key of the request the job was started for
  status: JobStatus | null
  result: SimulationResponse | null
  error: string | null
  run: (bundle: Bundle) => Promise<void>
  cancel: () => Promise<void>
}

export const useHighAccuracy = create<HighState>((set, get) => ({
  key: null,
  status: null,
  result: null,
  error: null,
  run: async ({ key, scene, request }) => {
    set({ key, status: null, result: null, error: null })
    const mine = () => get().key === key
    try {
      const { job_id } = await api.createJob(scene, request)
      if (!mine()) return void api.cancelJob(job_id)
      set({ status: { job_id, state: 'queued', progress: 0, message: '' } })
      const final = await api.watchJob(job_id, (status) => mine() && set({ status }))
      if (!mine()) return
      if (final.state === 'succeeded') set({ result: await api.jobResult(job_id), status: final })
      else set({ status: final, error: final.failure_reason ?? null })
    } catch (e) {
      if (mine()) set({ error: e instanceof Error ? e.message : String(e), status: null })
    }
  },
  cancel: async () => {
    const id = get().status?.job_id
    if (id) await api.cancelJob(id)
  },
}))

export interface Simulation {
  result: SimulationResponse | undefined
  source: 'interactive' | 'high'
  error: ApiError | Error | null
  isFetching: boolean
  /** True while the displayed result belongs to an older physical state than the scene. */
  isStale: boolean
  highBundle: Bundle
}

/** The result to display. Physics-relevant changes trigger a debounced solve (coarser while
 *  dragging); visual-only changes never reach this hook's query key. */
export function useSimulation(): Simulation {
  const dragging = useViewStore((s) => s.dragging)
  const live = useBundle(dragging ? 'preview' : 'normal')
  const highBundle = useBundle('high')
  const bundle = useDebounced(live, dragging ? 25 : 90)
  const query = useQuery({
    queryKey: ['simulation', bundle.key],
    queryFn: ({ signal }) => api.simulate(bundle.scene, bundle.request, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
    retry: false,
  })
  const high = useHighAccuracy()
  const useHigh = !dragging && high.result !== null && high.key === highBundle.key
  return {
    result: useHigh ? high.result! : query.data,
    source: useHigh ? 'high' : 'interactive',
    error: query.error,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData || bundle.key !== live.key,
    highBundle,
  }
}
