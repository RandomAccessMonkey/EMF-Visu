// Drawing of the Phase 3B sources in object-local coordinates (the parent group applies the
// object's position and rotation). Geometry only: turn positions follow the engine's rules
// (solenoid z_k = −L/2 + kL/(N−1); toroid φ_k = phase + 2πk/N with turn normal e_φ), and the
// current direction marks follow the right-hand rule about each turn's normal.
import { Html } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { SceneObject } from '@/api/types'
import { useViewStore } from '@/state/viewStore'
import { CORE_COLOR, MAGNET_COLOR, MAGNET_SOUTH_COLOR, MAGNETIC_SOURCE_COLOR } from './magneticColors'

const Y = new THREE.Vector3(0, 1, 0)
const SEGMENTS = 64

type Coil = Extract<SceneObject['primitive'], { type: 'coil' }>
type Torus = Extract<SceneObject['primitive'], { type: 'torus' }>
type Cylinder = Extract<SceneObject['primitive'], { type: 'cylinder' }>

export function solenoidTurnZ(turns: number, length: number): number[] {
  if (turns === 1) return [0]
  return Array.from({ length: turns }, (_, k) => -length / 2 + (k * length) / (turns - 1))
}

export function toroidTurnAngles(turns: number, phase: number): number[] {
  return Array.from({ length: turns }, (_, k) => phase + (2 * Math.PI * k) / turns)
}

/** Circles (centre, unit normal, in-plane unit u, radius) as one line-segment geometry. */
function circlesGeometry(circles: { c: THREE.Vector3; n: THREE.Vector3; u: THREE.Vector3; r: number }[]): THREE.BufferGeometry {
  const pos = new Float32Array(circles.length * SEGMENTS * 6)
  let k = 0
  for (const { c, n, u, r } of circles) {
    const v = new THREE.Vector3().crossVectors(n, u)
    const at = (i: number) => {
      const t = (2 * Math.PI * i) / SEGMENTS
      return c.clone().addScaledVector(u, r * Math.cos(t)).addScaledVector(v, r * Math.sin(t))
    }
    for (let i = 0; i < SEGMENTS; i++) {
      const a = at(i)
      const b = at(i + 1)
      pos.set([a.x, a.y, a.z, b.x, b.y, b.z], k)
      k += 6
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  return g
}

/** Cones showing the current direction on a circle: tangent = sign(I) · n × radial. */
function TurnArrows({ c, n, u, r, sign, size, count = 4 }: { c: THREE.Vector3; n: THREE.Vector3; u: THREE.Vector3; r: number; sign: number; size: number; count?: number }) {
  const arrows = useMemo(() => {
    const v = new THREE.Vector3().crossVectors(n, u)
    return Array.from({ length: count }, (_, k) => {
      const t = (2 * Math.PI * k) / count + Math.PI / count
      const radial = u.clone().multiplyScalar(Math.cos(t)).addScaledVector(v, Math.sin(t))
      const tangent = new THREE.Vector3().crossVectors(n, radial).multiplyScalar(sign)
      return { p: c.clone().addScaledVector(radial, r), q: new THREE.Quaternion().setFromUnitVectors(Y, tangent) }
    })
  }, [c, n, u, r, sign, count])
  return (
    <>
      {arrows.map((a, i) => (
        <mesh key={i} position={a.p} quaternion={a.q}>
          <coneGeometry args={[size * 0.55, size * 1.5, 10]} />
          <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} toneMapped={false} />
        </mesh>
      ))}
    </>
  )
}

const EZ = new THREE.Vector3(0, 0, 1)
const EX = new THREE.Vector3(1, 0, 0)

export function CoilBody({ p, current, marker, highlight }: { p: Coil; current: number; marker: number; highlight: boolean }) {
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const zs = useMemo(() => solenoidTurnZ(p.turns, p.length_m), [p.turns, p.length_m])
  const geometry = useMemo(
    () => circlesGeometry(zs.map((z) => ({ c: new THREE.Vector3(0, 0, z), n: EZ, u: EX, r: p.radius_m }))),
    [zs, p.radius_m],
  )
  const ends = useMemo(() => [zs[0]!, zs[zs.length - 1]!].map((z) => new THREE.Vector3(0, 0, z)), [zs])
  const len = p.turns > 1 ? p.length_m : 0
  return (
    <>
      <lineSegments geometry={geometry}>
        <lineBasicMaterial color={highlight ? '#f3e8ff' : MAGNETIC_SOURCE_COLOR} toneMapped={false} />
      </lineSegments>
      {/* Faint winding envelope, for picking and orientation (not a physical surface). */}
      {len > 0 && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[p.radius_m, p.radius_m, len, 32, 1, true]} />
          <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} transparent opacity={highlight ? 0.12 : 0.05} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {showDir && current !== 0 &&
        ends.map((c, i) => <TurnArrows key={i} c={c} n={EZ} u={EX} r={p.radius_m} sign={Math.sign(current)} size={marker} count={3} />)}
    </>
  )
}

