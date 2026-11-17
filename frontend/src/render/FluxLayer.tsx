// Faraday measurement surfaces (Phase 4A): the surface and its oriented boundary (shared with
// the Ampère path drawing), plus the sense in which E_ind circulates, from the engine's EMF sign:
// along the traversal for EMF > 0, against it for EMF < 0 (Lenz). Display only.
//
// Phase 4B: a moving surface is drawn where the engine placed it at the simulation time (its
// world polyline, normal and centre come from the result, never from client-side motion), with
// the conductor velocity u and the motional term u × B at the engine's sample points, and for
// the sliding rod the stationary rails apart from the moving rod.
import { Html, Line } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { AmperePath, FluxSurface, SurfaceResult, Vec3 } from '@/api/types'
import type { InductionData } from '@/sim/useInduction'
import { isMovingSurface, pathDisplayOf, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { localOutline, PathNode } from './AmpereLayer'
import { Arrow3, norm } from './Arrow3'
import {
  CONDUCTOR_VELOCITY_COLOR,
  FLUX_SURFACE_COLOR,
  INDUCED_E_COLOR,
  MOTIONAL_COLOR,
  MOVING_SEGMENT_COLOR,
  STATIONARY_SEGMENT_COLOR,
} from './magneticColors'

const Y = new THREE.Vector3(0, 1, 0)

/** Cones along the boundary, slightly inside it, pointing the way E_ind circulates. */
function Circulation({ path, result, marker }: { path: AmperePath; result: SurfaceResult; marker: number }) {
  const sense = result.lenz?.circulation
  const cones = useMemo(() => {
    if (sense !== 'along_path' && sense !== 'against_path') return []
    const pts = localOutline(path)
    const c = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).multiplyScalar(1 / pts.length)
    const n = Math.min(8, pts.length * 2)
    return Array.from({ length: n }, (_, k) => {
      const f = (k * pts.length) / n
      const i = Math.floor(f)
      const a = pts[i % pts.length]!
      const b = pts[(i + 1) % pts.length]!
      const p = a.clone().lerp(b, f - i)
      const inward = p.clone().lerp(c, 0.12)
      const dir = b.clone().sub(a).normalize().multiplyScalar(sense === 'along_path' ? 1 : -1)
      return { p: inward, q: new THREE.Quaternion().setFromUnitVectors(Y, dir) }
    })
  }, [path, sense])
  return (
    <group position={path.center_m} rotation={path.rotation_euler_xyz_rad as Vec3}>
      {cones.map((c, i) => (
        <mesh key={i} position={c.p} quaternion={c.q} renderOrder={8}>
          <coneGeometry args={[marker * 0.6, marker * 1.8, 12]} />
          <meshBasicMaterial color={INDUCED_E_COLOR} depthTest={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

/** Triangles of a planar world polygon (projected onto its own plane for triangulation). */
function planarFill(pts: THREE.Vector3[], normal: THREE.Vector3): THREE.BufferGeometry | null {
  if (pts.length < 3 || normal.lengthSq() === 0) return null
  const u = new THREE.Vector3().crossVectors(normal, Math.abs(normal.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).normalize()
  const v = new THREE.Vector3().crossVectors(normal, u)
  const flat = pts.map((p) => new THREE.Vector2(p.dot(u), p.dot(v)))
  const tris = THREE.ShapeUtils.triangulateShape(flat, [])
  const g = new THREE.BufferGeometry().setFromPoints(pts)
  g.setIndex(tris.flat())
  return g
}

function MovingSurface({ f, r, marker, selected }: { f: FluxSurface; r: SurfaceResult; marker: number; selected: boolean }) {
  const d = pathDisplayOf(f)
  const showVectors = useViewStore((s) => s.showMotionVectors)
  const pts = useMemo(() => {
    const p = r.polyline_m.map((q) => new THREE.Vector3(q[0], q[1], q[2]))
    return p.length > 1 && p[0]!.distanceTo(p[p.length - 1]!) === 0 ? p.slice(0, -1) : p
  }, [r.polyline_m])
  const normal = useMemo(() => new THREE.Vector3(...((r.normal ?? [0, 0, 1]) as Vec3)), [r.normal])
  const fill = useMemo(() => (d.show_surface ? planarFill(pts, normal) : null), [d.show_surface, pts, normal])
  const rod = r.motion?.kind === 'sliding_rod'
  const size = Math.max(...pts.map((p) => p.distanceTo(new THREE.Vector3(...((r.center_m ?? [0, 0, 0]) as Vec3)))), marker)
  const samples = r.motional_samples
  const uMax = Math.max(1e-300, ...samples.map((s) => norm(s.u_m_per_s)))
  const eMax = Math.max(1e-300, ...samples.map((s) => norm(s.u_cross_B_V_per_m)))
  const sense = r.lenz?.circulation
  const cones = useMemo(() => {
    if ((sense !== 'along_path' && sense !== 'against_path') || pts.length < 2) return []
    const n = Math.min(8, pts.length)
    return Array.from({ length: n }, (_, k) => {
      const i = Math.floor((k * pts.length) / n)
      const a = pts[i]!
      const b = pts[(i + 1) % pts.length]!
      const dir = b.clone().sub(a).normalize().multiplyScalar(sense === 'along_path' ? 1 : -1)
      return { p: a.clone().lerp(b, 0.5), q: new THREE.Quaternion().setFromUnitVectors(Y, dir) }
    })
  }, [pts, sense])
  if (!d.visible) return null
  const color = selected ? '#ecfdf5' : rod ? STATIONARY_SEGMENT_COLOR : FLUX_SURFACE_COLOR
  return (
    <group>
      {!rod && pts.length > 1 && <Line points={[...pts, pts[0]!]} color={color} lineWidth={selected ? 2.5 : 1.8} depthTest={false} />}
      {rod && r.motion?.rails_m.map((seg, i) => <Line key={i} points={seg as Vec3[]} color={STATIONARY_SEGMENT_COLOR} lineWidth={2} depthTest={false} />)}
      {rod && r.motion && r.motion.rod_m.length === 2 && <Line points={r.motion.rod_m as Vec3[]} color={selected ? '#ecfdf5' : MOVING_SEGMENT_COLOR} lineWidth={4} depthTest={false} />}
      {fill && (
        <mesh geometry={fill}>
          <meshBasicMaterial color={FLUX_SURFACE_COLOR} transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {d.show_normal && r.center_m && (
        <>
          <Arrow3 from={r.center_m} dir={r.normal ?? [0, 0, 1]} length={Math.max(marker * 4, size * 0.4)} radius={marker * 0.12} color={FLUX_SURFACE_COLOR} />
          <Html position={(r.center_m as Vec3).map((c, i) => c + (r.normal?.[i] ?? 0) * (Math.max(marker * 4, size * 0.4) + marker * 1.5)) as Vec3} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
            <span className="select-none font-mono text-[10px]" style={{ color: FLUX_SURFACE_COLOR }}>n̂ {f.name || f.id}</span>
          </Html>
        </>
      )}
      {showVectors &&
        samples.map((s, i) => (
          <group key={i}>
            {s.moving && norm(s.u_m_per_s) > 0 && <Arrow3 from={s.point_m} dir={s.u_m_per_s} length={(marker * 5 * norm(s.u_m_per_s)) / uMax} radius={marker * 0.1} color={CONDUCTOR_VELOCITY_COLOR} />}
            {s.u_cross_B_V_per_m && norm(s.u_cross_B_V_per_m) > 0 && (
              <Arrow3 from={s.point_m} dir={s.u_cross_B_V_per_m} length={(marker * 4 * norm(s.u_cross_B_V_per_m)) / eMax} radius={marker * 0.1} color={MOTIONAL_COLOR} />
            )}
          </group>
        ))}
      {cones.map((c, i) => (
        <mesh key={`c${i}`} position={c.p} quaternion={c.q} renderOrder={8}>
          <coneGeometry args={[marker * 0.6, marker * 1.8, 12]} />
          <meshBasicMaterial color={INDUCED_E_COLOR} depthTest={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

export function FluxLayer({ induction, marker }: { induction: InductionData | undefined; marker: number }) {
  const surfaces = useSceneStore((s) => s.fluxSurfaces)
  const selectedId = useSceneStore((s) => s.selectedFluxId)
  const results = new Map((induction?.surfaces ?? []).map((r) => [r.surface_id, r]))
  return (
    <>
      {surfaces.map((p) => {
        const r = results.get(p.id)
        if (isMovingSurface(p)) {
          // Drawn only from an engine result (its pose at the simulation time).
          return r && r.polyline_m.length > 0 ? <MovingSurface key={p.id} f={p} r={r} marker={marker} selected={p.id === selectedId} /> : null
        }
        const path = p as AmperePath
        return (
          <group key={p.id}>
            <PathNode path={path} result={r} marker={marker} selected={p.id === selectedId} baseColor={FLUX_SURFACE_COLOR} />
            {r && pathDisplayOf(p).visible && <Circulation path={path} result={r} marker={marker} />}
          </group>
        )
      })}
    </>
  )
}
