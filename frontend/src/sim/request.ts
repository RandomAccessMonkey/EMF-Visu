// Builds the sampling request sent to the physics engine. This file decides *where* fields are
// sampled (geometry of the view); it contains no physics.
import type { Domain, LatticeSampling, PlaneGridSampling, Scene, SolveRequest, Vec3 } from '@/api/types'

export type SlicePlane = 'xy' | 'xz' | 'yz'

export interface PlaneBasis {
  u: Vec3
  v: Vec3
  normal: Vec3 // u × v; the 2D camera looks along −normal
  uAxis: 0 | 1 | 2
  vAxis: 0 | 1 | 2
  nAxis: 0 | 1 | 2
}

export const PLANE_BASIS: Record<SlicePlane, PlaneBasis> = {
  xy: { u: [1, 0, 0], v: [0, 1, 0], normal: [0, 0, 1], uAxis: 0, vAxis: 1, nAxis: 2 },
  xz: { u: [1, 0, 0], v: [0, 0, 1], normal: [0, -1, 0], uAxis: 0, vAxis: 2, nAxis: 1 },
  yz: { u: [0, 1, 0], v: [0, 0, 1], normal: [1, 0, 0], uAxis: 1, vAxis: 2, nAxis: 0 },
}

/** The only view settings that reach the physics request. Everything else in the view
 *  (visibility toggles, densities, colour maps, vector field choice, camera) is display-only and
 *  works on the cached result. */
export interface SamplingSettings {
  plane: SlicePlane
  offset: number // coordinate of the slice along its normal axis, metres
  mode: '2d' | '3d' // decides which derived products are computed (planar or spherical lines, isosurfaces)
}

/** Samples along the longer slice edge. Odd counts keep a grid node on the slice centre. */
export const HEAT_RESOLUTION = { preview: 65, normal: 193, high: 769 } as const
/** Lattice points per axis used to extract equipotential surfaces (3D view). */
export const ISO_RESOLUTION = { preview: 21, normal: 41, high: 65 } as const
export type Quality = keyof typeof HEAT_RESOLUTION

/** Arrows are always sampled on this grid; the displayed density is a subsample of it, so
 *  changing the density never needs a new solve. */
export const ARROW_BASE = 49
export const ARROW_DENSITIES = [7, 9, 13, 17, 25, 49] as const
export const LATTICE_BASE = 13
export const LATTICE_DENSITIES = [3, 4, 5, 7, 13] as const
export const FIELD_LINE_LEVELS = 3
export const CALCULUS_QUANTITIES: SolveRequest['quantities'] = ['E', 'D', 'div_E', 'curl_E', 'div_D', 'curl_D']

export const nearest = (allowed: readonly number[], value: number): number =>
  allowed.reduce((best, a) => (Math.abs(a - value) < Math.abs(best - value) ? a : best), allowed[0]!)

function sliceGrid(id: string, domain: Domain, s: SamplingSettings, n: number): PlaneGridSampling {
  const b = PLANE_BASIS[s.plane]
  const center: Vec3 = [0, 0, 0]
  for (const a of [0, 1, 2] as const) center[a] = (domain.min_m[a] + domain.max_m[a]) / 2
  center[b.nAxis] = s.offset
  const ue = domain.max_m[b.uAxis] - domain.min_m[b.uAxis]
  const ve = domain.max_m[b.vAxis] - domain.min_m[b.vAxis]
  const longer = Math.max(ue, ve)
  const count = (extent: number) => Math.max(2, Math.round((n - 1) * (extent / longer)) + 1)
  return {
    kind: 'plane_grid',
    id,
    center_m: center,
    u_dir: b.u,
    v_dir: b.v,
    u_extent_m: ue,
    v_extent_m: ve,
    nu: count(ue),
    nv: count(ve),
  }
}

/** Shrink a grid slightly so no arrow sits exactly on the domain boundary. */
function inset(g: PlaneGridSampling, n: number): PlaneGridSampling {
  const f = 1 - 1 / n
  return { ...g, u_extent_m: g.u_extent_m * f, v_extent_m: g.v_extent_m * f }
}

function lattice(id: string, domain: Domain, n: number, insetCells: number): LatticeSampling {
  const pad = (a: number) => (insetCells * (domain.max_m[a]! - domain.min_m[a]!)) / n
  return {
    kind: 'lattice',
    id,
    min_m: domain.min_m.map((lo, a) => lo + pad(a)) as Vec3,
    max_m: domain.max_m.map((hi, a) => hi - pad(a)) as Vec3,
    nx: n,
    ny: n,
    nz: n,
  }
}

