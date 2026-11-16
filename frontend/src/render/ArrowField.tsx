import { useThree } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { logT, sequential, type LogScale } from './colormaps'

/** Unit-length arrow along +Y, centred on its sample point. */
function arrowGeometry(): THREE.BufferGeometry {
  const shaft = new THREE.CylinderGeometry(0.035, 0.035, 0.62, 8, 1)
  shaft.translate(0, -0.19, 0)
  const head = new THREE.ConeGeometry(0.13, 0.38, 12, 1)
  head.translate(0, 0.31, 0)
  return mergeGeometries([shaft, head])
}

interface Props {
  points: Float32Array // (N, 3) sample positions, metres
  vectors: Float32Array // (N, 3) field vectors from the engine
  magnitudes: Float32Array // (N) |vector|
  scale: LogScale // colour (and optionally length) range
  cell: number // sample spacing, metres
  lengthMode: 'uniform' | 'log'
  sizeFactor: number
}

const UP = new THREE.Vector3(0, 1, 0)

/** Instanced field arrows: one draw call for the whole field. Direction is the field
 *  direction; colour encodes magnitude on the legend's log scale. Arrow length is either
 *  uniform (direction only) or log-scaled magnitude — a visualization choice, stated in the UI. */
export function ArrowField({ points, vectors, magnitudes, scale, cell, lengthMode, sizeFactor }: Props) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const geometry = useMemo(arrowGeometry, [])
  const count = magnitudes.length

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const pos = new THREE.Vector3()
    const dir = new THREE.Vector3()
    const size = new THREE.Vector3()
    const color = new THREE.Color()
    const rgb = [0, 0, 0]
    for (let i = 0; i < count; i++) {
      const mag = magnitudes[i]!
      const t = Math.min(1, Math.max(0, logT(mag, scale)))
      // Undefined (singular) or exactly zero field: draw nothing rather than a fake direction.
      let len = 0
      if (Number.isFinite(mag) && mag > 0) {
        len = cell * 0.85 * sizeFactor * (lengthMode === 'log' ? 0.25 + 0.75 * t : 1)
        dir.set(vectors[3 * i]! / mag, vectors[3 * i + 1]! / mag, vectors[3 * i + 2]! / mag)
        q.setFromUnitVectors(UP, dir)
      }
      pos.set(points[3 * i]!, points[3 * i + 1]!, points[3 * i + 2]!)
      m.compose(pos, q, size.setScalar(len))
      mesh.setMatrixAt(i, m)
      sequential(0.25 + 0.75 * t, rgb)
      mesh.setColorAt(i, color.setRGB(rgb[0]! / 255, rgb[1]! / 255, rgb[2]! / 255, THREE.SRGBColorSpace))
    }
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    invalidate()
  }, [points, vectors, magnitudes, scale, cell, lengthMode, sizeFactor, count, invalidate])

  return (
    <instancedMesh key={count} ref={ref} args={[geometry, undefined, count]} frustumCulled={false}>
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  )
}
