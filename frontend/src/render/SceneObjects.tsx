import { Billboard, Html, TransformControls } from '@react-three/drei'
import { useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { SceneObject, Vec3 } from '@/api/types'
import { PLANE_BASIS } from '@/sim/request'
import { chargeOf, useSceneStore } from '@/state/sceneStore'
import { MAGNETIC_SOURCE_COLOR } from './magneticColors'
import { useViewStore } from '@/state/viewStore'

const groups = new Map<string, THREE.Group>()
const COLORS = { positive: '#ff7a59', negative: '#4aa8ff', neutral: '#9aa7bd', inert: '#7c8db0' }

function chargeColor(o: SceneObject): string {
  const q = chargeOf(o) ?? 0
  return q > 0 ? COLORS.positive : q < 0 ? COLORS.negative : COLORS.neutral
}

const Z = new THREE.Vector3(0, 0, 1)
const Y = new THREE.Vector3(0, 1, 0)

/** Static chevrons along local +z (the positive current direction) times the sign of I. */
function Chevrons({ positions, sign, size }: { positions: THREE.Vector3[]; sign: number; size: number }) {
  const q = new THREE.Quaternion().setFromUnitVectors(Y, Z.clone().multiplyScalar(sign >= 0 ? 1 : -1))
  return (
    <>
      {positions.map((p, i) => (
        <mesh key={i} position={p} quaternion={q}>
          <coneGeometry args={[size * 0.55, size * 1.5, 12]} />
          <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} toneMapped={false} />
        </mesh>
      ))}
    </>
  )
}

/** An infinite wire, drawn as a segment across the region with "∞" at its ends: the drawn ends
 *  are not physical ends. Local +z is the positive current direction. */
function WireBody({ o, marker, length, highlight }: { o: SceneObject; marker: number; length: number; highlight: boolean }) {
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const I = o.source?.type === 'infinite_wire' ? o.source.current_A : 0
  const half = length / 2
  const chevrons = useMemo(() => [-0.3, 0, 0.3].map((f) => new THREE.Vector3(0, 0, f * length)), [length])
  return (
    <>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[marker * (highlight ? 0.5 : 0.28), marker * (highlight ? 0.5 : 0.28), length, 12]} />
        <meshBasicMaterial color={highlight ? '#f3e8ff' : MAGNETIC_SOURCE_COLOR} toneMapped={false} transparent opacity={0.9} />
      </mesh>
      {showDir && I !== 0 && <Chevrons positions={chevrons} sign={Math.sign(I)} size={marker} />}
      {[-half, half].map((z) => (
        <Html key={z} position={[0, 0, z]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <span className="select-none font-mono text-[11px]" style={{ color: MAGNETIC_SOURCE_COLOR }}>∞</span>
        </Html>
      ))}
    </>
  )
}

/** A thin circular loop in its local xy plane, with arrowheads along the current direction
 *  (counter-clockwise about local +z for positive current). */
function LoopBody({ o, marker, highlight }: { o: SceneObject; marker: number; highlight: boolean }) {
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const radius = o.primitive.type === 'ring' ? o.primitive.radius_m : 0
  const I = o.source?.type === 'circular_loop' ? o.source.current_A : 0
  const arrows = useMemo(
    () => [0, 1, 2, 3].map((k) => {
      const a = (k * Math.PI) / 2 + Math.PI / 4
      const tangent = new THREE.Vector3(-Math.sin(a), Math.cos(a), 0).multiplyScalar(Math.sign(I) || 1)
      return { p: new THREE.Vector3(radius * Math.cos(a), radius * Math.sin(a), 0), q: new THREE.Quaternion().setFromUnitVectors(Y, tangent) }
    }),
    [radius, I],
  )
  return (
    <>
      <mesh>
        <torusGeometry args={[radius, marker * (highlight ? 0.5 : 0.28), 10, 96]} />
        <meshBasicMaterial color={highlight ? '#f3e8ff' : MAGNETIC_SOURCE_COLOR} toneMapped={false} />
      </mesh>
      {showDir && I !== 0 && arrows.map((a, i) => (
        <mesh key={i} position={a.p} quaternion={a.q}>
          <coneGeometry args={[marker * 0.55, marker * 1.5, 12]} />
          <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} toneMapped={false} />
        </mesh>
      ))}
    </>
  )
}

function Shape({ o, marker, ghost, wireLength, highlight }: { o: SceneObject; marker: number; ghost: boolean; wireLength: number; highlight: boolean }) {
  const p = o.primitive
  if (o.source?.type === 'infinite_wire' && p.type === 'line') return <WireBody o={o} marker={marker} length={wireLength} highlight={highlight} />
  if (o.source?.type === 'circular_loop' && p.type === 'ring') return <LoopBody o={o} marker={marker} highlight={highlight} />
  const inert = (
    <meshStandardMaterial color={COLORS.inert} transparent opacity={0.3} roughness={0.6} side={THREE.DoubleSide} />
  )
  switch (p.type) {
    case 'group': // no geometry of its own: a small handle to select and move the whole group
      return (
        <mesh>
          <octahedronGeometry args={[marker * 0.9, 0]} />
          <meshBasicMaterial color="#c4b5fd" wireframe toneMapped={false} />
        </mesh>
      )
    case 'point':
      // In the 2D view a charge that does not lie in the slice is drawn hollow: it is seen
      // through the slice, not a singularity inside it.
      return ghost ? (
        <Billboard>
          <mesh>
            <ringGeometry args={[marker * 0.65, marker, 28]} />
            <meshBasicMaterial color={chargeColor(o)} transparent opacity={0.6} toneMapped={false} />
          </mesh>
        </Billboard>
      ) : (
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

function ObjectNode({ o, marker, offSlice, wireLength }: { o: SceneObject; marker: number; offSlice: ReadonlySet<string>; wireLength: number }) {
  const ref = useRef<THREE.Group>(null)
  const children = useSceneStore((s) => s.scene.objects).filter((c) => c.parent_id === o.id)
  const selected = useSceneStore((s) => s.selectedId === o.id)
  const { select, setTransform } = useSceneStore.getState()
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const showCurrents = useViewStore((s) => s.showCurrents)
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
        {(o.role !== 'current_source' || showCurrents) && (
          <Shape o={o} marker={marker} ghost={mode === '2d' && offSlice.has(o.id)} wireLength={wireLength} highlight={selected || hover} />
        )}
        {(selected || hover) && (o.primitive.type === 'point' || o.primitive.type === 'group') && (
          <mesh>
            <sphereGeometry args={[marker * 1.9, 24, 16]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={selected ? 0.28 : 0.14} depthWrite={false} />
          </mesh>
        )}
      </group>
      {children.map((c) => (
        <ObjectNode key={c.id} o={c} marker={marker} offSlice={offSlice} wireLength={wireLength} />
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

export function SceneObjects({ marker, offSlice, wireLength }: { marker: number; offSlice: ReadonlySet<string>; wireLength: number }) {
  const objects = useSceneStore((s) => s.scene.objects)
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const roots = useMemo(() => objects.filter((o) => !o.parent_id), [objects])
  return (
    <>
      {roots.map((o) => (
        <ObjectNode key={o.id} o={o} marker={marker} offSlice={offSlice} wireLength={wireLength} />
      ))}
      {mode === '3d' && tool === 'select' && <Gizmo />}
    </>
  )
}
