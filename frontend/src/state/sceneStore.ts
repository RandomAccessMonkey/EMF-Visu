import { create } from 'zustand'
import type { AmperePath, CoaxSpec, CurrentProfile, Domain, EddyDisk, Electrical, FluxSurface, GaussSurface, PassiveCircuit, PathDisplay, PrimitiveType, Scene, SceneObject, Source, SurfaceDisplay, TestCharge, Transform, Vec3 } from '@/api/types'

export const EMPTY_SCENE: Scene = {
  schema_version: 1,
  dimensionality: '3d',
  objects: [],
  materials: [
    {
      id: 'vacuum',
      name: 'Vacuum',
      model: 'vacuum',
      relative_permittivity: 1,
      relative_permeability: 1,
      conductivity_S_per_m: 0,
    },
  ],
  boundaries: [],
  domain: {
    min_m: [-2, -2, -2],
    max_m: [2, 2, 2],
    background_material_id: 'vacuum',
    potential_reference: 'infinity',
  },
}

const IDENTITY: Transform = {
  position_m: [0, 0, 0],
  rotation_euler_xyz_rad: [0, 0, 0],
  scale: [1, 1, 1],
}

const PRIMITIVE_DEFAULTS: { [K in PrimitiveType]: Extract<SceneObject['primitive'], { type: K }> } = {
  group: { type: 'group', kind: 'generic' },
  point: { type: 'point' },
  sphere: { type: 'sphere', radius_m: 0.25 },
  box: { type: 'box', size_m: [0.5, 0.5, 0.5] },
  cylinder: { type: 'cylinder', radius_m: 0.2, height_m: 0.6 },
  ring: { type: 'ring', radius_m: 0.3 },
  plane: { type: 'plane', width_m: 1, height_m: 1 },
  line: { type: 'line', length_m: 1 },
  coil: { type: 'coil', radius_m: 0.04, length_m: 0.2, turns: 20 },
  torus: { type: 'torus', major_radius_m: 0.12, winding_radius_m: 0.03, core_radius_m: 0.03, turns: 24, phase_rad: 0 },
}

export type NewObjectKind =
  | 'positive_charge'
  | 'negative_charge'
  | 'wire'
  | 'loop'
  | 'solenoid'
  | 'toroid'
  | 'magnet'
  | Exclude<PrimitiveType, 'point' | 'group' | 'coil' | 'torus'>

export type ChargeSource = Extract<Source, { type: 'point_charge' }>
/** Every free-current source; all carry a signed current per turn (A). */
export type CurrentSource = Extract<Source, { current_A: number }>
export type MagnetSource = Extract<Source, { type: 'permanent_magnet' }>
export type ToroidSource = Extract<Source, { type: 'toroid_finite' | 'toroid_ideal' }>
export type ChargeObject = SceneObject & { source: ChargeSource }

/** Charge of a point-charge object, undefined for anything else. */
export const chargeOf = (o: SceneObject): number | undefined =>
  o.source?.type === 'point_charge' ? o.source.charge_C : undefined
/** Current (per turn, A) of a free-current object, undefined for anything else. */
export const currentOf = (o: SceneObject): number | undefined =>
  o.source && 'current_A' in o.source ? o.source.current_A : undefined
/** Magnetization (A/m, along local +z) of a permanent magnet, undefined otherwise. */
export const magnetizationOf = (o: SceneObject): number | undefined =>
  o.source?.type === 'permanent_magnet' ? o.source.magnetization_A_per_m : undefined
export const isCurrentSource = (o: SceneObject): boolean => o.role === 'current_source'
/** Objects the magnetostatic model reads: free currents and magnetized material. */
export const isMagneticSource = (o: SceneObject): boolean => o.role === 'current_source' || o.role === 'magnetic_material'
export const isChargeSource = (o: SceneObject): boolean => o.role === 'charge_source'

/** Rotation (Euler XYZ, radians) that turns local +z into the unit vector d. Geometry only:
 *  wires run along local +z and loops have their normal along local +z. */
export function rotationForDirection(d: Vec3): Vec3 {
  const n = Math.hypot(d[0], d[1], d[2])
  if (!(n > 0)) return [0, 0, 0]
  const [x, y, z] = [d[0] / n, d[1] / n, d[2] / n]
  // R = Rx(a) Ry(b) Rz(0) maps e_z to (sin b, -sin a cos b, cos a cos b).
  const b = Math.asin(Math.max(-1, Math.min(1, x)))
  const a = Math.atan2(-y, z)
  return [a, b, 0]
}

