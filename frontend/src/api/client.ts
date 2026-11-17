import { decodeContainer, type SimulationResult } from './container'
import type {
  AmpereHeader,
  AmperePath,
  CurrentProfile,
  EquationsResponse,
  ErrorBody,
  FluxSurface,
  GaussSituation,
  GaussSurface,
  Health,
  InductionHeader,
  JobCreated,
  JobStatus,
  LorentzRequest,
  LorentzResult,
  ParticleRequest,
  Preset,
  ProbeResponse,
  ProfileSamples,
  ProjectOut,
  ProjectSummary,
  Scene,
  SolveRequest,
  SolverStatus,
  TestCharge,
  TrajectoryResult,
  Vec3,
  VelocityConvention,
} from './types'

const BASE = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`

/** An error reported by the API. `body.reasons` carries localized explanations. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ErrorBody | null,
    message: string,
  ) {
    super(message)
  }
}

async function fail(res: Response): Promise<never> {
  let body: ErrorBody | null = null
  let message = `${res.status} ${res.statusText}`
  try {
    const json = (await res.json()) as { detail?: unknown }
    if (json.detail && typeof json.detail === 'object' && 'code' in json.detail) {
      body = json.detail as ErrorBody
      message = body.message
    } else if (json.detail) {
      message = JSON.stringify(json.detail)
    }
  } catch {
    // non-JSON error body: keep the status line
  }
  throw new ApiError(res.status, body, message)
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch (cause) {
    throw new ApiError(0, null, `network error: ${String(cause)}`)
  }
  if (!res.ok) await fail(res)
  return res
}

const json = (body: unknown, method = 'POST', signal?: AbortSignal): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  signal,
})

async function get<T>(path: string): Promise<T> {
  return (await (await request(path)).json()) as T
}

export interface SimulationResponse extends SimulationResult {
  cache: 'hit' | 'miss' | 'job'
  roundTripMs: number
}

export const api = {
  health: () => get<Health>('/health'),
  solvers: () => get<SolverStatus[]>('/solvers'),
  presets: () => get<Preset[]>('/presets'),

  async simulate(
    scene: Scene,
    req: SolveRequest,
    signal?: AbortSignal,
  ): Promise<SimulationResponse> {
    const t0 = performance.now()
    const res = await request('/simulations', json({ scene, request: req }, 'POST', signal))
    const result = decodeContainer(await res.arrayBuffer())
    const cache = res.headers.get('X-EMF-Cache') === 'hit' ? 'hit' : 'miss'
    return { ...result, cache, roundTripMs: performance.now() - t0 }
  },

  async probe(scene: Scene, point: Vec3, signal?: AbortSignal, timeS = 0): Promise<ProbeResponse> {
    const res = await request('/probe', json({ scene, point_m: point, time_s: timeS }, 'POST', signal))
    return (await res.json()) as ProbeResponse
  },

  async equations(scene: Scene, signal?: AbortSignal, surfaces: GaussSurface[] = [], paths: AmperePath[] = [], fluxSurfaces: FluxSurface[] = [], testCharge: TestCharge | null = null): Promise<EquationsResponse> {
    const res = await request('/equations/evaluate', json({ scene, surfaces, paths, flux_surfaces: fluxSurfaces, test_charge: testCharge }, 'POST', signal))
    return (await res.json()) as EquationsResponse
  },

  /** Flux through closed Gaussian surfaces (EMF1 container with a FluxHeader). */
  async flux(body: unknown, signal?: AbortSignal): Promise<SimulationResult> {
    const res = await request('/flux', json(body, 'POST', signal))
    return decodeContainer(await res.arrayBuffer())
  },
  /** Ampère's law on closed planar paths (JSON). */
  async ampere(scene: Scene, paths: AmperePath[], signal?: AbortSignal, timeS = 0): Promise<AmpereHeader & { cache: 'hit' | 'miss' }> {
    const res = await request('/ampere', json({ scene, ampere: { paths, time_s: timeS } }, 'POST', signal))
    const body = (await res.json()) as AmpereHeader
    return { ...body, cache: res.headers.get('X-EMF-Cache') === 'hit' ? 'hit' : 'miss' }
  },
  /** Flux, Faraday's law, Lenz signs and mutual inductance at one time (Phase 4A). */
  async induction(scene: Scene, surfaces: FluxSurface[], timeS: number, signal?: AbortSignal, convention: VelocityConvention = 'undefined'): Promise<InductionHeader & { cache: 'hit' | 'miss' }> {
    const res = await request('/induction', json({ scene, induction: { surfaces, time_s: timeS, mutual: true, velocity_convention: convention } }, 'POST', signal))
    const body = (await res.json()) as InductionHeader
    return { ...body, cache: res.headers.get('X-EMF-Cache') === 'hit' ? 'hit' : 'miss' }
  },
  /** Lorentz force on a test charge at one point and time (Phase 4B). */
  async lorentz(scene: Scene, req: LorentzRequest, signal?: AbortSignal): Promise<LorentzResult> {
    const res = await request('/lorentz', json({ scene, lorentz: req }, 'POST', signal))
    return (await res.json()) as LorentzResult
  },
  /** Nonrelativistic test-particle trajectory (Phase 4B). */
  async particle(scene: Scene, req: ParticleRequest, signal?: AbortSignal): Promise<TrajectoryResult> {
    const res = await request('/particle', json({ scene, particle: req }, 'POST', signal))
    return (await res.json()) as TrajectoryResult
  },
  /** I(t) and dI/dt of a profile on an even grid, evaluated by the engine (for plotting). */
  async profileSample(profile: CurrentProfile, startS: number, endS: number, signal?: AbortSignal): Promise<ProfileSamples> {
    const res = await request('/profile/sample', json({ profile, start_s: startS, end_s: endS, count: 241 }, 'POST', signal))
    return (await res.json()) as ProfileSamples
  },
  gaussSituations: () => get<GaussSituation[]>('/gauss/situations'),

  async createJob(scene: Scene, req: SolveRequest): Promise<JobCreated> {
    return (await (await request('/jobs', json({ scene, request: req }))).json()) as JobCreated
  },
  jobStatus: (id: string) => get<JobStatus>(`/jobs/${id}`),
  async cancelJob(id: string): Promise<void> {
    await request(`/jobs/${id}`, { method: 'DELETE' })
  },
  async jobResult(id: string): Promise<SimulationResponse> {
    const t0 = performance.now()
    const res = await request(`/jobs/${id}/result`)
    const result = decodeContainer(await res.arrayBuffer())
    return { ...result, cache: 'job', roundTripMs: performance.now() - t0 }
  },
  /** Progress stream; resolves when the job reaches a terminal state. */
  watchJob(id: string, onStatus: (s: JobStatus) => void): Promise<JobStatus> {
    return new Promise((resolve, reject) => {
      const origin = import.meta.env.VITE_API_URL ?? window.location.origin
      const ws = new WebSocket(`${origin.replace(/^http/, 'ws')}/api/v1/ws/jobs/${id}`)
      let last: JobStatus | null = null
      ws.onmessage = (ev) => {
        const msg = JSON.parse(String(ev.data)) as JobStatus | { error: string }
        if ('error' in msg) return reject(new Error(msg.error))
        last = msg
        onStatus(msg)
        if (msg.state === 'succeeded' || msg.state === 'failed' || msg.state === 'cancelled') {
          resolve(msg)
        }
      }
      ws.onerror = () => reject(new Error('progress connection failed'))
      ws.onclose = () => {
        if (!last || last.state === 'queued' || last.state === 'running') {
          reject(new Error('progress connection closed'))
        }
      }
    })
  },

  projects: () => get<ProjectSummary[]>('/projects'),
  project: (id: string) => get<ProjectOut>(`/projects/${id}`),
  async saveProject(
    name: string,
    scene: Scene,
    view: Record<string, unknown>,
    id?: string,
    surfaces: GaussSurface[] = [],
    paths: AmperePath[] = [],
    fluxSurfaces: FluxSurface[] = [],
    testCharge: TestCharge | null = null,
  ): Promise<ProjectOut> {
    const init = json({ name, scene, view, surfaces, paths, flux_surfaces: fluxSurfaces, test_charge: testCharge }, id ? 'PUT' : 'POST')
    return (await (await request(id ? `/projects/${id}` : '/projects', init)).json()) as ProjectOut
  },
  async deleteProject(id: string): Promise<void> {
    await request(`/projects/${id}`, { method: 'DELETE' })
  },
}
