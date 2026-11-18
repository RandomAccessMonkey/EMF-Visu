// Coaxial-cable TEM model in the viewport: a 2D cross-section (true scale) at the selected z,
// and a 3D cut-away cable (radial dimensions exaggerated, stated on screen). Every V, I, E, H and
// S shown here is the engine's closed-form value at the current simulation time; this file only
// places and colours them. Arrows reuse the shared instanced ArrowField with linear lengths
// (amplitude ∝ |field| / its maximum over the playback range), so the wave's amplitude is the
// arrow length.
import { Html, Line, OrbitControls, OrthographicCamera, PerspectiveCamera } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useMemo } from 'react'
import * as THREE from 'three'
import type { CoaxSnapshot, CoaxSpec, Vec3 } from '@/api/types'
import { useT } from '@/i18n'
import { formatSI } from '@/lib/format'
import type { CoaxData } from '@/sim/coax'
import { useViewStore } from '@/state/viewStore'
import { ArrowField } from './ArrowField'
import { MAGNETIC_LINE_COLOR } from './magneticColors'

export const COAX_E_COLOR = '#fdba74' // E field lines (radial)
export const COAX_H_COLOR = MAGNETIC_LINE_COLOR // H field lines (azimuthal)
export const COAX_S_COLOR = '#facc15' // Poynting vector
const COPPER = '#c2793a'
const SHIELD = '#8b95a7'
const DIELECTRIC = '#1e3a5f'
const POS = new THREE.Color('#f87171')
const NEG = new THREE.Color('#60a5fa')
const ZERO = new THREE.Color('#243047')
const UP = new THREE.Vector3(0, 1, 0)

/** Diverging colour of a signed value relative to its scale (V(z) along the cable). */
export function divergingColor(v: number, scale: number, out = new THREE.Color()): THREE.Color {
  const t = scale > 0 ? Math.max(-1, Math.min(1, v / scale)) : 0
  return out.copy(ZERO).lerp(t >= 0 ? POS : NEG, Math.abs(t))
}

/** Radial display magnification of the 3D cable: the outer radius is drawn as 12 % of L. */
export function radialScale(g: CoaxSpec['geometry']): number {
  return Math.max(1, (0.12 * g.length_m) / g.shield_outer_radius_m)
}

/** Angle (physical φ) the 3D camera looks from; the cut-away wedge is centred on it. */
const CUT_PHI = Math.atan2(-1.45, -0.8)
const CUT_HALF = (55 * Math.PI) / 180

// ------------------------------------------------------------------------------- 2D view