/** World direction of local +z for a root object's rotation (Euler XYZ). Geometry only. */
export function directionOfRotation(r: Vec3): Vec3 {
  const [a, b] = r
  return [Math.sin(b), -Math.sin(a) * Math.cos(b), Math.cos(a) * Math.cos(b)]
}

function freshId(scene: Scene): string {
  const used = new Set(scene.objects.map((o) => o.id))
  let n = scene.objects.length + 1
  while (used.has(`obj${n}`)) n++
  return `obj${n}`
}

export function makeObject(scene: Scene, kind: NewObjectKind, name: string): SceneObject {
  const base = { id: freshId(scene), name, transform: IDENTITY, enabled: true }
  if (kind === 'wire') {
    return { ...base, primitive: { type: 'line', length_m: 4 }, role: 'current_source', source: { type: 'infinite_wire', current_A: 10 } }
  }
  if (kind === 'loop') {
    return { ...base, primitive: { type: 'ring', radius_m: 0.5 }, role: 'current_source', source: { type: 'circular_loop', current_A: 10 } }
  }
  if (kind === 'solenoid') {
    return { ...base, primitive: PRIMITIVE_DEFAULTS.coil, role: 'current_source', source: { type: 'solenoid', current_A: 1 } }
  }
  if (kind === 'toroid') {
    return { ...base, primitive: PRIMITIVE_DEFAULTS.torus, role: 'current_source', source: { type: 'toroid_finite', current_A: 1 } }
  }
  if (kind === 'magnet') {
    return {
      ...base,
      primitive: { type: 'cylinder', radius_m: 0.04, height_m: 0.08 },
      role: 'magnetic_material',
      source: { type: 'permanent_magnet', magnetization_A_per_m: 5e5 },
    }
  }
  if (kind === 'positive_charge' || kind === 'negative_charge') {
    return {
      ...base,
      primitive: PRIMITIVE_DEFAULTS.point,
      role: 'charge_source',
      source: { type: 'point_charge', charge_C: kind === 'positive_charge' ? 1e-9 : -1e-9 },
    }
  }
  return { ...base, primitive: PRIMITIVE_DEFAULTS[kind], role: 'geometry_only', source: null }
}

/** A dipole is two real point charges (+q, −q) under a group; q and d are read from the
 *  children, so there is no second copy of the physics state. */
export interface DipoleInfo {
  positive: ChargeObject
  negative: ChargeObject
  charge_C: number // |q|
  separation_m: number // d
  balanced: boolean // the two charges are still exactly +q and −q
}

export function dipoleInfo(scene: Scene, groupId: string): DipoleInfo | null {
  const kids = scene.objects.filter((o): o is ChargeObject => o.parent_id === groupId && o.source?.type === 'point_charge')
  const positive = kids.find((o) => o.source.charge_C > 0)
  const negative = kids.find((o) => o.source.charge_C < 0)
  if (kids.length !== 2 || !positive || !negative) return null
  const a = positive.transform.position_m
  const b = negative.transform.position_m
  return {
    positive,
    negative,
    charge_C: positive.source.charge_C,
    separation_m: Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
    balanced: positive.source.charge_C === -negative.source.charge_C,
  }
}

export type SurfaceKind = 'sphere' | 'cube' | 'box' | 'cylinder'

export const DEFAULT_DISPLAY: SurfaceDisplay = { visible: true, opacity: 0.3, show_normals: false, color_by_flux: true }

const SURFACE_DEFAULTS: Record<SurfaceKind, GaussSurface['shape']> = {
  sphere: { type: 'sphere', radius_m: 0.8 },
  cube: { type: 'cube', side_m: 1.0 },
  box: { type: 'box', size_m: [1.2, 0.8, 1.0] },
  cylinder: { type: 'cylinder', radius_m: 0.6, height_m: 1.2 },
}

export function makeSurface(existing: GaussSurface[], kind: SurfaceKind, name: string): GaussSurface {
  const used = new Set(existing.map((s) => s.id))
  let n = existing.length + 1
  while (used.has(`S${n}`)) n++
  return {
    id: `S${n}`,
    name,
    shape: SURFACE_DEFAULTS[kind],
    center_m: [0, 0, 0],
    rotation_euler_xyz_rad: [0, 0, 0],
    orientation: 'outward',
    subdivision: null,
    display: { ...DEFAULT_DISPLAY },
  }
}

