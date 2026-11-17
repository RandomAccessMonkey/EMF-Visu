// Test charge (Phase 4B): its position, velocity v and the electric, magnetic and total Lorentz
// forces from the engine's probe; the computed trajectory, and the computed sample at the
// current simulation time with its own v and forces. Arrow lengths are display choices (scaled
// to the largest force shown); directions and values come from the engine.
import { Line } from '@react-three/drei'
import { useMemo } from 'react'
import type { Vec3 } from '@/api/types'
import type { LorentzData } from '@/sim/useLorentz'
import { useSceneStore } from '@/state/sceneStore'
import { Arrow3, norm } from './Arrow3'
import {
  FORCE_B_COLOR,
  FORCE_E_COLOR,
  FORCE_TOTAL_COLOR,
  PARTICLE_COLOR,
  PARTICLE_VELOCITY_COLOR,
  TRAJECTORY_COLOR,
} from './magneticColors'

function Forces({ at, fe, fb, ft, marker }: { at: number[]; fe?: number[] | null; fb?: number[] | null; ft?: number[] | null; marker: number }) {
  const scale = Math.max(1e-300, norm(fe), norm(fb), norm(ft))
  const len = (f: number[] | null | undefined) => (marker * 7 * norm(f)) / scale
  return (
    <>
      {fe && norm(fe) > 0 && <Arrow3 from={at} dir={fe} length={len(fe)} radius={marker * 0.13} color={FORCE_E_COLOR} />}
      {fb && norm(fb) > 0 && <Arrow3 from={at} dir={fb} length={len(fb)} radius={marker * 0.13} color={FORCE_B_COLOR} />}
      {ft && norm(ft) > 0 && <Arrow3 from={at} dir={ft} length={len(ft)} radius={marker * 0.16} color={FORCE_TOTAL_COLOR} />}
    </>
  )
}

export function LorentzLayer({ data, marker }: { data: LorentzData; marker: number }) {
  const tc = useSceneStore((s) => s.testCharge)
  const traj = data.trajectory
  const points = useMemo(() => (traj ? traj.samples.map((s) => s.position_m as Vec3) : []), [traj])
  if (!tc || !tc.enabled) return null
  const p = data.probe
  const cur = data.current
  const showForces = tc.trajectory.show_forces
  return (
    <group>
      <mesh position={tc.position_m as Vec3} renderOrder={9}>
        <sphereGeometry args={[marker * 0.7, 16, 12]} />
        <meshBasicMaterial color={PARTICLE_COLOR} depthTest={false} toneMapped={false} />
      </mesh>
      {norm(tc.velocity_m_per_s) > 0 && <Arrow3 from={tc.position_m} dir={tc.velocity_m_per_s} length={marker * 6} radius={marker * 0.12} color={PARTICLE_VELOCITY_COLOR} />}
      {p && showForces && <Forces at={tc.position_m} fe={p.F_E_N} fb={p.F_B_N} ft={p.F_total_N} marker={marker} />}
      {tc.trajectory.enabled && tc.trajectory.show_trail && points.length > 1 && <Line points={points} color={TRAJECTORY_COLOR} lineWidth={1.5} />}
      {cur && (
        <group>
          <mesh position={cur.position_m as Vec3} renderOrder={9}>
            <sphereGeometry args={[marker * 0.55, 14, 10]} />
            <meshBasicMaterial color={TRAJECTORY_COLOR} depthTest={false} toneMapped={false} />
          </mesh>
          {norm(cur.velocity_m_per_s) > 0 && <Arrow3 from={cur.position_m} dir={cur.velocity_m_per_s} length={marker * 5} radius={marker * 0.1} color={PARTICLE_VELOCITY_COLOR} />}
          {showForces && <Forces at={cur.position_m} fe={cur.F_E_N} fb={cur.F_B_N} ft={cur.F_total_N} marker={marker} />}
        </group>
      )}
    </group>
  )
}
