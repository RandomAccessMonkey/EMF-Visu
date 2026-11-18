// Coaxial-cable TEM model: client-side validation (so an invalid geometry or excitation never
// reaches the solver or the renderer) and the two engine queries. Every V, I and field value
// shown anywhere comes from the engine's closed-form wave model at the current simulation time;
// nothing physical is evaluated or interpolated on the client.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { CoaxSnapshot, CoaxSpec, CoaxTrace } from '@/api/types'
import type { MessageKey } from '@/i18n'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { STATIONS } from '@/render/coaxSamples'

/** Preset 30 geometry and material, 1 V Gaussian pulse, open load (a useful starting point). */
export const DEFAULT_COAX: CoaxSpec = {
  geometry: { inner_radius_m: 0.5e-3, shield_inner_radius_m: 1.67e-3, shield_outer_radius_m: 2e-3, length_m: 2 },
  material: { relative_permittivity: 2.1, relative_permeability: 1 },
  excitation: { type: 'gaussian', amplitude_V: 1, center_s: 2e-9, width_s: 0.5e-9 },
  load: 'open',
  source: 'matched',
}

export const TRACE_SAMPLES = 401

export interface CoaxIssue {
  key: MessageKey
}

const pos = (v: number) => Number.isFinite(v) && v > 0

/** Every condition the engine also enforces, checked before a request is sent. */
export function validateCoax(spec: CoaxSpec, start: number, end: number): CoaxIssue[] {
  const out: CoaxIssue[] = []
  const g = spec.geometry
  const a = g.inner_radius_m
  const b = g.shield_inner_radius_m
  const c = g.shield_outer_radius_m
  if (![a, b, c, g.length_m].every(pos)) out.push({ key: 'coax.err.positive' })
  else {
    if (!(a < b)) out.push({ key: 'coax.err.ab' })
    else if (!(b / a >= 1 + 1e-6)) out.push({ key: 'coax.err.ratio' })
    if (!(b < c)) out.push({ key: 'coax.err.bc' })
  }
  const m = spec.material
  if (!pos(m.relative_permittivity) || !pos(m.relative_permeability)) out.push({ key: 'coax.err.material' })
  const e = spec.excitation
  if (!Number.isFinite(e.amplitude_V)) out.push({ key: 'coax.err.amplitude' })
  if (e.type === 'sinusoidal' && !pos(e.frequency_Hz)) out.push({ key: 'coax.err.frequency' })
  if (e.type === 'gaussian' && (!pos(e.width_s) || !Number.isFinite(e.center_s))) out.push({ key: 'coax.err.pulse' })
  if (!(Number.isFinite(start) && Number.isFinite(end) && end > start)) out.push({ key: 'coax.err.time' })
  return out
}

/** The cross-section probe: in the 2D view the probe point lies in the cross-section plane. */
export function coaxProbe(mode: '2d' | '3d', p: [number, number, number] | null): [number, number] | null {
  return mode === '2d' && p ? [p[0], p[1]] : null
}

export function useCoax() {
  const spec = useSceneStore((s) => s.coax)
  const timeS = useViewStore((s) => s.timeS)
  const start = useViewStore((s) => s.timeStart)
  const end = useViewStore((s) => s.timeEnd)
  const frac = useViewStore((s) => s.coaxZFraction)
  const mode = useViewStore((s) => s.mode)
  const probePoint = useViewStore((s) => s.probePoint)
  const density = useViewStore((s) => s.coaxDensity)
  const issues = spec ? validateCoax(spec, start, end) : []
  const ok = !!spec && issues.length === 0
  const z = spec ? Math.min(1, Math.max(0, frac)) * spec.geometry.length_m : 0
  const probe = coaxProbe(mode, probePoint)
  const range = { start_s: start, end_s: end }
  const snapshot = useQuery({
    queryKey: ['coax', spec, timeS, z, range, probe, density],
    queryFn: ({ signal }): Promise<CoaxSnapshot> => api.coaxSnapshot({ spec: spec!, t_s: timeS, z_m: z, range, probe_m: probe, stations: STATIONS[density] }, signal),
    enabled: ok,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  const trace = useQuery({
    queryKey: ['coaxTrace', spec, z, range],
    queryFn: ({ signal }): Promise<CoaxTrace> => api.coaxTrace({ spec: spec!, z_m: z, range, count: TRACE_SAMPLES }, signal),
    enabled: ok,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  return {
    spec,
    active: !!spec,
    issues,
    z,
    // Results are only shown for valid inputs (never a stale result for an invalid edit).
    data: ok ? snapshot.data : undefined,
    trace: ok ? trace.data : undefined,
    error: ok ? (snapshot.error ?? trace.error) : null,
    isFetching: snapshot.isFetching,
    isStale: snapshot.isPlaceholderData,
  }
}

export type CoaxData = ReturnType<typeof useCoax>