export const displayOf = (s: GaussSurface): SurfaceDisplay => s.display ?? DEFAULT_DISPLAY

export type PathKind = 'circle' | 'rectangle' | 'polygon'

export const DEFAULT_PATH_DISPLAY: PathDisplay = { visible: true, show_normal: true, show_crossings: true, show_surface: false }

/** Default Ampère path sizes, relative to the domain so they are visible in any scene. */
export function makePath(existing: AmperePath[], kind: PathKind, name: string, domain: Domain): AmperePath {
  const used = new Set(existing.map((p) => p.id))
  let n = existing.length + 1
  while (used.has(`A${n}`)) n++
  const span = Math.min(...[0, 1, 2].map((a) => domain.max_m[a]! - domain.min_m[a]!))
  const r = Math.round(span * 0.25 * 1000) / 1000
  const shape: AmperePath['shape'] =
    kind === 'circle'
      ? { type: 'circle', radius_m: r }
      : kind === 'rectangle'
        ? { type: 'rectangle', width_m: 2 * r, height_m: r }
        : { type: 'polygon', closed: true, vertices_m: [[-r, -r, 0], [r, -r, 0], [r * 0.6, r, 0], [-r * 0.6, r * 0.8, 0]] }
  return {
    id: `A${n}`,
    name,
    shape,
    center_m: [0, 0, 0],
    rotation_euler_xyz_rad: [0, 0, 0],
    reversed: false,
    rtol: 1e-4,
    display: { ...DEFAULT_PATH_DISPLAY },
  }
}

export const pathDisplayOf = (p: AmperePath | FluxSurface): PathDisplay => p.display ?? DEFAULT_PATH_DISPLAY

/** Physics-relevant part of a path (display and name excluded): for cache keys. */
export const pathPhysics = (p: AmperePath | FluxSurface): unknown => ({ ...p, name: '', display: null })

/** Phase 4B: a measurement surface that moves (rigid motion or the sliding-rod circuit). */
export const isMovingSurface = (f: FluxSurface): boolean => !!f.motion || f.shape.type === 'sliding_rod'

export type FluxKind = PathKind | 'sliding_rod'

/** The sliding-rod generator circuit with domain-relative defaults (Phase 4B). */
export function makeSlidingRod(existing: FluxSurface[], name: string, domain: Domain): FluxSurface {
  const base = makePath(existing as AmperePath[], 'rectangle', name, domain)
  const span = Math.min(...[0, 1, 2].map((a) => domain.max_m[a]! - domain.min_m[a]!))
  const len = Math.round(span * 0.5 * 1000) / 1000
  return {
    ...base,
    turns: 1,
    center_m: [-len / 2, 0, 0],
    shape: {
      type: 'sliding_rod',
      rail_separation_m: Math.round(len * 0.4 * 1000) / 1000,
      rail_length_m: len,
      rod_position_m: Math.round(len * 0.1 * 1000) / 1000,
      rod_motion: { type: 'constant_velocity', velocity_m_per_s: [Math.round(len * 1000) / 1000, 0, 0], t0_s: 0 },
    },
  }
}

/** Phase 4C: a passive circuit made from a measurement-surface geometry. Circles get the
 *  thin-loop self-inductance of a 1 mm copper wire; other shapes need a user self-inductance,
 *  and the sliding rod an explicit lumped resistance (its length changes). */
export function electricalFor(path: FluxSurface): Electrical {
  if (path.shape.type === 'circle') return { material: 'copper', wire_radius_m: 0.001, self_inductance: { mode: 'thin_loop' } }
  if (path.shape.type === 'sliding_rod') return { material: 'copper', wire_radius_m: 0.001, resistance_ohm: 0.002, self_inductance: { mode: 'user', value_H: 5e-6 } }
  return { material: 'copper', wire_radius_m: 0.001, self_inductance: { mode: 'user', value_H: 2e-7 } }
}

