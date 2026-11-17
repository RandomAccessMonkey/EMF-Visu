// Magnetic layers (Phase 3A). Everything drawn here is read from the magnetic result: B and H
// samples (total and per source) and the engine's table of current sources. No field value is
// computed here; the only arithmetic is geometry (where a loop crosses the slice plane).
import { Billboard, Html } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { SimulationResult } from '@/api/container'
import type { CurrentSourceInfo, LatticeSampling, PlaneGridSampling, Vec3 } from '@/api/types'
import { formatSI } from '@/lib/format'
import { PLANE_BASIS, subsampleLattice, subsamplePlane } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { ArrowField } from './ArrowField'
import type { LogScale } from './colormaps'
import { magnitudes, sampling } from './fieldImages'
import { CONTRIBUTION_COLORS, MAGNETIC_SOURCE_COLOR } from './magneticColors'

/** The contribution actually shown: a saved choice that no longer fits the scene (a removed
 *  source, or 'all' with fewer than two sources) falls back to the total field. */
export function effectiveContribution(choice: string, ids: string[]): string {
  if (choice === 'all') return ids.length > 1 ? 'all' : 'total'
  return ids.includes(choice) ? choice : 'total'
}

/** Name of the vector array for the chosen field and contribution ('total' or a source id). */
export const magneticArrayName = (id: 'arrows' | 'vol', field: 'B' | 'H', contribution: string) =>
  contribution === 'total' || contribution === 'all' ? `${id}.${field}` : `${id}.${field}@${contribution}`

export const contributionColor = (ids: string[], id: string) =>
  CONTRIBUTION_COLORS[Math.max(0, ids.indexOf(id)) % CONTRIBUTION_COLORS.length]!

function samples(result: SimulationResult, id: 'arrows' | 'vol', name: string, density: number) {
  const field = result.arrays[name]
  if (!field) return null
  if (id === 'arrows') {
    const g = sampling<PlaneGridSampling>(result, id)
    if (!g) return null
    const sub = subsamplePlane(g, field.data, density)
    return { ...sub, mags: magnitudes(sub.vectors) }
  }
  const l = sampling<LatticeSampling>(result, id)
  if (!l) return null
  const sub = subsampleLattice(l, field.data, density)
  return { ...sub, cell: sub.cell * 0.7, mags: magnitudes(sub.vectors) }
}

/** B or H arrows on the magnetic palette: the total field, one source's own field, or (mode
 *  'all', vector grid only) every source's own field in its own colour at the same points, so
 *  reinforcement and opposition are visible directly. */
export function MagneticArrows({ result, id, scale }: { result: SimulationResult; id: 'arrows' | 'vol'; scale: LogScale }) {
  const lengthMode = useViewStore((s) => s.arrowLength)
  const sizeFactor = useViewStore((s) => s.arrowScale)
  const field = useViewStore((s) => s.magneticField)
  const choice = useViewStore((s) => s.contribution)
  const density = useViewStore((s) => (id === 'arrows' ? s.arrowDensity : s.latticeDensity))
  const ids = useMemo(() => result.header.current_sources.map((c) => c.object_id), [result])
  const contribution = effectiveContribution(choice, ids)
  const layers = useMemo(() => {
    if (contribution === 'all' && id === 'arrows') {
      return ids.map((oid) => ({ data: samples(result, id, `${id}.${field}@${oid}`, density), color: contributionColor(ids, oid) }))
    }
    // The 3D lattice carries the total field only.
    const name = id === 'vol' ? `${id}.${field}` : magneticArrayName(id, field, contribution)
    return [{ data: samples(result, id, name, density), color: undefined }]
  }, [result, id, field, contribution, density, ids])
  return (
    <>
      {layers.map(({ data, color }, i) =>
        data ? (
          <ArrowField
            key={color ?? i}
            points={data.points}
            vectors={data.vectors}
            magnitudes={data.mags}
            scale={scale}
            cell={data.cell}
            lengthMode={color ? 'log' : lengthMode}
            sizeFactor={sizeFactor}
            palette="magnetic"
            solidColor={color}
          />
        ) : null,
      )}
    </>
  )
}

interface Crossing {
  key: string
  p: Vec3
  sign: number // +1 current towards the viewer (⊙), -1 away (⊗)
  label: string
}

