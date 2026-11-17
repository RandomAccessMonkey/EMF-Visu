import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { create } from 'zustand'
import { api } from '@/api/client'
import type { FluxSurface, InductionHeader, Scene, SurfaceResult, VelocityConvention } from '@/api/types'
import { isMovingSurface, pathPhysics, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { fieldScene, isTimeDependent, scenePhysics } from './request'

export type InductionData = InductionHeader & { cache: 'hit' | 'miss' }

/** Cache key of a Faraday evaluation: the magnetic subscene, the surfaces' physics, the
 *  simulation time (0 for scenes without current profiles or moving surfaces) and the velocity
 *  convention at velocity jumps (Phase 4B). */
export function inductionKey(scene: Scene, surfaces: FluxSurface[], timeS: number, convention: VelocityConvention = 'undefined'): string {
  return JSON.stringify({ scene: scenePhysics(fieldScene(scene, 'magnetic')), surfaces: surfaces.map(pathPhysics), t: timeS, c: convention })
}

/** Whether the induction results depend on the simulation time. */
export function inductionUsesTime(scene: Scene, surfaces: FluxSurface[]): boolean {
  return isTimeDependent(scene) || surfaces.some(isMovingSurface)
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

/** One engine result per computed simulation time, for the waveform plots (Phase 4B). Only
 *  times that were actually computed appear; nothing is interpolated. */
export interface HistoryPoint {
  t: number
  flux: number | null
  dflux: number | null
  emfTr: number | null
  emfMot: number | null
  emfTotal: number | null
  refEmf: number | null
}

interface HistoryState {
  base: string
  bySurface: Record<string, HistoryPoint[]>
  record: (base: string, surfaces: SurfaceResult[]) => void
  clear: () => void
}

export const useInductionHistory = create<HistoryState>((set) => ({
  base: '',
  bySurface: {},
  record: (base, surfaces) =>
    set((s) => {
      const by = s.base === base ? { ...s.bySurface } : {}
      for (const r of surfaces) {
        const pt: HistoryPoint = {
          t: r.time_s,
          flux: r.flux_Wb ?? null,
          dflux: r.dflux_dt_V ?? null,
          emfTr: r.emf_V ?? null,
          emfMot: r.emf_motional_V ?? null,
          emfTotal: r.moving ? (r.emf_total_V ?? null) : (r.emf_V ?? null),
          refEmf: r.reference?.emf_V ?? null,
        }
        const list = (by[r.surface_id] ?? []).filter((p) => p.t !== pt.t)
        list.push(pt)
        list.sort((a, b) => a.t - b.t)
        by[r.surface_id] = list.slice(-2000)
      }
      return { base, bySurface: by }
    }),
  clear: () => set({ base: '', bySurface: {} }),
}))

/** Flux, Faraday's law, Lenz signs and mutual inductance for the measurement surfaces at the
 *  simulation time (Phase 4A), and for moving surfaces the motional and generalized EMF
 *  (Phase 4B). Geometry-only work of stationary surfaces is cached on the server, so moving the
 *  time is cheap. Not evaluated while anything is dragged. */
export function useInduction() {
  const scene = useSceneStore((s) => s.scene)
  const surfaces = useSceneStore((s) => s.fluxSurfaces)
  const timeS = useViewStore((s) => s.timeS)
  const convention = useViewStore((s) => s.velocityConvention)
  const dragging = useViewStore((s) => s.dragging)
  const playing = useViewStore((s) => s.playing)
  const t = inductionUsesTime(scene, surfaces) ? timeS : 0
  const live = useMemo(
    () => ({ key: inductionKey(scene, surfaces, t, convention), base: inductionKey(scene, surfaces, 0, convention), scene: fieldScene(scene, 'magnetic'), surfaces, t, convention }),
    [scene, surfaces, t, convention],
  )
  const bundle = useDebounced(live, playing ? 0 : 120)
  const query = useQuery({
    queryKey: ['induction', bundle.key],
    queryFn: ({ signal }): Promise<InductionData> => api.induction(bundle.scene, bundle.surfaces, bundle.t, signal, bundle.convention),
    enabled: bundle.surfaces.length > 0 && !dragging,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  const fresh = !query.isPlaceholderData && query.data !== undefined
  useEffect(() => {
    if (fresh && query.data) useInductionHistory.getState().record(bundle.base, query.data.surfaces)
  }, [fresh, query.data, bundle.base])
  return {
    data: surfaces.length > 0 ? query.data : undefined,
    error: query.error,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData || bundle.key !== live.key || dragging,
  }
}