export function circuitFrom(path: FluxSurface, existing: PassiveCircuit[], name: string): PassiveCircuit {
  const used = new Set(existing.map((c) => c.id))
  let n = existing.length + 1
  while (used.has(`C${n}`)) n++
  const id = `C${n}`
  const rod = path.shape.type === 'sliding_rod'
  return {
    id,
    name,
    path: { ...path, id, display: null },
    electrical: electricalFor(path),
    initial_current_A: 0,
    mechanics: rod ? { mode: 'dynamic', mass_kg: 0.02, initial_velocity_m_per_s: 0.5, external_force_N: 0, damping_N_s_per_m: 0 } : null,
    display: { visible: true, show_current: true },
  }
}

export function makeDisk(existing: EddyDisk[], name: string, domain: Domain): EddyDisk {
  const used = new Set(existing.map((d) => d.id))
  let n = existing.length + 1
  while (used.has(`D${n}`)) n++
  const span = Math.min(...[0, 1, 2].map((a) => domain.max_m[a]! - domain.min_m[a]!))
  const r = Math.round(span * 0.3 * 1000) / 1000
  return {
    id: `D${n}`,
    name,
    center_m: [0, 0, 0],
    rotation_euler_xyz_rad: [0, 0, 0],
    outer_radius_m: r,
    inner_radius_m: 0,
    thickness_m: Math.max(1e-4, Math.round(r * 0.05 * 1e5) / 1e5),
    material: 'copper',
    bands: 10,
    display: { visible: true, show_current: true },
  }
}

/** Default test charge: a proton at the origin moving along +x (Phase 4B). */
export const DEFAULT_TEST_CHARGE: TestCharge = {
  enabled: true,
  charge_C: 1.602176634e-19,
  mass_kg: 1.67262192369e-27,
  position_m: [0, 0, 0],
  velocity_m_per_s: [1e5, 0, 0],
  trajectory: { enabled: false, start_s: 0, end_s: 1e-6, tolerance: 0.02, max_steps: 20000, show_trail: true, show_forces: true },
}

/** Last relative permeability per ideal toroid, so switching to the finite model and back
 *  restores it (the finite model has no core). Display/editing memory only. */
const toroidMu = new Map<string, number>()

/** Switch a toroid between the finite-turn and the ideal model. The primitive keeps both radii
 *  (winding radius for the finite model, core radius for the ideal one), so neither is lost. */
export function toroidWithModel(o: SceneObject, model: ToroidSource['type']): SceneObject {
  const src = o.source
  if (!src || (src.type !== 'toroid_finite' && src.type !== 'toroid_ideal') || src.type === model) return o
  if (src.type === 'toroid_ideal') toroidMu.set(o.id, src.relative_permeability)
  const source: ToroidSource =
    model === 'toroid_ideal'
      ? { type: 'toroid_ideal', current_A: src.current_A, relative_permeability: toroidMu.get(o.id) ?? 1 }
      : { type: 'toroid_finite', current_A: src.current_A }
  return { ...o, source }
}

