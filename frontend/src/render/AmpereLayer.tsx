// Ampère paths in the viewport: the closed outline with its traversal direction, the positive
// surface normal (right-hand rule), an optional translucent spanning surface, and the signed
// crossings of free currents reported by the engine. Paths are mathematical integration paths,
// not physical objects.
import { Billboard, Html } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { AmperePath, PathResult, Vec3 } from '@/api/types'
import type { AmpereData } from '@/sim/useAmpere'
import { pathDisplayOf, useSceneStore } from '@/state/sceneStore'
import { AMPERE_PATH_COLOR } from './magneticColors'

const Y = new THREE.Vector3(0, 1, 0)
const INVALID_COLOR = '#f59e0b'

/** Local outline (path frame) in traversal order, closed implicitly. Circle and rectangle run
 *  counter-clockwise about local +z; a polygon follows its vertex order; `reversed` flips it. */
export function localOutline(path: AmperePath, circleSegments = 96): THREE.Vector3[] {
  const sh = path.shape
  let pts: THREE.Vector3[]
  if (sh.type === 'circle') {
    pts = Array.from({ length: circleSegments }, (_, i) => {
      const t = (2 * Math.PI * i) / circleSegments
      return new THREE.Vector3(sh.radius_m * Math.cos(t), sh.radius_m * Math.sin(t), 0)
    })
  } else if (sh.type === 'rectangle') {
    const w = sh.width_m / 2
    const h = sh.height_m / 2
    pts = [new THREE.Vector3(-w, -h, 0), new THREE.Vector3(w, -h, 0), new THREE.Vector3(w, h, 0), new THREE.Vector3(-w, h, 0)]
  } else {
    pts = sh.vertices_m.map((v) => new THREE.Vector3(...v))
  }
  return path.reversed ? pts.reverse() : pts
}

/** Right-hand normal of a closed outline (Newell's method); zero for a degenerate outline. */
export function outlineNormal(pts: THREE.Vector3[]): THREE.Vector3 {
  const n = new THREE.Vector3()
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i]!
    const b = pts[(i + 1) % pts.length]!
    n.x += (a.y - b.y) * (a.z + b.z)
    n.y += (a.z - b.z) * (a.x + b.x)
    n.z += (a.x - b.x) * (a.y + b.y)
  }
  return n.lengthSq() > 0 ? n.normalize() : n
}

function PathNode({ path, result, marker, selected }: { path: AmperePath; result: PathResult | undefined; marker: number; selected: boolean }) {
  const d = pathDisplayOf(path)
  const pts = useMemo(() => localOutline(path), [path])
  const normal = useMemo(() => outlineNormal(pts), [pts])
  const centroid = useMemo(() => pts.reduce((c, p) => c.add(p), new THREE.Vector3()).multiplyScalar(1 / Math.max(1, pts.length)), [pts])
  const invalid = result?.status === 'invalid'
  const color = invalid ? INVALID_COLOR : AMPERE_PATH_COLOR
  const line = useMemo(() => new THREE.BufferGeometry().setFromPoints([...pts, pts[0] ?? new THREE.Vector3()]), [pts])
  // Traversal arrows at a few points along the outline.
  const arrows = useMemo(() => {
    if (pts.length < 2) return []
    const n = Math.min(pts.length, path.shape.type === 'circle' ? 4 : pts.length)
    return Array.from({ length: n }, (_, k) => {
      const i = Math.floor((k * pts.length) / n)
      const a = pts[i]!
      const b = pts[(i + 1) % pts.length]!
      const dir = b.clone().sub(a)
      if (dir.lengthSq() === 0) return null
      const mid = path.shape.type === 'circle' ? a : a.clone().add(b).multiplyScalar(0.5)
      return { p: mid, q: new THREE.Quaternion().setFromUnitVectors(Y, dir.normalize()) }
    }).filter((x): x is { p: THREE.Vector3; q: THREE.Quaternion } => x !== null)
  }, [pts, path.shape.type])
  const surface = useMemo(() => {
    if (!d.show_surface || invalid || pts.length < 3) return null
    const shape = new THREE.Shape(pts.map((p) => new THREE.Vector2(p.x, p.y)))
    return new THREE.ShapeGeometry(shape, 48)
  }, [d.show_surface, invalid, pts])
  const size = Math.max(...pts.map((p) => p.distanceTo(centroid)), marker)
  const normalLen = Math.max(marker * 4, size * 0.4)
  const nq = useMemo(() => new THREE.Quaternion().setFromUnitVectors(Y, normal.lengthSq() > 0 ? normal : Y), [normal])
  if (!d.visible) return null
  return (
    <group position={path.center_m} rotation={path.rotation_euler_xyz_rad as Vec3}>
      <lineLoop geometry={line}>
        <lineBasicMaterial color={selected ? '#ecfdf5' : color} toneMapped={false} depthTest={false} transparent opacity={0.95} />
      </lineLoop>
      {arrows.map((a, i) => (
        <mesh key={i} position={a.p} quaternion={a.q} renderOrder={7}>
          <coneGeometry args={[marker * 0.5, marker * 1.4, 10]} />
          <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
        </mesh>
      ))}
      {surface && (
        <mesh geometry={surface} position={[0, 0, pts[0]?.z ?? 0]}>
          <meshBasicMaterial color={color} transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {d.show_normal && !invalid && normal.lengthSq() > 0 && (
        <group position={centroid} quaternion={nq}>
          <mesh position={[0, normalLen / 2, 0]}>
            <cylinderGeometry args={[marker * 0.12, marker * 0.12, normalLen, 6]} />
            <meshBasicMaterial color={color} toneMapped={false} />
          </mesh>
          <mesh position={[0, normalLen, 0]}>
            <coneGeometry args={[marker * 0.45, marker * 1.2, 10]} />
            <meshBasicMaterial color={color} toneMapped={false} />
          </mesh>
          <Html position={[0, normalLen + marker * 1.5, 0]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
            <span className="select-none font-mono text-[10px]" style={{ color }}>n̂ {path.name || path.id}</span>
          </Html>
        </group>
      )}
    </group>
  )
}

/** Crossing markers in world coordinates: green along the normal, red against it, amber when
 *  the crossing lies on the path or is ambiguous. */
function Crossings({ result, marker }: { result: PathResult; marker: number }) {
  const crossings = result.enclosure?.crossings ?? []
  return (
    <>
      {crossings.map((c, i) => {
        const color = c.state !== 'inside' || c.sign === 0 ? INVALID_COLOR : c.contribution_A >= 0 ? '#22c55e' : '#ef4444'
        return (
          <Billboard key={i} position={c.point_m as Vec3}>
            <mesh renderOrder={8}>
              <ringGeometry args={[marker * 0.9, marker * 1.25, 24]} />
              <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
            </mesh>
          </Billboard>
        )
      })}
    </>
  )
}

export function AmpereLayer({ ampere, marker }: { ampere: AmpereData | undefined; marker: number }) {
  const paths = useSceneStore((s) => s.paths)
  const selectedId = useSceneStore((s) => s.selectedPathId)
  const results = new Map((ampere?.paths ?? []).map((r) => [r.path_id, r]))
  return (
    <>
      {paths.map((p) => {
        const r = results.get(p.id)
        const d = pathDisplayOf(p)
        return (
          <group key={p.id}>
            <PathNode path={p} result={r} marker={marker} selected={p.id === selectedId} />
            {r && d.visible && d.show_crossings && <Crossings result={r} marker={marker} />}
          </group>
        )
      })}
    </>
  )
}
