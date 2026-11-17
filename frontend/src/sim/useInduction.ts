import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api/client'
import type { AmperePath, InductionHeader, Scene } from '@/api/types'
import { pathPhysics, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { fieldScene, isTimeDependent, scenePhysics } from './request'

export type InductionData = InductionHeader & { cache: 'hit' | 'miss' }

/** Cache key of a Faraday evaluation: the magnetic subscene, the surfaces' physics and the
 *  simulation time (0 for scenes without current profiles). */
export function inductionKey(scene: Scene, surfaces: AmperePath[], timeS: number): string {
  return JSON.stringify({ scene: scenePhysics(fieldScene(scene, 'magnetic')), surfaces: surfaces.map(pathPhysics), t: timeS })
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

/** Flux, Faraday's law, Lenz signs and mutual inductance for the measurement surfaces at the
 *  simulation time (Phase 4A). Geometry-only work is cached on the server, so moving the time
 *  is cheap. Not evaluated while anything is dragged. */
export function useInduction() {
  const scene = useSceneStore((s) => s.scene)
  const surfaces = useSceneStore((s) => s.fluxSurfaces)
  const timeS = useViewStore((s) => s.timeS)
  const dragging = useViewStore((s) => s.dragging)
  const playing = useViewStore((s) => s.playing)
  const t = isTimeDependent(scene) ? timeS : 0
  const live = useMemo(() => ({ key: inductionKey(scene, surfaces, t), scene: fieldScene(scene, 'magnetic'), surfaces, t }), [scene, surfaces, t])
  const bundle = useDebounced(live, playing ? 0 : 120)
  const query = useQuery({
    queryKey: ['induction', bundle.key],
    queryFn: ({ signal }): Promise<InductionData> => api.induction(bundle.scene, bundle.surfaces, bundle.t, signal),
    enabled: bundle.surfaces.length > 0 && !dragging,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  return {
    data: surfaces.length > 0 ? query.data : undefined,
    error: query.error,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData || bundle.key !== live.key || dragging,
  }
}