function Cross2D({ spec, data }: { spec: CoaxSpec; data: CoaxSnapshot | undefined }) {
  const { t } = useT()
  const v = useViewStore()
  const size = useThree((s) => s.size)
  const g = spec.geometry
  const a = g.inner_radius_m
  const b = g.shield_inner_radius_m
  const c = g.shield_outer_radius_m
  const zoom = (0.8 * Math.min(size.width, size.height)) / (2 * c * 1.35)
  const m = c * 0.035 // marker size
  const cs = data?.cross_section
  const lnba = data?.params.ln_b_over_a ?? Math.log(b / a)
  const alphaE = data && data.scale_V > 0 ? Math.min(1, Math.abs(data.V) / data.scale_V) : 0
  const alphaH = data && data.scale_I > 0 ? Math.min(1, Math.abs(data.I) / data.scale_I) : 0
  // Sample rings (log-spaced radii, inner to outer): E arrows on rings 0 and 2, H arrows on rings
  // 1 and 3, the axial S markers on every other point of ring 3, so no glyphs overlap.
  const samples = useMemo(() => {
    if (!cs) return []
    const radii = [...new Set(cs.points_m.map(([x, y]) => Math.hypot(x, y).toPrecision(9)))].map(Number).sort((x, y) => x - y)
    const count = new Map<number, number>()
    return cs.points_m.map(([x, y], i) => {
      const r = Math.hypot(x, y)
      const ring = radii.findIndex((q) => Math.abs(q - r) <= 1e-6 * r)
      const k = count.get(ring) ?? 0
      count.set(ring, k + 1)
      const role = ring % 2 === 0 ? 'E' : ring === radii.length - 1 && k % 2 === 0 ? 'S' : 'H'
      return { i, x, y, r, role }
    })
  }, [cs])
  const arrows = useMemo(() => {
    if (!cs || !data || samples.length === 0) return null
    const pack = (role: 'E' | 'H') => {
      const sel = samples.filter((p) => p.role === role)
      const pts = new Float32Array(3 * sel.length)
      const vec = new Float32Array(3 * sel.length)
      const mag = new Float32Array(sel.length)
      sel.forEach((p, n) => {
        const [vx, vy] = (role === 'E' ? cs.E : cs.H)[p.i]!
        pts.set([p.x, p.y, c * 0.002], 3 * n)
        vec.set([vx, vy, 0], 3 * n)
        mag[n] = Math.hypot(vx, vy)
      })
      return { pts, vec, mag, r1: Math.min(...sel.map((p) => p.r)) }
    }
    const e = pack('E')
    const h = pack('H')
    // Fixed scales: the largest |E| and |H| over the playback range, at each set's innermost ring.
    return {
      e,
      h,
      eScale: { min: 0, max: data.scale_V / (e.r1 * lnba) },
      hScale: { min: 0, max: data.scale_I / (2 * Math.PI * h.r1) },
      cell: ((b - a) / 4) * 1.35,
    }
  }, [cs, data, samples, b, a, c, lnba])
  const sMarks = useMemo(() => {
    if (!cs || !data || !v.coaxShowPoynting) return []
    // The Poynting vector is axial: ⊙ (out of the screen, +z) or ⊗ (into it, −z), size ∝ |S|.
    const sel = samples.filter((p) => p.role === 'S').map((p) => ({ ...p, s: cs.S_z[p.i]! }))
    const sRef = (data.scale_V * data.scale_I) / (2 * Math.PI * (sel[0]?.r ?? 1) ** 2 * lnba)
    return sel.map((p) => ({ ...p, k: sRef > 0 ? Math.min(1, Math.abs(p.s) / sRef) : 0 }))
  }, [cs, data, samples, v.coaxShowPoynting, lnba])
  const labelAt = (r: number, ang: number): Vec3 => [r * Math.cos(ang), r * Math.sin(ang), 0]
  const dims: [string, number, number][] = [
    [`a = ${formatSI(a, 'm', 3)}`, a, (205 * Math.PI) / 180],
    [`b = ${formatSI(b, 'm', 3)}`, b, (235 * Math.PI) / 180],
    [`c = ${formatSI(c, 'm', 3)}`, c, (265 * Math.PI) / 180],
  ]
  return (
    <>
      <OrthographicCamera key={`coax2d-${v.cameraResetToken}`} makeDefault position={[0, 0, 10 * c]} up={[0, 1, 0]} zoom={zoom} near={c * 1e-3} far={c * 100} />
      <OrbitControls key={`coax2dc-${v.cameraResetToken}`} makeDefault target={[0, 0, 0]} enableRotate={false} zoomToCursor mouseButtons={{ MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }} />
      {/* Probe plane (the cross-section at z). */}
      <mesh
        position={[0, 0, -c * 0.02]}
        onClick={(e) => {
          if (v.tool !== 'probe') return
          e.stopPropagation()
          useViewStore.getState().set({ probePoint: [e.point.x, e.point.y, 0] })
        }}
      >
        <planeGeometry args={[4 * c, 4 * c]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <ringGeometry args={[b, c, 160]} />
        <meshBasicMaterial color={SHIELD} />
      </mesh>
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <ringGeometry args={[a, b, 160]} />
        <meshBasicMaterial color={DIELECTRIC} transparent opacity={0.55} />
      </mesh>
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <circleGeometry args={[a, 96]} />
        <meshBasicMaterial color={COPPER} />
      </mesh>
      {dims.map(([text, r, ang]) => (
        <group key={text}>
          <Line points={[[0, 0, c * 0.003], labelAt(r, ang)]} color="#e2e8f0" lineWidth={1.2} />
          <Line points={[labelAt(r, ang), labelAt(c * 1.12, ang)]} color="#94a3b8" lineWidth={0.8} dashed dashSize={c * 0.03} gapSize={c * 0.02} />
          <Html position={labelAt(c * 1.2, ang)} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
            <span className="select-none whitespace-nowrap rounded bg-bg/70 px-1 font-mono text-[10px] text-text">{text}</span>
          </Html>
        </group>
      ))}
      <Html position={[0, c * 1.32, 0]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <span className="select-none whitespace-nowrap font-mono text-[10px] text-muted">{t('coax.view.section', { z: formatSI(data?.z_m ?? 0, 'm', 3) })}</span>
      </Html>
      {data && cs && v.showFieldLines && alphaE > 1e-3 && (
        <group>
          {cs.e_line_angles_rad.map((ang) => {
            const d = new THREE.Vector3(Math.cos(ang), Math.sin(ang), 0)
            const rm = Math.sqrt(a * b)
            return (
              <group key={ang}>
                <Line points={[d.clone().multiplyScalar(a).toArray() as Vec3, d.clone().multiplyScalar(b).toArray() as Vec3]} color={COAX_E_COLOR} lineWidth={1.4} transparent opacity={alphaE} />
                <mesh position={d.clone().multiplyScalar(rm)} quaternion={new THREE.Quaternion().setFromUnitVectors(UP, d.clone().multiplyScalar(cs.e_sign))}>
                  <coneGeometry args={[m * 0.45, m * 1.3, 10]} />
                  <meshBasicMaterial color={COAX_E_COLOR} transparent opacity={alphaE} toneMapped={false} />
                </mesh>
              </group>
            )
          })}
        </group>
      )}
      {data && cs && v.showBLines && alphaH > 1e-3 && (
        <group>
          {cs.h_line_radii_m.map((r, k) => {
            const pts = Array.from({ length: 129 }, (_, i) => [r * Math.cos((2 * Math.PI * i) / 128), r * Math.sin((2 * Math.PI * i) / 128), c * 0.001] as Vec3)
            const ang = (k * Math.PI) / 4 + Math.PI / 8
            const tan = new THREE.Vector3(-Math.sin(ang), Math.cos(ang), 0).multiplyScalar(cs.h_sign)
            return (
              <group key={r}>
                <Line points={pts} color={COAX_H_COLOR} lineWidth={1.2} transparent opacity={alphaH} />
                <mesh position={[r * Math.cos(ang), r * Math.sin(ang), 0]} quaternion={new THREE.Quaternion().setFromUnitVectors(UP, tan)}>
                  <coneGeometry args={[m * 0.4, m * 1.2, 10]} />
                  <meshBasicMaterial color={COAX_H_COLOR} transparent opacity={alphaH} toneMapped={false} />
                </mesh>
              </group>
            )
          })}
        </group>
      )}
      {arrows && v.showArrows && <ArrowField points={arrows.e.pts} vectors={arrows.e.vec} magnitudes={arrows.e.mag} scale={arrows.eScale} cell={arrows.cell} lengthMode="linear" sizeFactor={v.arrowScale} solidColor={COAX_E_COLOR} />}
      {arrows && v.showBArrows && <ArrowField points={arrows.h.pts} vectors={arrows.h.vec} magnitudes={arrows.h.mag} scale={arrows.hScale} cell={arrows.cell} lengthMode="linear" sizeFactor={v.arrowScale} solidColor={COAX_H_COLOR} />}
      {sMarks.map((p, i) =>
        p.k > 1e-3 ? (
          <group key={i} position={[p.x * 1.0, p.y * 1.0, c * 0.004]}>
            <Line points={Array.from({ length: 33 }, (_, j) => [Math.cos((j * Math.PI) / 16) * m * (0.4 + 0.8 * p.k), Math.sin((j * Math.PI) / 16) * m * (0.4 + 0.8 * p.k), 0] as Vec3)} color={COAX_S_COLOR} lineWidth={1.3} />
            {p.s > 0 ? (
              <mesh>
                <circleGeometry args={[m * 0.18 * (0.6 + p.k), 16]} />
                <meshBasicMaterial color={COAX_S_COLOR} toneMapped={false} />
              </mesh>
            ) : (
              <Line points={[[-1, -1, 0], [1, 1, 0], [0, 0, 0], [-1, 1, 0], [1, -1, 0]].map(([x, y]) => [x! * m * 0.3 * (0.4 + 0.8 * p.k), y! * m * 0.3 * (0.4 + 0.8 * p.k), 0] as Vec3)} color={COAX_S_COLOR} lineWidth={1.3} />
            )}
          </group>
        ) : null,
      )}
      {v.probePoint && (
        <mesh position={[v.probePoint[0], v.probePoint[1], c * 0.01]}>
          <circleGeometry args={[m * 0.35, 16]} />
          <meshBasicMaterial color="#ffffff" toneMapped={false} />
        </mesh>
      )}
    </>
  )
}

// ------------------------------------------------------------------------------- 3D view

/** Physical (x, y, z) → display: the cable axis along world x (centred), radial × k. The map
 *  (x, y, z) → (z − L/2, k y, −k x) is a proper rotation (right-handed axes are kept). */
function toDisplay(x: number, y: number, z: number, k: number, L: number): [number, number, number] {
  return [z - L / 2, k * y, -k * x]
}

/** A cylindrical surface r = const, φ ∈ [φ0, φ1], z ∈ [0, L] (display coordinates), with
 *  optional per-z vertex colours. */
function cylinderPatch(r: number, phi0: number, phi1: number, zs: number[], k: number, L: number, colors?: THREE.Color[]) {
  const nPhi = 48
  const pos: number[] = []
  const col: number[] = []
  const idx: number[] = []
  zs.forEach((z, j) => {
    for (let i = 0; i <= nPhi; i++) {
      const ph = phi0 + ((phi1 - phi0) * i) / nPhi
      pos.push(...toDisplay(r * Math.cos(ph), r * Math.sin(ph), z, k, L))
      if (colors) col.push(colors[j]!.r, colors[j]!.g, colors[j]!.b)
    }
  })
  for (let j = 0; j < zs.length - 1; j++) {
    for (let i = 0; i < nPhi; i++) {
      const p = j * (nPhi + 1) + i
      const q = p + nPhi + 1
      idx.push(p, q, p + 1, p + 1, q, q + 1)
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  if (colors) geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3))
  geo.setIndex(idx)
  geo.computeVertexNormals()
  return geo
}

/** A radial strip φ = const, r ∈ [r0, r1], z ∈ [0, L] (the faces of the cut-away). */
function radialStrip(r0: number, r1: number, phi: number, zs: number[], k: number, L: number, colors?: THREE.Color[]) {
  const pos: number[] = []
  const col: number[] = []
  const idx: number[] = []
  zs.forEach((z, j) => {
    for (const r of [r0, r1]) {
      pos.push(...toDisplay(r * Math.cos(phi), r * Math.sin(phi), z, k, L))
      if (colors) col.push(colors[j]!.r, colors[j]!.g, colors[j]!.b)
    }
  })
  for (let j = 0; j < zs.length - 1; j++) {
    const p = 2 * j
    idx.push(p, p + 2, p + 1, p + 1, p + 2, p + 3)
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  if (colors) geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3))
  geo.setIndex(idx)
  return geo
}

function Cable3D({ spec, data, z }: { spec: CoaxSpec; data: CoaxSnapshot | undefined; z: number }) {
  const { t } = useT()
  const v = useViewStore()
  const g = spec.geometry
  const L = g.length_m
  const a = g.inner_radius_m
  const b = g.shield_inner_radius_m
  const c = g.shield_outer_radius_m
  const k = radialScale(g)
  const p0 = CUT_PHI + CUT_HALF
  const p1 = CUT_PHI + 2 * Math.PI - CUT_HALF
  const line = data?.line
  // Static geometry (rebuilt only when the cable changes).
  const shell = useMemo(() => ({
    inner: cylinderPatch(a, 0, 2 * Math.PI, [0, L], k, L),
    shield: cylinderPatch(c, p0, p1, [0, L], k, L),
    shieldIn: cylinderPatch(b, p0, p1, [0, L], k, L),
    cut0: radialStrip(b, c, p0, [0, L], k, L),
    cut1: radialStrip(b, c, p1, [0, L], k, L),
  }), [a, b, c, L, k, p0, p1])
  // The dielectric's cut faces and its back wall coloured by V(z, t) (diverging scale).
  const wave = useMemo(() => {
    if (!line || !data) return null
    const cols = line.V.map((x) => divergingColor(x, data.scale_V))
    return {
      wall: cylinderPatch(b * 0.995, p0, p1, line.z_m, k, L, cols),
      f0: radialStrip(a, b, p0, line.z_m, k, L, cols),
      f1: radialStrip(a, b, p1, line.z_m, k, L, cols),
    }
  }, [line, data, a, b, k, L, p0, p1])
  const arrows = useMemo(() => {
    const st = data?.stations
    if (!st || !data) return null
    const n = st.z_m.length
    const rm = st.r_m
    const phE = CUT_PHI - 0.45
    const phH = CUT_PHI + 0.45
    const pe = new Float32Array(3 * n)
    const ph = new Float32Array(3 * n)
    const ps = new Float32Array(3 * n)
    const ve = new Float32Array(3 * n)
    const vh = new Float32Array(3 * n)
    const vs = new Float32Array(3 * n)
    const me = new Float32Array(n)
    const mh = new Float32Array(n)
    const ms = new Float32Array(n)
    // Unit vectors r̂(φ) and φ̂(φ) mapped to display axes; components from the engine.
    const rh = (p: number) => toDisplay(Math.cos(p), Math.sin(p), 0, 1, 0)
    const fh = (p: number) => toDisplay(-Math.sin(p), Math.cos(p), 0, 1, 0)
    st.z_m.forEach((zz, i) => {
      pe.set(toDisplay(rm * Math.cos(phE), rm * Math.sin(phE), zz, k, L), 3 * i)
      ph.set(toDisplay(rm * Math.cos(phH), rm * Math.sin(phH), zz, k, L), 3 * i)
      ps.set(toDisplay(rm * Math.cos(CUT_PHI), rm * Math.sin(CUT_PHI), zz, k, L), 3 * i)
      const er = st.E_r[i]!
      const hp = st.H_phi[i]!
      const sz = st.S_z[i]!
      const [rx, ry, rz] = rh(phE)
      ve.set([rx * er, ry * er, rz * er], 3 * i)
      const [fx, fy, fz] = fh(phH)
      vh.set([fx * hp, fy * hp, fz * hp], 3 * i)
      vs.set([sz, 0, 0], 3 * i)
      me[i] = Math.abs(er)
      mh[i] = Math.abs(hp)
      ms[i] = Math.abs(sz)
    })
    const lnba = data.params.ln_b_over_a
    return {
      pe, ph, ps, ve, vh, vs, me, mh, ms,
      eScale: { min: 0, max: data.scale_V / (rm * lnba) },
      hScale: { min: 0, max: data.scale_I / (2 * Math.PI * rm) },
      sScale: { min: 0, max: (data.scale_V * data.scale_I) / (2 * Math.PI * rm * rm * lnba) },
      cellR: (b - a) * k * 0.95,
      cellZ: (L / (n - 1)) * 1.9,
    }
  }, [data, k, L, a, b])
  const cut = data?.cross_section
  const zLabel = (zz: number, text: string) => (
    <Html position={toDisplay(c * 2.3, 0, zz, k, L)} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
      <span className="select-none whitespace-nowrap rounded bg-bg/70 px-1 font-mono text-[10px] text-text">{text}</span>
    </Html>
  )
  const diag = L * 1.2
  return (
    <>
      <PerspectiveCamera key={`coax3d-${v.cameraResetToken}`} makeDefault position={[-0.1 * L, -1.45 * L, 0.8 * L]} up={[0, 0, 1]} fov={36} near={L * 1e-3} far={diag * 20} />
      <OrbitControls key={`coax3dc-${v.cameraResetToken}`} makeDefault target={[0, 0, 0]} enableDamping dampingFactor={0.12} />
      <mesh geometry={shell.inner}>
        <meshStandardMaterial color={COPPER} metalness={0.6} roughness={0.35} />
      </mesh>
      <mesh geometry={shell.shield}>
        <meshStandardMaterial color={SHIELD} metalness={0.5} roughness={0.5} transparent opacity={0.28} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh geometry={shell.shieldIn}>
        <meshStandardMaterial color={SHIELD} metalness={0.5} roughness={0.5} transparent opacity={0.18} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {[shell.cut0, shell.cut1].map((geo, i) => (
        <mesh key={i} geometry={geo}>
          <meshStandardMaterial color={SHIELD} side={THREE.DoubleSide} />
        </mesh>
      ))}
      {wave && (
        <>
          <mesh geometry={wave.wall}>
            <meshBasicMaterial vertexColors side={THREE.DoubleSide} transparent opacity={0.6} depthWrite={false} />
          </mesh>
          {[wave.f0, wave.f1].map((geo, i) => (
            <mesh key={i} geometry={geo}>
              <meshBasicMaterial vertexColors side={THREE.DoubleSide} transparent opacity={0.85} />
            </mesh>
          ))}
        </>
      )}
      {/* The inspected cross-section (the 2D view) with its E rays and H circles. */}
      <mesh position={toDisplay(0, 0, z, k, L)} rotation={[0, Math.PI / 2, 0]}>
        <ringGeometry args={[a * k, b * k, 96]} />
        <meshBasicMaterial color="#e2e8f0" transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {cut && data && v.showFieldLines && Math.abs(data.V) > 1e-3 * data.scale_V && cut.e_line_angles_rad.map((ang) => (
        <Line key={ang} points={[toDisplay(a * Math.cos(ang), a * Math.sin(ang), z, k, L), toDisplay(b * Math.cos(ang), b * Math.sin(ang), z, k, L)]} color={COAX_E_COLOR} lineWidth={1.2} transparent opacity={Math.min(1, Math.abs(data.V) / data.scale_V)} />
      ))}
      {cut && data && v.showBLines && Math.abs(data.I) > 1e-3 * data.scale_I && cut.h_line_radii_m.filter((_, i) => i % 2 === 1).map((r) => (
        <Line key={r} points={Array.from({ length: 97 }, (_, i) => toDisplay(r * Math.cos((2 * Math.PI * i) / 96), r * Math.sin((2 * Math.PI * i) / 96), z, k, L))} color={COAX_H_COLOR} lineWidth={1.2} transparent opacity={Math.min(1, Math.abs(data.I) / data.scale_I)} />
      ))}
      {arrows && v.showArrows && <ArrowField points={arrows.pe} vectors={arrows.ve} magnitudes={arrows.me} scale={arrows.eScale} cell={arrows.cellR} lengthMode="linear" sizeFactor={v.arrowScale} solidColor={COAX_E_COLOR} />}
      {arrows && v.showBArrows && <ArrowField points={arrows.ph} vectors={arrows.vh} magnitudes={arrows.mh} scale={arrows.hScale} cell={arrows.cellR} lengthMode="linear" sizeFactor={v.arrowScale} solidColor={COAX_H_COLOR} />}
      {arrows && v.coaxShowPoynting && <ArrowField points={arrows.ps} vectors={arrows.vs} magnitudes={arrows.ms} scale={arrows.sScale} cell={arrows.cellZ} lengthMode="linear" sizeFactor={v.arrowScale} solidColor={COAX_S_COLOR} />}
      {zLabel(0, t('coax.view.source', { term: t(`coax.term.${spec.source ?? 'matched'}`) }))}
      {zLabel(L, t('coax.view.load', { term: t(`coax.term.${spec.load ?? 'matched'}`) }))}
      {zLabel(z, `z = ${formatSI(z, 'm', 3)}`)}
      <Html position={toDisplay(-c * 2.4, 0, L / 2, k, L)} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <span className="select-none whitespace-nowrap font-mono text-[10px] text-muted">{t('coax.view.radial', { k: k.toFixed(0) })} · +z →</span>
      </Html>
    </>
  )
}

export function CoaxLayer({ coax }: { coax: CoaxData }) {
  const mode = useViewStore((s) => s.mode)
  // Geometry is drawn only for a valid specification.
  if (!coax.spec || coax.issues.length > 0) return null
  return mode === '2d' ? <Cross2D spec={coax.spec} data={coax.data} /> : <Cable3D spec={coax.spec} data={coax.data} z={coax.z} />
}