interface SceneState {
  scene: Scene
  selectedId: string | null
  /** Gaussian surfaces: mathematical integration surfaces, not part of the field model. */
  surfaces: GaussSurface[]
  selectedSurfaceId: string | null
  projectId: string | null
  projectName: string
  presetId: string | null
  /** Scene of the loaded preset (or variant), so an object can be reset to its preset state. */
  presetScene: Scene | null
  select: (id: string | null) => void
  selectSurface: (id: string | null) => void
  addSurface: (kind: SurfaceKind, name: string) => void
  updateSurface: (id: string, patch: Partial<GaussSurface>) => void
  setSurfaceDisplay: (id: string, patch: Partial<SurfaceDisplay>) => void
  removeSurface: (id: string) => void
  setSurfaces: (surfaces: GaussSurface[]) => void
  /** Ampère paths: mathematical integration paths, not part of the field model (Phase 3B). */
  paths: AmperePath[]
  selectedPathId: string | null
  selectPath: (id: string | null) => void
  addPath: (kind: PathKind, name: string) => void
  updatePath: (id: string, patch: Partial<AmperePath>) => void
  setPathDisplay: (id: string, patch: Partial<PathDisplay>) => void
  removePath: (id: string) => void
  setPaths: (paths: AmperePath[]) => void
  /** Faraday measurement surfaces (Phase 4A): stationary planar surfaces bounded by a closed
   *  path, with the same geometry and orientation conventions as Ampère paths. */
  fluxSurfaces: FluxSurface[]
  selectedFluxId: string | null
  selectFlux: (id: string | null) => void
  addFlux: (kind: FluxKind, name: string) => void
  updateFlux: (id: string, patch: Partial<FluxSurface>) => void
  setFluxDisplay: (id: string, patch: Partial<PathDisplay>) => void
  removeFlux: (id: string) => void
  setFluxSurfaces: (surfaces: FluxSurface[]) => void
  /** Test charge for the Lorentz-force probe and its optional trajectory (Phase 4B); null when
   *  none is defined. */
  testCharge: TestCharge | null
  setTestCharge: (tc: TestCharge | null) => void
  /** Passive conducting circuits and eddy-current disks (Phase 4C). */
  circuits: PassiveCircuit[]
  eddyDisks: EddyDisk[]
  selectedCircuitId: string | null
  selectCircuit: (id: string | null) => void
  addCircuit: (kind: FluxKind, name: string) => void
  convertFluxToCircuit: (fluxId: string, name: string) => void
  updateCircuit: (id: string, patch: Partial<PassiveCircuit>) => void
  removeCircuit: (id: string) => void
  setCircuits: (c: PassiveCircuit[]) => void
  addDisk: (name: string) => void
  updateDisk: (id: string, patch: Partial<EddyDisk>) => void
  removeDisk: (id: string) => void
  setDisks: (d: EddyDisk[]) => void
  /** Coaxial-cable TEM model (standalone analytical model; null when not active). While it is
   *  active the viewport shows the cable instead of the scene. */
  coax: CoaxSpec | null
  setCoax: (c: CoaxSpec | null) => void
  /** Set or clear a current source's time profile (Phase 4A). The engine derives the source's
   *  current at t = 0 from the profile; the client never evaluates it. */
  setProfile: (id: string, profile: CurrentProfile | null) => void
  add: (kind: NewObjectKind, name: string) => void
  addDipole: (name: string) => void
  setDipole: (groupId: string, charge_C: number, separation_m: number) => void
  remove: (id: string) => void
  duplicate: (id: string, name: string) => void
  update: (id: string, patch: Partial<SceneObject>) => void
  setTransform: (id: string, patch: Partial<Transform>) => void
  setDomain: (domain: Domain) => void
  resetToPreset: (id: string) => void
  load: (scene: Scene, meta?: { projectId?: string | null; name?: string; presetId?: string | null; presetScene?: Scene | null }) => void
}

const mapObject = (scene: Scene, id: string, f: (o: SceneObject) => SceneObject): Scene => ({
  ...scene,
  objects: scene.objects.map((o) => (o.id === id ? f(o) : o)),
})

