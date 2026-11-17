import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api/client'
import type { AmpereHeader, AmperePath, Scene } from '@/api/types'
import { pathPhysics, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { fieldScene, isTimeDependent, scenePhysics } from './request'

export type AmpereData = AmpereHeader & { cache: 'hit' | 'miss' }

/** Cache key of an Ampère evaluation: the magnetic subscene (charges cannot change it) and the
 *  physics of the paths (names and display settings excluded). Mirrors `ampere.fingerprint`. */
export function ampereKey(scene: Scene, paths: AmperePath[]): string {
  return JSON.stringify({ scene: scenePhysics(fieldScene(scene, 'magnetic')), paths: paths.map(pathPhysics) })
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

/** Ampère's law for every path. Not evaluated while anything is being dragged (the previous
 *  result stays on screen, marked stale). */
export function useAmpere() {
  const scene = useSceneStore((s) => s.scene)
  const paths = useSceneStore((s) => s.paths)
  const dragging = useViewStore((s) => s.dragging)
  const timeS = useViewStore((s) => s.timeS)
  const t = isTimeDependent(scene) ? timeS : 0 // Phase 4A: currents at the simulation time
  const live = useMemo(() => ({ key: `${ampereKey(scene, paths)}|${t}`, scene: fieldScene(scene, 'magnetic'), paths, t }), [scene, paths, t])
  const bundle = useDebounced(live, 200)
  const query = useQuery({
    queryKey: ['ampere', bundle.key],
    queryFn: ({ signal }): Promise<AmpereData> => api.ampere(bundle.scene, bundle.paths, signal, bundle.t),
    enabled: bundle.paths.length > 0 && !dragging,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  return {
    data: paths.length > 0 ? query.data : undefined,
    error: query.error,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData || bundle.key !== live.key || dragging,
  }
}
