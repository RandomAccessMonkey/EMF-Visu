// Gaussian-surface helpers: the flux request and its cache key, and pure geometry for the 2D
// cross-section. No physics here: every flux value comes from the engine.
import type { SimulationResult } from '@/api/container'
import type { FluxHeader, GaussSurface, Scene, SurfaceFlux, Vec3 } from '@/api/types'
import { scenePhysics } from './request'

export type FluxQuality = 'preview' | 'final'

/** What the engine needs: display metadata and names are stripped, so that changing them
 *  neither changes the request nor the cache key. */
export function surfacePhysics(s: GaussSurface): GaussSurface {
  return {
    id: s.id,
    name: '',
    shape: s.shape,
    center_m: s.center_m,
    rotation_euler_xyz_rad: s.rotation_euler_xyz_rad,
    orientation: s.orientation,
    subdivision: s.subdivision ?? null,
    display: null,
  }
}

export interface FluxBody {
  scene: Scene
  flux: { surfaces: GaussSurface[]; quality: FluxQuality; patch_details: boolean }
}

export function buildFluxBody(scene: Scene, surfaces: GaussSurface[], quality: FluxQuality): FluxBody {
  return { scene, flux: { surfaces: surfaces.map(surfacePhysics), quality, patch_details: true } }
}

/** Separate cache key for flux results: physical scene + surface geometry and orientation +
 *  quality (which fixes the mesh resolution, so preview and final can never be confused). */
export function fluxKey(scene: Scene, surfaces: GaussSurface[], quality: FluxQuality): string {
  return JSON.stringify({ scene: scenePhysics(scene), surfaces: surfaces.map(surfacePhysics), quality })
}

export interface FluxData {
  header: FluxHeader
  result: SimulationResult
}

export function surfaceResult(flux: FluxData | undefined, id: string | null): SurfaceFlux | undefined {
  return id ? flux?.header.surfaces.find((s) => s.surface_id === id) : undefined
}

/** Line segments where the triangles cross the plane {x : (x - c) · n = 0}. Pure geometry on
 *  the engine's mesh; returns [x0,y0,z0,x1,y1,z1, ...] and the triangle of each segment. */
export function crossSection(triangles: Float32Array, center: Vec3, normal: Vec3): { points: number[]; triangle: number[] } {
  const points: number[] = []
  const triangle: number[] = []
  const d = (i: number) =>
    (triangles[i]! - center[0]) * normal[0] + (triangles[i + 1]! - center[1]) * normal[1] + (triangles[i + 2]! - center[2]) * normal[2]
  for (let t = 0; t < triangles.length / 9; t++) {
    const base = 9 * t
    const ds = [d(base), d(base + 3), d(base + 6)]
    const hits: number[][] = []
    for (let e = 0; e < 3; e++) {
      const a = e
      const b = (e + 1) % 3
      const da = ds[a]!
      const db = ds[b]!
      if ((da < 0 && db > 0) || (da > 0 && db < 0)) {
        const s = da / (da - db)
        const pa = base + 3 * a
        const pb = base + 3 * b
        hits.push([0, 1, 2].map((k) => triangles[pa + k]! + s * (triangles[pb + k]! - triangles[pa + k]!)))
      } else if (da === 0) {
        hits.push([0, 1, 2].map((k) => triangles[base + 3 * a + k]!))
      }
    }
    if (hits.length >= 2) {
      points.push(...hits[0]!, ...hits[1]!)
      triangle.push(t)
    }
  }
  return { points, triangle }
}

/** Facts for the guided explanation, read from one surface result. */
export function explanationFacts(s: SurfaceFlux) {
  const enc = s.enclosed
  const external = s.charges.filter((c) => c.state === 'outside')
  const externalNet = external.reduce((sum, c) => sum + (c.flux_E_V_m ?? 0), 0)
  return {
    status: s.status,
    npos: enc?.positive_count ?? 0,
    nneg: enc?.negative_count ?? 0,
    qenc: enc?.total_C ?? 0,
    nexternal: external.length,
    externalNet,
    nboundary: enc?.boundary_count ?? 0,
    nearIds: s.charges.filter((c) => c.near_boundary && c.state !== 'boundary').map((c) => c.object_id),
    flux: s.flux_E_V_m ?? null,
    volume: s.volume_integral_E_V_m ?? null,
    sign: s.orientation_sign,
  }
}
