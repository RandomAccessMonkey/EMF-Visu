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

export interface SamplingSettings {
  plane: SlicePlane
  offset: number // coordinate of the slice along its normal axis, metres
  arrowDensity: number // arrows along the longer slice edge
  latticeDensity: number // lattice points per axis (3D)
  lattice: boolean
  heatResolution: number // heat-map samples along the longer slice edge
}

export const HEAT_RESOLUTION = { preview: 64, normal: 192, high: 768 } as const
export type Quality = keyof typeof HEAT_RESOLUTION

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

/** Arrow grids are inset by half a cell so no arrow sits on the domain boundary. */
function inset(g: PlaneGridSampling): PlaneGridSampling {
  return {
    ...g,
    u_extent_m: g.u_extent_m * (1 - 1 / g.nu),
    v_extent_m: g.v_extent_m * (1 - 1 / g.nv),
  }
}

export function buildRequest(domain: Domain, s: SamplingSettings, quality: Quality): SolveRequest {
  const samplings: SolveRequest['samplings'] = [
    sliceGrid('heat', domain, s, s.heatResolution),
    inset(sliceGrid('arrows', domain, s, s.arrowDensity)),
  ]
  if (s.lattice) {
    const n = s.latticeDensity
    const lattice: LatticeSampling = {
      kind: 'lattice',
      id: 'vol',
      min_m: domain.min_m.map((lo, a) => lo + (domain.max_m[a]! - lo) / (2 * n)) as Vec3,
      max_m: domain.max_m.map((hi, a) => hi - (hi - domain.min_m[a]!) / (2 * n)) as Vec3,
      nx: n,
      ny: n,
      nz: n,
    }
    samplings.push(lattice)
  }
  return { samplings, quantities: ['E', 'phi'], quality }
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
