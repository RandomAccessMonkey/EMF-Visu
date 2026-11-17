// A straight arrow from a point along a direction (display only; length chosen by the caller).
import { useMemo } from 'react'
import * as THREE from 'three'

const Y = new THREE.Vector3(0, 1, 0)

export function Arrow3({ from, dir, length, radius, color, renderOrder = 9 }: { from: number[]; dir: number[]; length: number; radius: number; color: string; renderOrder?: number }) {
  const q = useMemo(() => {
    const d = new THREE.Vector3(dir[0] ?? 0, dir[1] ?? 0, dir[2] ?? 0)
    return d.lengthSq() > 0 ? new THREE.Quaternion().setFromUnitVectors(Y, d.normalize()) : null
  }, [dir])
  if (!q || !(length > 0)) return null
  const head = Math.min(length * 0.4, radius * 5)
  return (
    <group position={from as [number, number, number]} quaternion={q}>
      <mesh position={[0, (length - head) / 2, 0]} renderOrder={renderOrder}>
        <cylinderGeometry args={[radius, radius, Math.max(length - head, 1e-9), 6]} />
        <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
      </mesh>
      <mesh position={[0, length - head / 2, 0]} renderOrder={renderOrder}>
        <coneGeometry args={[radius * 2.6, head, 10]} />
        <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
      </mesh>
    </group>
  )
}

export const norm = (v: number[] | null | undefined): number => (v ? Math.hypot(v[0] ?? 0, v[1] ?? 0, v[2] ?? 0) : 0)
