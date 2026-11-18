// Passive circuits and eddy-current bands (Phase 4C): each drawn at the geometry and with the
// induced current of the engine's solution sample for the current simulation time. Colour
// encodes the sign of the induced current (relative to the circuit's traversal), cones its
// direction; prescribed source currents keep their own (purple) style.
import { Html, Line } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { PassiveFilament, Vec3 } from '@/api/types'
import type { CircuitsData } from '@/sim/useCircuits'
import { formatSI } from '@/lib/format'

const Y = new THREE.Vector3(0, 1, 0)
export const INDUCED_POS = '#f472b6' // induced current along the traversal
export const INDUCED_NEG = '#38bdf8' // induced current against the traversal
const IDLE = '#94a3b8'

/** Points of a filament in its positive-current order (closed implicitly). */
export function filamentPoints(f: PassiveFilament, n = 64): THREE.Vector3[] {
  if (f.kind === 'circle') {
    const c = new THREE.Vector3(...(f.center_m as Vec3))
    const nrm = new THREE.Vector3(...(f.normal as Vec3)).normalize()
    const u = new THREE.Vector3(...(f.u as Vec3)).normalize()
    const v = new THREE.Vector3().crossVectors(nrm, u)
    const r = f.radius_m ?? 0
    return Array.from({ length: n }, (_, i) => {
      const t = (2 * Math.PI * i) / n
      return c.clone().addScaledVector(u, r * Math.cos(t)).addScaledVector(v, r * Math.sin(t))
    })
  }
  return f.vertices_m.map((p) => new THREE.Vector3(...(p as Vec3)))
}

function Filament({ f, current, scale, marker, label }: { f: PassiveFilament; current: number; scale: number; marker: number; label: string | null }) {
  const pts = useMemo(() => filamentPoints(f), [f])
  const rel = scale > 0 ? Math.abs(current) / scale : 0
  const color = rel < 1e-6 ? IDLE : current > 0 ? INDUCED_POS : INDUCED_NEG
  const cones = useMemo(() => {
    if (rel < 1e-6 || pts.length < 2) return []
    const n = Math.min(8, pts.length)
    return Array.from({ length: n }, (_, k) => {
      const i = Math.floor((k * pts.length) / n)
      const a = pts[i]!
      const b = pts[(i + 1) % pts.length]!
      const dir = b.clone().sub(a).normalize().multiplyScalar(current > 0 ? 1 : -1)
      return { p: a.clone().lerp(b, 0.5), q: new THREE.Quaternion().setFromUnitVectors(Y, dir) }
    })
  }, [pts, current, rel])
  const size = marker * (0.5 + 0.8 * Math.min(1, rel))
  return (
    <group>
      <Line points={[...pts, pts[0]!]} color={color} lineWidth={1.5 + 3 * Math.min(1, rel)} depthTest={false} />
      {cones.map((c, i) => (
        <mesh key={i} position={c.p} quaternion={c.q} renderOrder={9}>
          <coneGeometry args={[size * 0.55, size * 1.6, 10]} />
          <meshBasicMaterial color={color} depthTest={false} toneMapped={false} />
        </mesh>
      ))}
      {label && pts[0] && (
        <Html position={pts[0]} zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <span className="select-none whitespace-nowrap font-mono text-[10px]" style={{ color }}>{label}</span>
        </Html>
      )}
    </group>
  )
}

export function CircuitLayer({ data, marker }: { data: CircuitsData; marker: number }) {
  const r = data.data
  const s = r?.series
  const k = data.k
  if (!r || !s || k < 0) return null
  const scale = Math.max(0, ...s.current_A.map((c) => Math.max(...c.map(Math.abs))))
  return (
    <group>
      {r.elements.map((e, i) => {
        const fils = s.filaments[i]!
        const f = fils.length > 1 ? fils[k] : fils[0]
        if (!f) return null
        const cur = s.current_A[i]![k]!
        // Bands: their own scale (current density), labels only for circuits.
        return <Filament key={e.id} f={f} current={cur} scale={scale} marker={marker} label={e.kind === 'circuit' ? `${e.name}: ${formatSI(cur, 'A', 3)}` : null} />
      })}
    </group>
  )
}
