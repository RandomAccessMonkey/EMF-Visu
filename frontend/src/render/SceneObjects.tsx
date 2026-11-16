import { TransformControls } from '@react-three/drei'
import { useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { SceneObject, Vec3 } from '@/api/types'
import { PLANE_BASIS } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const groups = new Map<string, THREE.Group>()
const COLORS = { positive: '#ff7a59', negative: '#4aa8ff', neutral: '#9aa7bd', inert: '#7c8db0' }

function chargeColor(o: SceneObject): string {
  const q = o.source?.charge_C ?? 0
  return q > 0 ? COLORS.positive : q < 0 ? COLORS.negative : COLORS.neutral
}

function Shape({ o, marker }: { o: SceneObject; marker: number }) {
  const p = o.primitive
  const inert = (
    <meshStandardMaterial color={COLORS.inert} transparent opacity={0.3} roughness={0.6} side={THREE.DoubleSide} />
  )
  switch (p.type) {
    case 'point':
      return (
        <mesh>
          <sphereGeometry args={[marker, 24, 16]} />
          <meshBasicMaterial color={chargeColor(o)} toneMapped={false} />
        </mesh>
      )
    case 'sphere':
      return <mesh><sphereGeometry args={[p.radius_m, 32, 20]} />{inert}</mesh>
    case 'box':
      return <mesh><boxGeometry args={p.size_m} />{inert}</mesh>
    case 'cylinder': // axis along local z
      return (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[p.radius_m, p.radius_m, p.height_m, 32]} />
          {inert}
        </mesh>
      )
    case 'ring':
      return <mesh><torusGeometry args={[p.radius_m, marker * 0.35, 12, 64]} />{inert}</mesh>
    case 'plane':
      return <mesh><planeGeometry args={[p.width_m, p.height_m]} />{inert}</mesh>
    case 'line': // along local z
      return (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[marker * 0.3, marker * 0.3, p.length_m, 12]} />
          {inert}
        </mesh>
      )
  }
}

function ObjectNode({ o, marker }: { o: SceneObject; marker: number }) {
  const ref = useRef<THREE.Group>(null)
  const children = useSceneStore((s) => s.scene.objects).filter((c) => c.parent_id === o.id)
  const selected = useSceneStore((s) => s.selectedId === o.id)
  const { select, setTransform } = useSceneStore.getState()
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const drag = useRef<{ plane: THREE.Plane } | null>(null)
  const [hover, setHover] = useState(false)

  useEffect(() => {
    const g = ref.current
    if (!g) return
    groups.set(o.id, g)
    return () => void groups.delete(o.id)
  }, [o.id])

  const onPointerDown = (e: ThreeEvent<PointerEvent>) => {
    if (tool !== 'select' || e.button !== 0) return
    e.stopPropagation()
    select(o.id)
    if (mode !== '2d' || !ref.current) return
    const view = useViewStore.getState()
    const world = ref.current.getWorldPosition(new THREE.Vector3())
    const normal = new THREE.Vector3(...PLANE_BASIS[view.plane].normal)
    drag.current = { plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, world) }
    ;(e.target as Element).setPointerCapture(e.pointerId)
    view.set({ dragging: true })
  }
  const onPointerMove = (e: ThreeEvent<PointerEvent>) => {
    const g = ref.current
    if (!drag.current || !g?.parent) return
    e.stopPropagation()
    const hit = e.ray.intersectPlane(drag.current.plane, new THREE.Vector3())
    if (!hit) return
    const view = useViewStore.getState()
    const local = g.parent.worldToLocal(hit)
    const b = PLANE_BASIS[view.plane]
    const next = [local.x, local.y, local.z] as Vec3
    if (view.snap && view.snapStep > 0) {
      for (const a of [b.uAxis, b.vAxis]) next[a] = Math.round(next[a]! / view.snapStep) * view.snapStep
    }
    next[b.nAxis] = o.transform.position_m[b.nAxis]! // dragging never leaves the slice-parallel plane
    setTransform(o.id, { position_m: next })
  }
  const onPointerUp = (e: ThreeEvent<PointerEvent>) => {
    if (!drag.current) return
    drag.current = null
    ;(e.target as Element).releasePointerCapture(e.pointerId)
    useViewStore.getState().set({ dragging: false })
  }

  return (
    <group
      ref={ref}
      position={o.transform.position_m}
      rotation={o.transform.rotation_euler_xyz_rad}
      scale={o.transform.scale}
    >
      <group
        visible={o.enabled}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerOver={() => setHover(true)}
        onPointerOut={() => setHover(false)}
      >
        <Shape o={o} marker={marker} />
        {(selected || hover) && o.primitive.type === 'point' && (
          <mesh>
            <sphereGeometry args={[marker * 1.9, 24, 16]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={selected ? 0.28 : 0.14} depthWrite={false} />
          </mesh>
        )}
      </group>
      {children.map((c) => (
        <ObjectNode key={c.id} o={c} marker={marker} />
      ))}
    </group>
  )
}

/** 3D manipulation gizmo for the selected object (translate / rotate / scale). */
function Gizmo() {
  const selectedId = useSceneStore((s) => s.selectedId)
  const objectCount = useSceneStore((s) => s.scene.objects.length)
  const transformMode = useViewStore((s) => s.transformMode)
  const snap = useViewStore((s) => (s.snap ? s.snapStep : null))
  const invalidate = useThree((s) => s.invalidate)
  const [target, setTarget] = useState<THREE.Group | null>(null)
  useEffect(() => {
    setTarget(selectedId ? (groups.get(selectedId) ?? null) : null)
  }, [selectedId, objectCount])
  if (!target || !selectedId) return null
  return (
    <TransformControls
      object={target}
      mode={transformMode}
      size={0.7}
      translationSnap={snap}
      rotationSnap={snap ? Math.PI / 12 : null}
      onMouseDown={() => useViewStore.getState().set({ dragging: true })}
      onMouseUp={() => useViewStore.getState().set({ dragging: false })}
      onObjectChange={() => {
        useSceneStore.getState().setTransform(selectedId, {
          position_m: target.position.toArray() as Vec3,
          rotation_euler_xyz_rad: [target.rotation.x, target.rotation.y, target.rotation.z],
          scale: target.scale.toArray() as Vec3,
        })
        invalidate()
      }}
    />
  )
}

export function SceneObjects({ marker }: { marker: number }) {
  const objects = useSceneStore((s) => s.scene.objects)
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const roots = useMemo(() => objects.filter((o) => !o.parent_id), [objects])
  return (
    <>
      {roots.map((o) => (
        <ObjectNode key={o.id} o={o} marker={marker} />
      ))}
      {mode === '3d' && tool === 'select' && <Gizmo />}
    </>
  )
}