/** All sampling regions come from the scene's own domain; the frontend defines no bounds. */
export function buildRequest(domain: Domain, s: SamplingSettings, quality: Quality): SolveRequest {
  const samplings: SolveRequest['samplings'] = [
    { ...sliceGrid('heat', domain, s, HEAT_RESOLUTION[quality]), quantities: ['E', 'phi'] },
    // Vectors and the pointwise divergence/curl are sampled on the fixed vector grid, so every
    // vector layer and the divergence/curl colour maps are display-only choices.
    { ...inset(sliceGrid('arrows', domain, s, ARROW_BASE), ARROW_BASE), quantities: CALCULUS_QUANTITIES },
  ]
  const request: SolveRequest = {
    samplings,
    quantities: ['E', 'phi'],
    quality,
    field_lines: {
      seeding: s.mode === '2d' ? 'planar' : 'spherical',
      sampling_id: 'heat',
      base_lines: 8,
      levels: FIELD_LINE_LEVELS,
      guard_cells: 0.5,
    },
    equipotentials: { sampling_id: 'heat' },
  }
  if (s.mode === '3d') {
    samplings.push({ ...lattice('vol', domain, LATTICE_BASE, 0.5), quantities: ['phi', ...CALCULUS_QUANTITIES] })
    request.isosurfaces = { lattice: lattice('iso', domain, ISO_RESOLUTION[quality], 0) }
  }
  return request
}

/** Everything that can change a physical result. Display-only attributes are excluded, so
 *  renaming an object or changing a colour map never triggers a new solve. */
export function physicsKey(scene: Scene, request: SolveRequest): string {
  return JSON.stringify({ scene: scenePhysics(scene), request })
}

export function scenePhysics(scene: Scene): unknown {
  return {
    ...scene,
    objects: scene.objects.map((o) => ({ ...o, name: '' })),
    materials: (scene.materials ?? []).map((m) => ({ ...m, name: '' })),
  }
}

/** World positions of the sample points of a plane grid, row-major (v, u) like the payload. */
export function planeGridPoints(g: PlaneGridSampling): Float32Array {
  const out = new Float32Array(g.nu * g.nv * 3)
  let k = 0
  for (let j = 0; j < g.nv; j++) {
    const v = -g.v_extent_m / 2 + (g.v_extent_m * j) / (g.nv - 1)
    for (let i = 0; i < g.nu; i++) {
      const u = -g.u_extent_m / 2 + (g.u_extent_m * i) / (g.nu - 1)
      for (let a = 0; a < 3; a++) out[k++] = g.center_m[a]! + u * g.u_dir[a]! + v * g.v_dir[a]!
    }
  }
  return out
}

/** World positions of lattice points, ordered (z, y, x) like the payload. */
export function latticePoints(l: LatticeSampling): Float32Array {
  const out = new Float32Array(l.nx * l.ny * l.nz * 3)
  const at = (lo: number, hi: number, i: number, n: number) => lo + ((hi - lo) * i) / (n - 1)
  let k = 0
  for (let iz = 0; iz < l.nz; iz++)
    for (let iy = 0; iy < l.ny; iy++)
      for (let ix = 0; ix < l.nx; ix++) {
        out[k++] = at(l.min_m[0], l.max_m[0], ix, l.nx)
        out[k++] = at(l.min_m[1], l.max_m[1], iy, l.ny)
        out[k++] = at(l.min_m[2], l.max_m[2], iz, l.nz)
      }
  return out
}

export interface VectorSamples {
  points: Float32Array // (N, 3)
  vectors: Float32Array // (N, 3)
  cell: number // spacing between displayed samples, metres
}

/** Every `stride`-th sample of a plane grid (rows and columns), keeping the centre sample. */
export function subsamplePlane(g: PlaneGridSampling, vectors: Float32Array, density: number): VectorSamples {
  const stride = Math.max(1, Math.round((Math.max(g.nu, g.nv) - 1) / (density - 1)))
  const all = planeGridPoints(g)
  const is: number[] = []
  const js: number[] = []
  for (let i = ((g.nu - 1) / 2) % stride; i < g.nu; i += stride) is.push(Math.round(i))
  for (let j = ((g.nv - 1) / 2) % stride; j < g.nv; j += stride) js.push(Math.round(j))
  const points = new Float32Array(is.length * js.length * 3)
  const out = new Float32Array(points.length)
  let k = 0
  for (const j of js)
    for (const i of is) {
      const src = 3 * (j * g.nu + i)
      for (let a = 0; a < 3; a++) {
        points[k] = all[src + a]!
        out[k++] = vectors[src + a]!
      }
    }
  const cell = stride * Math.min(g.u_extent_m / (g.nu - 1), g.v_extent_m / (g.nv - 1))
  return { points, vectors: out, cell }
}

/** Every `stride`-th sample of a lattice along each axis. */
export function subsampleLattice(l: LatticeSampling, vectors: Float32Array, density: number): VectorSamples {
  const stride = Math.max(1, Math.round((l.nx - 1) / (density - 1)))
  const all = latticePoints(l)
  const idx = (n: number) => {
    const out: number[] = []
    for (let i = 0; i < n; i += stride) out.push(i)
    return out
  }
  const xs = idx(l.nx)
  const ys = idx(l.ny)
  const zs = idx(l.nz)
  const points = new Float32Array(xs.length * ys.length * zs.length * 3)
  const out = new Float32Array(points.length)
  let k = 0
  for (const z of zs)
    for (const y of ys)
      for (const x of xs) {
        const src = 3 * ((z * l.ny + y) * l.nx + x)
        for (let a = 0; a < 3; a++) {
          points[k] = all[src + a]!
          out[k++] = vectors[src + a]!
        }
      }
  const cell = stride * Math.min(...[0, 1, 2].map((a) => (l.max_m[a]! - l.min_m[a]!) / ([l.nx, l.ny, l.nz][a]! - 1)))
  return { points, vectors: out, cell }
}
