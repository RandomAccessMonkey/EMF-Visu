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
  point: { type: 'point' },
  sphere: { type: 'sphere', radius_m: 0.25 },
  box: { type: 'box', size_m: [0.5, 0.5, 0.5] },
  cylinder: { type: 'cylinder', radius_m: 0.2, height_m: 0.6 },
  ring: { type: 'ring', radius_m: 0.3 },
  plane: { type: 'plane', width_m: 1, height_m: 1 },
  line: { type: 'line', length_m: 1 },
}

export type NewObjectKind = 'positive_charge' | 'negative_charge' | Exclude<PrimitiveType, 'point'>

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

interface SceneState {
  scene: Scene
  selectedId: string | null
  projectId: string | null
  projectName: string
  presetId: string | null
  select: (id: string | null) => void
  add: (kind: NewObjectKind, name: string) => void
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
  remove: (id) =>
    set((s) => ({
      scene: {
        ...s.scene,
        objects: s.scene.objects
          .filter((o) => o.id !== id)
          .map((o) => (o.parent_id === id ? { ...o, parent_id: null } : o)),
      },
      selectedId: s.selectedId === id ? null : s.selectedId,
    })),
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
