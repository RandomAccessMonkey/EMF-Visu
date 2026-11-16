// Pure helpers for the divergence/curl/source layers (no rendering; unit-tested).
import type { SimulationResult } from '@/api/container'
import type { PlaneGridSampling, Vec3 } from '@/api/types'
import type { VectorSamples } from '@/sim/request'
import { sampling } from './fieldImages'

/** Split vector samples into exact zeros, nonzero vectors and undefined samples. */
export function partitionVectors(s: VectorSamples) {
  const zero: number[] = []
  const nonzero: number[] = []
  let undef = 0
  for (let i = 0; i < s.points.length / 3; i++) {
    const x = s.vectors[3 * i]!
    const y = s.vectors[3 * i + 1]!
    const z = s.vectors[3 * i + 2]!
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) undef++
    else if (x === 0 && y === 0 && z === 0) zero.push(i)
    else nonzero.push(i)
  }
  return { zero, nonzero, undef }
}

export interface SourceMarker {
  id: string
  name: string
  charge_C: number
  position: Vec3 // true 3D position
  shownAt: Vec3 // where the marker is drawn (the projection onto the slice for off-slice charges)
  ghost: boolean // off-slice charge seen in the 2D view
  axis: 'x' | 'y' | 'z'
  delta: number // coordinate difference along the slice normal axis, metres (2D only)
  divEWeight: number
  divDWeight: number
}

/** Marker model from the engine's source table. In 2D a charge off the slice plane is a
 *  projection (ghost), never a singularity inside the slice. */
export function sourceMarkers(result: SimulationResult, mode: '2d' | '3d', names: Record<string, string>): SourceMarker[] {
  const grid = sampling<PlaneGridSampling>(result, 'heat')
  const n: Vec3 = grid
    ? [
        grid.u_dir[1] * grid.v_dir[2] - grid.u_dir[2] * grid.v_dir[1],
        grid.u_dir[2] * grid.v_dir[0] - grid.u_dir[0] * grid.v_dir[2],
        grid.u_dir[0] * grid.v_dir[1] - grid.u_dir[1] * grid.v_dir[0],
      ]
    : [0, 0, 1]
  const axisIndex = n.findIndex((c) => Math.abs(c) === 1)
  return result.header.point_sources.map((s) => {
    const pos = s.position_m as Vec3
    const d = s.plane_distance_m['heat'] ?? 0
    const ghost = mode === '2d' && s.in_plane['heat'] === false
    return {
      id: s.object_id,
      name: names[s.object_id] ?? s.object_id,
      charge_C: s.charge_C,
      position: pos,
      shownAt: ghost ? (pos.map((c, a) => c - d * n[a]!) as Vec3) : pos,
      ghost,
      axis: (['x', 'y', 'z'] as const)[axisIndex >= 0 ? axisIndex : 2]!,
      delta: axisIndex >= 0 ? d * n[axisIndex]! : d,
      divEWeight: s.div_E_weight_V_m,
      divDWeight: s.div_D_weight_C,
    }
  })
}

