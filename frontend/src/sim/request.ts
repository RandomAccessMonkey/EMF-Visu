// Builds the sampling request sent to the physics engine. This file decides *where* fields are
// sampled (geometry of the view); it contains no physics.
import type { Domain, FieldKind, LatticeSampling, PlaneGridSampling, Scene, SceneObject, SolveRequest, Vec3 } from '@/api/types'

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
/** Magnetic quantities on the vector grid (B, H and their exact divergence). */
export const MAGNETIC_GRID_QUANTITIES: SolveRequest['quantities'] = ['B', 'H', 'div_B', 'div_H']

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
    source_contributions: [],
  }
  if (s.mode === '3d') {
    samplings.push({ ...lattice('vol', domain, LATTICE_BASE, 0.5), quantities: ['phi', ...CALCULUS_QUANTITIES] })
    request.isosurfaces = { lattice: lattice('iso', domain, ISO_RESOLUTION[quality], 0) }
  }
  return request
}

/** The magnetic request (Phase 3A): B and H on the same slice and vector grid as the electric
 *  request, each source's own B on the vector grid (so showing one contribution is visual-only),
 *  and B field lines. No equipotentials: they belong to the electric field. */
export function buildMagneticRequest(domain: Domain, s: SamplingSettings, quality: Quality): SolveRequest {
  const samplings: SolveRequest['samplings'] = [
    { ...sliceGrid('heat', domain, s, HEAT_RESOLUTION[quality]), quantities: ['B', 'H'] },
    { ...inset(sliceGrid('arrows', domain, s, ARROW_BASE), ARROW_BASE), quantities: MAGNETIC_GRID_QUANTITIES },
  ]
  if (s.mode === '3d') samplings.push({ ...lattice('vol', domain, LATTICE_BASE, 0.5), quantities: ['B', 'H'] })
  return {
    samplings,
    quantities: ['B'],
    quality,
    field_lines: {
      seeding: s.mode === '2d' ? 'planar' : 'spherical',
      sampling_id: 'heat',
      base_lines: 8,
      levels: FIELD_LINE_LEVELS,
      guard_cells: 0.5,
    },
    source_contributions: ['arrows'],
  }
}

/** The kind of field a request asks for (requests never mix the two). */
export function requestKind(request: SolveRequest): FieldKind {
  return (request.quantities as string[]).some((q) => q === 'B' || q === 'H' || q === 'div_B' || q === 'div_H') ? 'magnetic' : 'electric'
}

const rigid = (o: SceneObject) => o.transform.scale.every((v) => v === 1)

/** Sources the magnetostatic model accepts (bookkeeping mirror of `current_sources`): the
 *  source type on its matching primitive; coils, tori and magnets must not be scaled. */
const isWellFormedMagnetic = (o: SceneObject) => {
  switch (o.source?.type) {
    case 'infinite_wire':
      return o.primitive.type === 'line'
    case 'circular_loop':
      return o.primitive.type === 'ring'
    case 'solenoid':
      return o.primitive.type === 'coil' && rigid(o)
    case 'toroid_finite':
    case 'toroid_ideal':
      return o.primitive.type === 'torus' && rigid(o)
    case 'permanent_magnet':
      return o.primitive.type === 'cylinder' && rigid(o)
    default:
      return false
  }
}
const isMagneticRole = (o: SceneObject) => o.role === 'current_source' || o.role === 'magnetic_material'

/** Mirror of the engine's `field_subscene` (bookkeeping, not physics): the objects that can
 *  affect a field of one kind. Used for cache keys, so moving a wire never re-solves the
 *  electric field and moving a charge never re-solves the magnetic field. */
export function fieldScene(scene: Scene, kind: FieldKind): Scene {
  const drop = new Set(
    scene.objects
      .filter((o) => (kind === 'electric' ? isMagneticRole(o) && (isWellFormedMagnetic(o) || !o.enabled) : o.role === 'charge_source' && o.source?.type === 'point_charge'))
      .map((o) => o.id),
  )
  for (;;) {
    const kept = scene.objects.filter((o) => !drop.has(o.id))
    const parents = new Set(kept.map((o) => o.parent_id).filter((x): x is string => !!x))
    for (const id of parents) drop.delete(id)
    const empty = kind === 'magnetic'
      ? kept.filter((o) => o.primitive.type === 'group' && !parents.has(o.id) && scene.objects.some((x) => x.parent_id === o.id) && !drop.has(o.id))
      : []
    if (empty.length === 0) break
    for (const o of empty) drop.add(o.id)
  }
  return { ...scene, objects: scene.objects.filter((o) => !drop.has(o.id)) }
}

/** Which solves a scene needs: magnetic with current sources or magnets; electric with charges
 *  or when there are no magnetic sources (so scenes without currents behave as before).
 *  Mirrors `engine.field_kinds`. */
export function fieldKinds(scene: Scene): FieldKind[] {
  const live = scene.objects.filter((o) => o.enabled)
  const currents = live.some(isMagneticRole)
  const charges = live.some((o) => o.role === 'charge_source')
  const out: FieldKind[] = []
  if (charges || !currents) out.push('electric')
  if (currents) out.push('magnetic')
  return out
}

/** Everything that can change a physical result: the request and the part of the scene that
 *  affects its kind of field. Display-only attributes are excluded, so renaming an object or
 *  changing a colour map never triggers a new solve. */
export function physicsKey(scene: Scene, request: SolveRequest): string {
  return JSON.stringify({ scene: scenePhysics(fieldScene(scene, requestKind(request))), request })
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
