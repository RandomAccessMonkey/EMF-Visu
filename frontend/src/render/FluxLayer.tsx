// Faraday measurement surfaces (Phase 4A): the surface and its oriented boundary (shared with
// the Ampère path drawing), plus the sense in which E_ind circulates, from the engine's EMF sign:
// along the traversal for EMF > 0, against it for EMF < 0 (Lenz). Display only.
import { useMemo } from 'react'
import * as THREE from 'three'
import type { AmperePath, SurfaceResult, Vec3 } from '@/api/types'
import type { InductionData } from '@/sim/useInduction'
import { pathDisplayOf, useSceneStore } from '@/state/sceneStore'
import { localOutline, PathNode } from './AmpereLayer'
import { FLUX_SURFACE_COLOR, INDUCED_E_COLOR } from './magneticColors'

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

export function FluxLayer({ induction, marker }: { induction: InductionData | undefined; marker: number }) {
  const surfaces = useSceneStore((s) => s.fluxSurfaces)
  const selectedId = useSceneStore((s) => s.selectedFluxId)
  const results = new Map((induction?.surfaces ?? []).map((r) => [r.surface_id, r]))
  return (
    <>
      {surfaces.map((p) => {
        const r = results.get(p.id)
        return (
          <group key={p.id}>
            <PathNode path={p} result={r} marker={marker} selected={p.id === selectedId} baseColor={FLUX_SURFACE_COLOR} />
            {r && pathDisplayOf(p).visible && <Circulation path={p} result={r} marker={marker} />}
          </group>
        )
      })}
    </>
  )
}