export const useSceneStore = create<SceneState>((set) => ({
  scene: EMPTY_SCENE,
  selectedId: null,
  surfaces: [],
  selectedSurfaceId: null,
  projectId: null,
  projectName: '',
  presetId: null,
  presetScene: null,
  // Selecting an object and selecting a surface are mutually exclusive (one gizmo at a time).
  select: (id) => set(id ? { selectedId: id, selectedSurfaceId: null } : { selectedId: null }),
  selectSurface: (id) => set(id ? { selectedSurfaceId: id, selectedId: null } : { selectedSurfaceId: null }),
  addSurface: (kind, name) =>
    set((s) => {
      const surface = makeSurface(s.surfaces, kind, name)
      return { surfaces: [...s.surfaces, surface], selectedSurfaceId: surface.id, selectedId: null }
    }),
  updateSurface: (id, patch) => set((s) => ({ surfaces: s.surfaces.map((x) => (x.id === id ? { ...x, ...patch } : x)) })),
  setSurfaceDisplay: (id, patch) =>
    set((s) => ({ surfaces: s.surfaces.map((x) => (x.id === id ? { ...x, display: { ...displayOf(x), ...patch } } : x)) })),
  removeSurface: (id) =>
    set((s) => ({ surfaces: s.surfaces.filter((x) => x.id !== id), selectedSurfaceId: s.selectedSurfaceId === id ? null : s.selectedSurfaceId })),
  setSurfaces: (surfaces) => set({ surfaces, selectedSurfaceId: surfaces[0]?.id ?? null }),
  paths: [],
  selectedPathId: null,
  selectPath: (id) => set({ selectedPathId: id }),
  addPath: (kind, name) =>
    set((s) => {
      const path = makePath(s.paths, kind, name, s.scene.domain)
      return { paths: [...s.paths, path], selectedPathId: path.id }
    }),
  updatePath: (id, patch) => set((s) => ({ paths: s.paths.map((x) => (x.id === id ? { ...x, ...patch } : x)) })),
  setPathDisplay: (id, patch) =>
    set((s) => ({ paths: s.paths.map((x) => (x.id === id ? { ...x, display: { ...pathDisplayOf(x), ...patch } } : x)) })),
  removePath: (id) =>
    set((s) => ({ paths: s.paths.filter((x) => x.id !== id), selectedPathId: s.selectedPathId === id ? null : s.selectedPathId })),
  setPaths: (paths) => set({ paths, selectedPathId: paths[0]?.id ?? null }),
  fluxSurfaces: [],
  selectedFluxId: null,
  selectFlux: (id) => set({ selectedFluxId: id }),
  addFlux: (kind, name) =>
    set((s) => {
      const base = kind === 'sliding_rod' ? makeSlidingRod(s.fluxSurfaces, name, s.scene.domain) : makePath(s.fluxSurfaces as AmperePath[], kind, name, s.scene.domain)
      const surface: FluxSurface = { turns: 1, ...base, id: base.id.replace(/^A/, 'F'), display: { ...DEFAULT_PATH_DISPLAY, show_surface: true } }
      return { fluxSurfaces: [...s.fluxSurfaces, surface], selectedFluxId: surface.id }
    }),
  updateFlux: (id, patch) => set((s) => ({ fluxSurfaces: s.fluxSurfaces.map((x) => (x.id === id ? { ...x, ...patch } : x)) })),
  setFluxDisplay: (id, patch) =>
    set((s) => ({ fluxSurfaces: s.fluxSurfaces.map((x) => (x.id === id ? { ...x, display: { ...pathDisplayOf(x), ...patch } } : x)) })),
  removeFlux: (id) =>
    set((s) => ({ fluxSurfaces: s.fluxSurfaces.filter((x) => x.id !== id), selectedFluxId: s.selectedFluxId === id ? null : s.selectedFluxId })),
  setFluxSurfaces: (fluxSurfaces) => set({ fluxSurfaces, selectedFluxId: fluxSurfaces[0]?.id ?? null }),
  testCharge: null,
  setTestCharge: (testCharge) => set({ testCharge }),
  circuits: [],
  eddyDisks: [],
  selectedCircuitId: null,
  selectCircuit: (id) => set({ selectedCircuitId: id }),
  addCircuit: (kind, name) =>
    set((s) => {
      const base = kind === 'sliding_rod' ? makeSlidingRod([], name, s.scene.domain) : makePath([], kind, name, s.scene.domain)
      const path: FluxSurface = { turns: 1, ...base }
      const c = circuitFrom(path, s.circuits, name)
      return { circuits: [...s.circuits, c], selectedCircuitId: c.id }
    }),
  convertFluxToCircuit: (fluxId, name) =>
    set((s) => {
      const f = s.fluxSurfaces.find((x) => x.id === fluxId)
      if (!f) return {}
      const c = circuitFrom(f, s.circuits, name)
      return { circuits: [...s.circuits, c], selectedCircuitId: c.id }
    }),
  updateCircuit: (id, patch) => set((s) => ({ circuits: s.circuits.map((c) => (c.id === id ? { ...c, ...patch } : c)) })),
  removeCircuit: (id) => set((s) => ({ circuits: s.circuits.filter((c) => c.id !== id), selectedCircuitId: s.selectedCircuitId === id ? null : s.selectedCircuitId })),
  setCircuits: (circuits) => set({ circuits, selectedCircuitId: circuits[0]?.id ?? null }),
  addDisk: (name) => set((s) => ({ eddyDisks: [...s.eddyDisks, makeDisk(s.eddyDisks, name, s.scene.domain)] })),
  updateDisk: (id, patch) => set((s) => ({ eddyDisks: s.eddyDisks.map((d) => (d.id === id ? { ...d, ...patch } : d)) })),
  removeDisk: (id) => set((s) => ({ eddyDisks: s.eddyDisks.filter((d) => d.id !== id) })),
  setDisks: (eddyDisks) => set({ eddyDisks }),
  coax: null,
  setCoax: (coax) => set({ coax }),
  setProfile: (id, profile) =>
    set((s) => ({
      scene: mapObject(s.scene, id, (o) =>
        o.source && 'current_A' in o.source ? { ...o, source: { ...o.source, profile } as typeof o.source } : o,
      ),
    })),
  add: (kind, name) =>
    set((s) => {
      const obj = makeObject(s.scene, kind, name)
      return { scene: { ...s.scene, objects: [...s.scene.objects, obj] }, selectedId: obj.id }
    }),
  addDipole: (name) =>
    set((s) => {
      const used = new Set(s.scene.objects.map((o) => o.id))
      let n = 1
      while (used.has(`dipole${n}`)) n++
      const gid = `dipole${n}`
      const child = (suffix: string, label: string, q: number, x: number): SceneObject => ({
        id: `${gid}_${suffix}`,
        name: label,
        primitive: PRIMITIVE_DEFAULTS.point,
        transform: { ...IDENTITY, position_m: [x, 0, 0] },
        parent_id: gid,
        role: 'charge_source',
        source: { type: 'point_charge', charge_C: q },
        enabled: true,
      })
      const group: SceneObject = {
        id: gid,
        name,
        primitive: { type: 'group', kind: 'dipole' },
        transform: IDENTITY,
        role: 'geometry_only',
        source: null,
        enabled: true,
      }
      const objects = [...s.scene.objects, group, child('pos', 'q₊', 1e-9, -0.5), child('neg', 'q₋', -1e-9, 0.5)]
      return { scene: { ...s.scene, objects }, selectedId: gid }
    }),
  setDipole: (groupId, charge_C, separation_m) =>
    set((s) => {
      const info = dipoleInfo(s.scene, groupId)
      if (!info || !(separation_m > 0) || !(charge_C > 0)) return s
      // Keep the midpoint and the axis direction; only the magnitude and the separation change.
      const a = info.positive.transform.position_m
      const b = info.negative.transform.position_m
      const mid = a.map((v, i) => (v + b[i]!) / 2)
      const axis = b.map((v, i) => (v - a[i]!) / info.separation_m)
      const at = (sign: number) => mid.map((m, i) => m + (sign * axis[i]! * separation_m) / 2) as [number, number, number]
      const objects = s.scene.objects.map((o) => {
        if (o.id === info.positive.id)
          return { ...o, source: { type: 'point_charge' as const, charge_C }, transform: { ...o.transform, position_m: at(-1) } }
        if (o.id === info.negative.id)
          return { ...o, source: { type: 'point_charge' as const, charge_C: -charge_C }, transform: { ...o.transform, position_m: at(1) } }
        return o
      })
      return { scene: { ...s.scene, objects } }
    }),
  remove: (id) =>
    set((s) => {
      // Removing a group removes everything inside it.
      const doomed = new Set([id])
      let grew = true
      while (grew) {
        grew = false
        for (const o of s.scene.objects)
          if (o.parent_id && doomed.has(o.parent_id) && !doomed.has(o.id)) {
            doomed.add(o.id)
            grew = true
          }
      }
      return {
        scene: { ...s.scene, objects: s.scene.objects.filter((o) => !doomed.has(o.id)) },
        selectedId: s.selectedId && doomed.has(s.selectedId) ? null : s.selectedId,
      }
    }),
  duplicate: (id, name) =>
    set((s) => {
      const src = s.scene.objects.find((o) => o.id === id)
      if (!src) return s
      const p = src.transform.position_m
      const copy: SceneObject = {
        ...src,
        id: freshId(s.scene),
        name,
        transform: { ...src.transform, position_m: [p[0] + 0.25, p[1] + 0.25, p[2]] },
      }
      return { scene: { ...s.scene, objects: [...s.scene.objects, copy] }, selectedId: copy.id }
    }),
  update: (id, patch) => set((s) => ({ scene: mapObject(s.scene, id, (o) => ({ ...o, ...patch })) })),
  setTransform: (id, patch) =>
    set((s) => ({
      scene: mapObject(s.scene, id, (o) => ({ ...o, transform: { ...o.transform, ...patch } })),
    })),
  setDomain: (domain) => set((s) => ({ scene: { ...s.scene, domain } })),
  resetToPreset: (id) =>
    set((s) => {
      const original = s.presetScene?.objects.find((o) => o.id === id)
      return original ? { scene: mapObject(s.scene, id, () => original) } : s
    }),
  load: (scene, meta) =>
    set({
      scene,
      selectedId: null,
      projectId: meta?.projectId ?? null,
      projectName: meta?.name ?? '',
      presetId: meta?.presetId ?? null,
      presetScene: meta?.presetScene ?? (meta?.presetId ? scene : null),
    }),
}))