export function TorusBody({ p, source, marker, highlight }: { p: Torus; source: NonNullable<SceneObject['source']>; marker: number; highlight: boolean }) {
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const ideal = source.type === 'toroid_ideal'
  const current = 'current_A' in source ? source.current_A : 0
  const turns = useMemo(
    () =>
      toroidTurnAngles(p.turns, p.phase_rad).map((phi) => {
        const eRho = new THREE.Vector3(Math.cos(phi), Math.sin(phi), 0)
        const ePhi = new THREE.Vector3(-Math.sin(phi), Math.cos(phi), 0)
        return { c: eRho.clone().multiplyScalar(p.major_radius_m), n: ePhi, u: eRho, r: p.winding_radius_m }
      }),
    [p.turns, p.phase_rad, p.major_radius_m, p.winding_radius_m],
  )
  const geometry = useMemo(() => (ideal ? null : circlesGeometry(turns)), [turns, ideal])
  // Ideal model: the continuous winding is drawn as a few schematic rings on the core surface.
  const schematic = useMemo(
    () =>
      ideal
        ? circlesGeometry(
            toroidTurnAngles(24, p.phase_rad).map((phi) => ({
              c: new THREE.Vector3(Math.cos(phi), Math.sin(phi), 0).multiplyScalar(p.major_radius_m),
              n: new THREE.Vector3(-Math.sin(phi), Math.cos(phi), 0),
              u: new THREE.Vector3(Math.cos(phi), Math.sin(phi), 0),
              r: p.core_radius_m * 1.02,
            })),
          )
        : null,
    [ideal, p.phase_rad, p.major_radius_m, p.core_radius_m],
  )
  const arrowTurns = turns.length > 0 ? [turns[0]!, turns[Math.floor(turns.length / 2)]!] : []
  if (ideal) {
    return (
      <>
        <mesh>
          <torusGeometry args={[p.major_radius_m, p.core_radius_m, 24, 96]} />
          <meshStandardMaterial color={CORE_COLOR} transparent opacity={highlight ? 0.45 : 0.3} roughness={0.5} depthWrite={false} />
        </mesh>
        <lineSegments geometry={schematic!}>
          <lineBasicMaterial color={highlight ? '#f3e8ff' : MAGNETIC_SOURCE_COLOR} transparent opacity={0.45} toneMapped={false} />
        </lineSegments>
      </>
    )
  }
  return (
    <>
      <lineSegments geometry={geometry!}>
        <lineBasicMaterial color={highlight ? '#f3e8ff' : MAGNETIC_SOURCE_COLOR} toneMapped={false} />
      </lineSegments>
      {showDir && current !== 0 && arrowTurns.map((tg, i) => <TurnArrows key={i} {...tg} sign={Math.sign(current)} size={marker} count={2} />)}
    </>
  )
}

/** A uniformly magnetized cylinder: the half towards +M is drawn red (north end), the other
 *  blue (south end); an arrow along the axis shows M; rings with arrows on the side wall show
 *  the bound surface current K = M × n (current-direction marks enabled). */
export function MagnetBody({ p, magnetization, marker, highlight }: { p: Cylinder; magnetization: number; marker: number; highlight: boolean }) {
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const sign = Math.sign(magnetization) || 1
  const half = p.height_m / 2
  const rings = useMemo(() => [-0.25, 0.25].map((f) => new THREE.Vector3(0, 0, f * p.height_m)), [p.height_m])
  const arrowQ = useMemo(() => new THREE.Quaternion().setFromUnitVectors(Y, EZ.clone().multiplyScalar(sign)), [sign])
  const material = (color: string) => <meshStandardMaterial color={color} transparent opacity={highlight ? 0.75 : 0.55} roughness={0.5} />
  const ringsGeometry = useMemo(() => circlesGeometry(rings.map((c) => ({ c, n: EZ, u: EX, r: p.radius_m * 1.005 }))), [rings, p.radius_m])
  return (
    <>
      {[1, -1].map((s) => (
        <mesh key={s} position={[0, 0, (s * half) / 2]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[p.radius_m, p.radius_m, half, 40]} />
          {material(s === sign ? MAGNET_COLOR : MAGNET_SOUTH_COLOR)}
        </mesh>
      ))}
      {magnetization !== 0 && (
        <group quaternion={arrowQ}>
          <mesh position={[0, 0, 0]}>
            <cylinderGeometry args={[marker * 0.2, marker * 0.2, p.height_m * 0.6, 8]} />
            <meshBasicMaterial color="#ffffff" depthTest={false} toneMapped={false} />
          </mesh>
          <mesh position={[0, p.height_m * 0.33, 0]}>
            <coneGeometry args={[marker * 0.6, marker * 1.6, 12]} />
            <meshBasicMaterial color="#ffffff" depthTest={false} toneMapped={false} />
          </mesh>
        </group>
      )}
      {(['N', 'S'] as const).map((label) => (
        <Html key={label} position={[0, 0, (label === 'N' ? sign : -sign) * (half + marker * 1.8)]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <span className="select-none font-mono text-[11px] font-bold" style={{ color: label === 'N' ? MAGNET_COLOR : MAGNET_SOUTH_COLOR }}>
            {magnetization === 0 ? '' : label}
          </span>
        </Html>
      ))}
      {showDir && magnetization !== 0 && (
        <>
          <lineSegments geometry={ringsGeometry}>
            <lineBasicMaterial color={MAGNETIC_SOURCE_COLOR} transparent opacity={0.6} toneMapped={false} />
          </lineSegments>
          {rings.map((c, i) => <TurnArrows key={i} c={c} n={EZ} u={EX} r={p.radius_m * 1.005} sign={sign} size={marker * 0.8} count={3} />)}
        </>
      )}
    </>
  )
}
