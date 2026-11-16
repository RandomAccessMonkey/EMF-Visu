import { create } from 'zustand'
import type { Domain, PrimitiveType, Scene, SceneObject, Transform } from '@/api/types'

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
}

export type NewObjectKind = 'positive_charge' | 'negative_charge' | Exclude<PrimitiveType, 'point' | 'group'>

function freshId(scene: Scene): string {
  const used = new Set(scene.objects.map((o) => o.id))
  let n = scene.objects.length + 1
  while (used.has(`obj${n}`)) n++
  return `obj${n}`
}

export function makeObject(scene: Scene, kind: NewObjectKind, name: string): SceneObject {
  const base = { id: freshId(scene), name, transform: IDENTITY, enabled: true }
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
  positive: SceneObject
  negative: SceneObject
  charge_C: number // |q|
  separation_m: number // d
  balanced: boolean // the two charges are still exactly +q and −q
}

export function dipoleInfo(scene: Scene, groupId: string): DipoleInfo | null {
  const kids = scene.objects.filter((o) => o.parent_id === groupId && o.source)
  const positive = kids.find((o) => (o.source?.charge_C ?? 0) > 0)
  const negative = kids.find((o) => (o.source?.charge_C ?? 0) < 0)
  if (kids.length !== 2 || !positive || !negative) return null
  const a = positive.transform.position_m
  const b = negative.transform.position_m
  return {
    positive,
    negative,
    charge_C: positive.source!.charge_C,
    separation_m: Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]),
    balanced: positive.source!.charge_C === -negative.source!.charge_C,
  }
}

interface SceneState {
  scene: Scene
  selectedId: string | null
  projectId: string | null
  projectName: string
  presetId: string | null
  select: (id: string | null) => void
  add: (kind: NewObjectKind, name: string) => void
  addDipole: (name: string) => void
  setDipole: (groupId: string, charge_C: number, separation_m: number) => void
  remove: (id: string) => void
  duplicate: (id: string, name: string) => void
  update: (id: string, patch: Partial<SceneObject>) => void
  setTransform: (id: string, patch: Partial<Transform>) => void
  setDomain: (domain: Domain) => void
  load: (scene: Scene, meta?: { projectId?: string | null; name?: string; presetId?: string | null }) => void
}

const mapObject = (scene: Scene, id: string, f: (o: SceneObject) => SceneObject): Scene => ({
  ...scene,
  objects: scene.objects.map((o) => (o.id === id ? f(o) : o)),
})

export const useSceneStore = create<SceneState>((set) => ({
  scene: EMPTY_SCENE,
  selectedId: null,
  projectId: null,
  projectName: '',
  presetId: null,
  select: (id) => set({ selectedId: id }),
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
          return { ...o, source: { ...o.source!, charge_C }, transform: { ...o.transform, position_m: at(-1) } }
        if (o.id === info.negative.id)
          return { ...o, source: { ...o.source!, charge_C: -charge_C }, transform: { ...o.transform, position_m: at(1) } }
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
  load: (scene, meta) =>
    set({
      scene,
      selectedId: null,
      projectId: meta?.projectId ?? null,
      projectName: meta?.name ?? '',
      presetId: meta?.presetId ?? null,
    }),
}))
