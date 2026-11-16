import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api/client'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { buildFluxBody, fluxKey, type FluxData, type FluxQuality } from './gauss'

function useDebounced<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return v
}

/** Flux through the Gaussian surfaces. While anything is dragged the preview mesh is used;
 *  when the drag ends, the final mesh. The quality is part of the key, so the two results are
 *  cached separately and labelled by the engine. */
export function useFlux() {
  const scene = useSceneStore((s) => s.scene)
  const surfaces = useSceneStore((s) => s.surfaces)
  const dragging = useViewStore((s) => s.dragging)
  const quality: FluxQuality = dragging ? 'preview' : 'final'
  const live = useMemo(() => ({ key: fluxKey(scene, surfaces, quality), body: buildFluxBody(scene, surfaces, quality) }), [scene, surfaces, quality])
  const bundle = useDebounced(live, dragging ? 30 : 120)
  const query = useQuery({
    queryKey: ['flux', bundle.key],
    queryFn: async ({ signal }): Promise<FluxData> => {
      const result = await api.flux(bundle.body, signal)
      return { header: result.header as unknown as FluxData['header'], result }
    },
    enabled: bundle.body.flux.surfaces.length > 0,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  return {
    data: surfaces.length > 0 ? query.data : undefined,
    error: query.error,
    isFetching: query.isFetching,
    isStale: query.isPlaceholderData || bundle.key !== live.key,
  }
}