/** Where the current sources cross the 2D slice, with the current direction relative to the
 *  viewer: ⊙ out of the screen, ⊗ into it. Wires: from the engine's table. Loops: the circle
 *  is intersected with the slice plane (geometry), and the sign is that of the loop tangent
 *  (normal × radial, times the sign of I) along the plane normal. */
export function currentCrossings(sources: CurrentSourceInfo[], center: Vec3, normal: Vec3, samplingId: string): Crossing[] {
  const n = new THREE.Vector3(...normal)
  const c0 = new THREE.Vector3(...center)
  const out: Crossing[] = []
  for (const s of sources) {
    const label = formatSI(s.current_A, 'A')
    if (s.kind === 'infinite_wire') {
      const p = s.plane_crossing_m[samplingId]
      const sign = s.plane_crossing_sign[samplingId] ?? 0
      if (p && sign !== 0) out.push({ key: s.object_id, p: p as Vec3, sign, label })
      continue
    }
    const nl = new THREE.Vector3(...s.direction)
    const cl = new THREE.Vector3(...s.point_m)
    const a = s.radius_m ?? 0
    // Points of the loop circle on the plane: cl + a(cos t e1 + sin t e2) with (·)·n = (c0 - cl)·n
    const e1 = new THREE.Vector3().crossVectors(nl, n)
    if (e1.lengthSq() < 1e-18) continue // loop parallel to the slice: it does not cross it
    e1.normalize()
    const e2 = new THREE.Vector3().crossVectors(nl, e1) // in the loop plane, ⊥ e1
    const k = e2.dot(n)
    const rhs = c0.clone().sub(cl).dot(n) / a
    if (Math.abs(k) < 1e-12 || Math.abs(rhs / k) > 1) continue
    const st = rhs / k
    for (const ct of [Math.sqrt(1 - st * st), -Math.sqrt(1 - st * st)]) {
      const radial = e1.clone().multiplyScalar(ct).add(e2.clone().multiplyScalar(st))
      const p = cl.clone().add(radial.clone().multiplyScalar(a))
      const tangent = new THREE.Vector3().crossVectors(nl, radial).multiplyScalar(Math.sign(s.current_A))
      const sign = Math.sign(tangent.dot(n))
      if (sign !== 0) out.push({ key: `${s.object_id}:${ct > 0 ? 1 : 2}`, p: p.toArray() as Vec3, sign, label })
    }
  }
  return out
}

export function CurrentMarkers({ result, size }: { result: SimulationResult; size: number }) {
  const mode = useViewStore((s) => s.mode)
  const plane = useViewStore((s) => s.plane)
  const showDir = useViewStore((s) => s.showCurrentDirection)
  const selectedId = useSceneStore((s) => s.selectedId)
  const grid = sampling<PlaneGridSampling>(result, 'heat')
  const crossings = useMemo(
    () => (grid ? currentCrossings(result.header.current_sources, grid.center_m, PLANE_BASIS[plane].normal, 'heat') : []),
    [result, grid, plane],
  )
  if (mode !== '2d' || !showDir) return null
  return (
    <>
      {crossings.map((c) => (
        <Billboard key={c.key} position={c.p}>
          <mesh renderOrder={6}>
            <ringGeometry args={[size * 1.5, size * 1.9, 32]} />
            <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} depthTest={false} toneMapped={false} />
          </mesh>
          {c.sign > 0 ? (
            <mesh renderOrder={6}>
              <circleGeometry args={[size * 0.5, 20]} />
              <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} depthTest={false} toneMapped={false} />
            </mesh>
          ) : (
            [Math.PI / 4, -Math.PI / 4].map((r) => (
              <mesh key={r} rotation={[0, 0, r]} renderOrder={6}>
                <planeGeometry args={[size * 2.6, size * 0.4]} />
                <meshBasicMaterial color={MAGNETIC_SOURCE_COLOR} depthTest={false} toneMapped={false} />
              </mesh>
            ))
          )}
          {selectedId && c.key.startsWith(selectedId) && (
            <Html position={[size * 2.4, size * 2.4, 0]} style={{ pointerEvents: 'none' }} zIndexRange={[10, 0]}>
              <span className="select-none whitespace-nowrap font-mono text-[10px]" style={{ color: MAGNETIC_SOURCE_COLOR }}>
                {c.sign > 0 ? '⊙' : '⊗'} {c.label}
              </span>
            </Html>
          )}
        </Billboard>
      ))}
    </>
  )
}
