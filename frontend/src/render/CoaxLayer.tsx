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
import { CUT, fieldScales, sectionRays, stationArrows, toDisplay, type CoaxCamera } from './coaxSamples'

export const COAX_E_COLOR = '#fdba74' // E field lines (radial)
export const COAX_H_COLOR = MAGNETIC_LINE_COLOR // H field lines (azimuthal)
export const COAX_S_COLOR = '#facc15' // Poynting vector
/** Coax arrows are drawn thicker than the shared default so they read at cable scale. */
const GIRTH = 1.8
const COPPER = '#c2793a'
const SHIELD = '#8b95a7'
const DIELECTRIC = '#1d4466'
const POS = new THREE.Color('#f87171')
const NEG = new THREE.Color('#60a5fa')
const ZERO = new THREE.Color('#243047')

/** Diverging colour of a signed value relative to its scale (V(z) along the cable). */
export function divergingColor(v: number, scale: number, out = new THREE.Color()): THREE.Color {
  const t = scale > 0 ? Math.max(-1, Math.min(1, v / scale)) : 0
  return out.copy(ZERO).lerp(t >= 0 ? POS : NEG, Math.abs(t))
}

/** Radial display magnification of the 3D cable: the outer radius is drawn as 12 % of L (20 %
 *  in the side view, where only the longitudinal section is seen). Stated on screen. */
export function radialScale(g: CoaxSpec['geometry'], view: CoaxCamera = 'iso'): number {
  return Math.max(1, ((view === 'side' ? 0.2 : 0.12) * g.length_m) / g.shield_outer_radius_m)
}

// ------------------------------------------------------------------------------ glyphs

/** ⊙ (vector toward the viewer) or ⊗ (away), drawn in its local x–y plane (local +z faces the
 *  viewer); size ∝ magnitude. Used for S in cross-sections and for H in the side view. */
function AxialGlyph({ p, toward, size, color, rotation }: { p: Vec3; toward: boolean; size: number; color: string; rotation?: [number, number, number] }) {
  const ring = useMemo(() => Array.from({ length: 33 }, (_, j) => [Math.cos((j * Math.PI) / 16) * size, Math.sin((j * Math.PI) / 16) * size, 0] as Vec3), [size])
  const s = size * 0.62
  return (
    <group position={p} rotation={rotation ?? [0, 0, 0]}>
      <Line points={ring} color={color} lineWidth={1.4} />
      {toward ? (
        <mesh position={[0, 0, size * 0.01]}>
          <circleGeometry args={[size * 0.3, 16]} />
          <meshBasicMaterial color={color} toneMapped={false} side={THREE.DoubleSide} />
        </mesh>
      ) : (
        <Line points={[[-s, -s, 0], [s, s, 0], [0, 0, 0], [-s, s, 0], [s, -s, 0]]} color={color} lineWidth={1.4} />
      )}
    </group>
  )
}

/** Cross-section field samples (E, H rays and S glyphs), mapped by `place` (physical x, y →
 *  world point) and `dir` (physical in-plane vector → world vector). Shared by the 2D view and
 *  the 3D section view so both use the same rays, scales and conventions. */
function SectionFields({ data, place, dir, glyphRotation, unit, towardSign }: {
  data: CoaxSnapshot
  place: (x: number, y: number) => Vec3
  dir: (vx: number, vy: number) => Vec3
  glyphRotation?: [number, number, number]
  unit: number // world length of one metre in the cross-section plane
  towardSign: 1 | -1 // sign of S_z that points toward the viewer
}) {
  const v = useViewStore()
  const cs = data.cross_section
  const set = useMemo(() => {
    const rays = sectionRays(cs, v.coaxDensity)
    const rings = rays.rings
    if (!rings.length) return null
    const seg = cs.segment_m ?? 0
    const sc = fieldScales(data, rings[0]!)
    const build = (angles: number[], comp: 'E' | 'H') => {
      const pts: number[] = []
      const vec: number[] = []
      const mag: number[] = []
      rings.forEach((_, ri) => angles.forEach((aj) => {
        const i = rays.index(ri, aj)
        const [px, py] = cs.points_m[i]!
        const [vx, vy] = (comp === 'E' ? cs.E : cs.H)[i]!
        pts.push(...place(px, py))
        vec.push(...dir(vx, vy))
        mag.push(Math.hypot(vx, vy))
      }))
      return { points: new Float32Array(pts), vectors: new Float32Array(vec), magnitudes: new Float32Array(mag) }
    }
    // Arc between an H ray and its neighbouring E/S rays at the innermost ring (H is longest there).
    const arc = (2 * Math.PI * rings[0]!) / (3 * rays.E.length)
    const glyphs = rings.slice(1).flatMap((_, q) => rays.S.map((aj) => {
      const i = rays.index(q + 1, aj)
      const [px, py] = cs.points_m[i]!
      return { p: place(px, py), s: cs.S_z[i]! }
    }))
    return {
      E: build(rays.E, 'E'),
      H: build(rays.H, 'H'),
      glyphs,
      sc,
      // Linear lengths: at the scale maximum an E arrow fills 95 % of its radial segment and an
      // H arrow at most 1.6 arcs, so no arrow reaches a conductor or its neighbours.
      cellE: ((0.95 * seg) / 0.85) * unit,
      cellH: (Math.min(0.95 * seg, 1.6 * arc) / 0.85) * unit,
      glyph: 0.32 * seg * unit,
    }
  }, [cs, data, v.coaxDensity, place, dir, unit])
  if (!set) return null
  return (
    <>
      {v.showArrows && <ArrowField points={set.E.points} vectors={set.E.vectors} magnitudes={set.E.magnitudes} scale={{ min: 0, max: set.sc.E }} cell={set.cellE} lengthMode="linear" sizeFactor={v.arrowScale} girth={GIRTH} solidColor={COAX_E_COLOR} />}
      {v.showBArrows && <ArrowField points={set.H.points} vectors={set.H.vectors} magnitudes={set.H.magnitudes} scale={{ min: 0, max: set.sc.H }} cell={set.cellH} lengthMode="linear" sizeFactor={v.arrowScale} girth={GIRTH} solidColor={COAX_H_COLOR} />}
      {v.coaxShowPoynting && set.glyphs.map((g, i) => {
        const kk = set.sc.S > 0 ? Math.min(1, Math.abs(g.s) / set.sc.S) : 0
        return kk > 2e-3 ? <AxialGlyph key={i} p={g.p} toward={g.s * towardSign > 0} size={set.glyph * (0.35 + 0.65 * Math.sqrt(kk))} color={COAX_S_COLOR} rotation={glyphRotation} /> : null
      })}
    </>
  )
}

// ------------------------------------------------------------------------------- 2D view

function Cross2D({ spec, data }: { spec: CoaxSpec; data: CoaxSnapshot | undefined }) {
  const { t } = useT()
  const v = useViewStore()
  const size = useThree((s) => s.size)
  const g = spec.geometry
  const a = g.inner_radius_m
  const b = g.shield_inner_radius_m
  const c = g.shield_outer_radius_m
  const zoom = (0.72 * Math.min(size.width, size.height)) / (2 * c * 1.35)
  const m = c * 0.035 // marker size
  const cs = data?.cross_section
  const alphaE = data && data.scale_V > 0 ? Math.min(1, Math.abs(data.V) / data.scale_V) : 0
  const alphaH = data && data.scale_I > 0 ? Math.min(1, Math.abs(data.I) / data.scale_I) : 0
  const place = useMemo(() => (x: number, y: number): Vec3 => [x, y, c * 0.004], [c])
  const dir = useMemo(() => (vx: number, vy: number): Vec3 => [vx, vy, 0], [])
  const labelAt = (r: number, ang: number): Vec3 => [r * Math.cos(ang), r * Math.sin(ang), 0]
  const dims: [string, number, number][] = [
    [`a = ${formatSI(a, 'm', 3)}`, a, (-20 * Math.PI) / 180],
    [`b = ${formatSI(b, 'm', 3)}`, b, (-42 * Math.PI) / 180],
    [`c = ${formatSI(c, 'm', 3)}`, c, (-64 * Math.PI) / 180],
  ]
  const circle = (r: number) => Array.from({ length: 161 }, (_, i) => [r * Math.cos((2 * Math.PI * i) / 160), r * Math.sin((2 * Math.PI * i) / 160), c * 0.001] as Vec3)
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
      {/* Three distinct regions at true proportions, with their boundaries outlined. */}
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <ringGeometry args={[b, c, 160]} />
        <meshBasicMaterial color={SHIELD} />
      </mesh>
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <ringGeometry args={[a, b, 160]} />
        <meshBasicMaterial color={DIELECTRIC} />
      </mesh>
      <mesh position={[0, 0, -c * 0.01]} renderOrder={-3}>
        <circleGeometry args={[a, 96]} />
        <meshBasicMaterial color={COPPER} />
      </mesh>
      {[a, b, c].map((r) => <Line key={r} points={circle(r)} color="#e2e8f0" lineWidth={1} transparent opacity={0.55} />)}
      {dims.map(([text, r, ang]) => (
        <group key={text}>
          <Line points={[[0, 0, c * 0.003], labelAt(r, ang)]} color="#e2e8f0" lineWidth={1.2} />
          <Line points={[labelAt(r, ang), labelAt(c * 1.18, ang)]} color="#94a3b8" lineWidth={0.8} dashed dashSize={c * 0.03} gapSize={c * 0.02} />
          <Html position={labelAt(c * 1.3, ang)} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
            <span className="select-none whitespace-nowrap rounded bg-bg/80 px-1 font-mono text-[11px] text-text">{text}</span>
          </Html>
        </group>
      ))}
      <Html position={[0, -c * 1.42, 0]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <span className="select-none whitespace-nowrap font-mono text-[11px] text-muted">{t('coax.view.section', { z: formatSI(data?.z_m ?? 0, 'm', 3) })}</span>
      </Html>
      {data && cs && v.showFieldLines && alphaE > 1e-3 && cs.e_line_angles_rad.map((ang) => {
        const d = new THREE.Vector3(Math.cos(ang), Math.sin(ang), 0)
        return <Line key={ang} points={[d.clone().multiplyScalar(a).toArray() as Vec3, d.clone().multiplyScalar(b).toArray() as Vec3]} color={COAX_E_COLOR} lineWidth={1} transparent opacity={0.45 * alphaE} />
      })}
      {data && cs && v.showBLines && alphaH > 1e-3 && cs.h_line_radii_m.map((r) => (
        <Line key={r} points={circle(r)} color={COAX_H_COLOR} lineWidth={1} transparent opacity={0.45 * alphaH} />
      ))}
      {data && <SectionFields data={data} place={place} dir={dir} unit={1} towardSign={1} />}
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

/** A cylindrical surface r = const, φ ∈ [φ0, φ1], z ∈ zs (display coordinates), with optional
 *  per-z vertex colours. */
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

/** A radial strip φ = const, r ∈ [r0, r1], z ∈ zs (the faces of the cut-away). */
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

/** Camera of each 3D preset. The camera is keyed by the preset and the reset token only, so
 *  playback (new data every step) never moves it: the user's orbit/zoom is kept. */
function Camera3D({ view, L, R, zSlice }: { view: CoaxCamera; L: number; R: number; zSlice: number }) {
  const token = useViewStore((s) => s.cameraResetToken)
  const size = useThree((s) => s.size)
  // Fixed per preset (deliberately not updated while the inspected z changes).
  const cfg = useMemo(() => {
    if (view === 'side') return { target: [0, 0, 0] as Vec3, position: [0, -3 * L, 0] as Vec3 }
    if (view === 'section') {
      const tz = zSlice - L / 2
      return { target: [tz, 0, 0] as Vec3, position: [tz + 6.5 * R, -3.4 * R, 2.6 * R] as Vec3 }
    }
    // Isometric: close enough that the arrows read, far enough to show both cable ends.
    return { target: [0, 0, 0] as Vec3, position: [-0.12 * L, -1.22 * L, 0.66 * L] as Vec3 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, L, R, token])
  const key = `${view}-${token}`
  if (view === 'side') {
    const zoom = Math.min((0.9 * size.width) / (1.2 * L), (0.55 * size.height) / (2 * R))
    return (
      <group key={key}>
        <OrthographicCamera makeDefault position={cfg.position} up={[0, 0, 1]} zoom={zoom} near={L * 1e-3} far={L * 20} />
        <OrbitControls makeDefault target={cfg.target} enableDamping dampingFactor={0.12} />
      </group>
    )
  }
  return (
    <group key={key}>
      <PerspectiveCamera makeDefault position={cfg.position} up={[0, 0, 1]} fov={36} near={L * 1e-4} far={L * 30} />
      <OrbitControls makeDefault target={cfg.target} enableDamping dampingFactor={0.12} />
    </group>
  )
}

function Cable3D({ spec, data, z }: { spec: CoaxSpec; data: CoaxSnapshot | undefined; z: number }) {
  const { t } = useT()
  const v = useViewStore()
  const view = v.coaxCamera
  const g = spec.geometry
  const L = g.length_m
  const a = g.inner_radius_m
  const b = g.shield_inner_radius_m
  const c = g.shield_outer_radius_m
  const k = radialScale(g, view)
  const section = view === 'section'
  const zEnd = section ? Math.max(z, L * 1e-3) : L
  const cut = CUT[view]
  const p0 = section ? 0 : cut.phi + cut.half
  const p1 = section ? 2 * Math.PI : cut.phi + 2 * Math.PI - cut.half
  const line = data?.line
  // Static geometry (rebuilt only when the cable, the view or the section end changes).
  const shell = useMemo(() => ({
    inner: cylinderPatch(a, 0, 2 * Math.PI, [0, zEnd], k, L),
    shield: cylinderPatch(c, p0, p1, [0, zEnd], k, L),
    shieldIn: cylinderPatch(b, p0, p1, [0, zEnd], k, L),
    cuts: section ? [] : [radialStrip(b, c, p0, [0, zEnd], k, L), radialStrip(b, c, p1, [0, zEnd], k, L)],
  }), [a, b, c, L, k, p0, p1, zEnd, section])
  // The dielectric's cut faces and its back wall coloured by the line voltage V(z, t).
  const wave = useMemo(() => {
    if (!line || !data) return null
    const keep = line.z_m.map((zz, i) => ({ zz, i })).filter((q) => q.zz <= zEnd + 1e-12)
    const zs = keep.map((q) => q.zz)
    if (zs.length < 2) return null
    const cols = keep.map((q) => divergingColor(line.V[q.i]!, data.scale_V))
    return {
      wall: cylinderPatch(b * 0.995, p0, p1, zs, k, L, cols),
      faces: section ? [] : [radialStrip(a, b, p0, zs, k, L, cols), radialStrip(a, b, p1, zs, k, L, cols)],
    }
  }, [line, data, a, b, k, L, p0, p1, zEnd, section])
  const st = useMemo(() => (data && !section ? stationArrows(data, view, k, L) : null), [data, view, section, k, L])
  const cells = useMemo(() => {
    if (!st || !data) return null
    const seg = data.stations.segment_m ?? 0
    const n = data.stations.z_m.length
    const dz = L / Math.max(1, n - 1)
    const r1 = st.rings[1] ?? st.rings[0]!
    return {
      sc: fieldScales(data, st.rings[0]!),
      E: ((0.95 * seg) / 0.85) * k,
      H: (Math.min(0.95 * seg * k, 0.85 * 0.25 * r1 * k) / 0.85),
      S: ((view === 'side' ? 1.7 : 0.9) * dz) / 0.85,
      glyph: 0.3 * seg * k,
    }
  }, [st, data, k, L, view])
  // Section view: the inspected cross-section's samples placed at z in display coordinates.
  const place = useMemo(() => (x: number, y: number): Vec3 => {
    const p = toDisplay(x, y, z, k, L)
    return [p[0] + c * k * 0.02, p[1], p[2]]
  }, [z, k, L, c])
  const dir = useMemo(() => (vx: number, vy: number): Vec3 => toDisplay(vx, vy, 0, 1, 0), [])
  // End labels are anchored inward (left-aligned at z = 0, right-aligned at z = L) so they stay
  // on screen; the label of the inspected cross-section is centred on it.
  const zLabel = (zz: number, text: string, align: 'start' | 'center' | 'end' = 'center') => (
    <Html position={toDisplay(c * 1.5, 0, zz, k, L)} zIndexRange={[10, 0]} style={{ pointerEvents: 'none', transform: `translate(${align === 'start' ? '0' : align === 'end' ? '-100%' : '-50%'}, -50%)` }}>
      <span className="select-none whitespace-nowrap rounded bg-bg/80 px-1 font-mono text-[11px] text-text">{text}</span>
    </Html>
  )
  const sliceColor = data ? divergingColor(data.V, data.scale_V) : ZERO
  return (
    <>
      <Camera3D view={view} L={L} R={c * k} zSlice={z} />
      <mesh geometry={shell.inner}>
        <meshStandardMaterial color={COPPER} metalness={0.6} roughness={0.35} />
      </mesh>
      <mesh geometry={shell.shield}>
        <meshStandardMaterial color={SHIELD} metalness={0.5} roughness={0.5} transparent opacity={view === 'side' ? 0.4 : 0.28} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh geometry={shell.shieldIn}>
        <meshStandardMaterial color={SHIELD} metalness={0.5} roughness={0.5} transparent opacity={0.18} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {shell.cuts.map((geo, i) => (
        <mesh key={i} geometry={geo}>
          <meshStandardMaterial color={SHIELD} side={THREE.DoubleSide} />
        </mesh>
      ))}
      {wave && (
        <>
          <mesh geometry={wave.wall}>
            <meshBasicMaterial vertexColors side={THREE.DoubleSide} transparent opacity={0.55} depthWrite={false} />
          </mesh>
          {wave.faces.map((geo, i) => (
            <mesh key={i} geometry={geo}>
              <meshBasicMaterial vertexColors side={THREE.DoubleSide} transparent opacity={0.8} depthWrite={false} />
            </mesh>
          ))}
        </>
      )}
      {section ? (
        <>
          {/* The cable ends at the inspected cross-section: its three regions face the camera. */}
          <mesh position={toDisplay(0, 0, zEnd, k, L)} rotation={[0, Math.PI / 2, 0]}>
            <circleGeometry args={[a * k, 64]} />
            <meshStandardMaterial color={COPPER} metalness={0.4} roughness={0.5} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={toDisplay(0, 0, zEnd, k, L)} rotation={[0, Math.PI / 2, 0]}>
            <ringGeometry args={[a * k, b * k, 96]} />
            <meshBasicMaterial color={sliceColor} transparent opacity={0.4} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={toDisplay(0, 0, zEnd, k, L)} rotation={[0, Math.PI / 2, 0]}>
            <ringGeometry args={[b * k, c * k, 96]} />
            <meshStandardMaterial color={SHIELD} side={THREE.DoubleSide} />
          </mesh>
          {data && <SectionFields data={data} place={place} dir={dir} unit={k} towardSign={1} glyphRotation={[0, Math.PI / 2, 0]} />}
        </>
      ) : (
        <mesh position={toDisplay(0, 0, z, k, L)} rotation={[0, Math.PI / 2, 0]}>
          <ringGeometry args={[a * k, b * k, 96]} />
          <meshBasicMaterial color="#e2e8f0" transparent opacity={0.1} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {!section && data && v.showFieldLines && Math.abs(data.V) > 1e-3 * data.scale_V && data.cross_section.e_line_angles_rad.map((ang) => (
        <Line key={ang} points={[toDisplay(a * Math.cos(ang), a * Math.sin(ang), z, k, L), toDisplay(b * Math.cos(ang), b * Math.sin(ang), z, k, L)]} color={COAX_E_COLOR} lineWidth={1} transparent opacity={0.6 * Math.min(1, Math.abs(data.V) / data.scale_V)} />
      ))}
      {!section && data && v.showBLines && Math.abs(data.I) > 1e-3 * data.scale_I && data.cross_section.h_line_radii_m.filter((_, i) => i % 2 === 1).map((r) => (
        <Line key={r} points={Array.from({ length: 97 }, (_, i) => toDisplay(r * Math.cos((2 * Math.PI * i) / 96), r * Math.sin((2 * Math.PI * i) / 96), z, k, L))} color={COAX_H_COLOR} lineWidth={1} transparent opacity={0.6 * Math.min(1, Math.abs(data.I) / data.scale_I)} />
      ))}
      {st && cells && v.showArrows && <ArrowField points={st.E.points} vectors={st.E.vectors} magnitudes={st.E.magnitudes} scale={{ min: 0, max: cells.sc.E }} cell={cells.E} lengthMode="linear" sizeFactor={v.arrowScale} girth={GIRTH} solidColor={COAX_E_COLOR} />}
      {st && cells && v.showBArrows && <ArrowField points={st.H.points} vectors={st.H.vectors} magnitudes={st.H.magnitudes} scale={{ min: 0, max: cells.sc.H }} cell={cells.H} lengthMode="linear" sizeFactor={v.arrowScale} girth={GIRTH} solidColor={COAX_H_COLOR} />}
      {st && cells && v.showBArrows && st.Hglyphs.map((gl, i) => {
        const kk = cells.sc.H > 0 ? Math.min(1, Math.abs(gl.value) / cells.sc.H) : 0
        // Side view (camera at −y): H along +y points into the screen (⊗), along −y out (⊙).
        return kk > 2e-3 ? <AxialGlyph key={i} p={[gl.p[0], gl.p[1] - c * k * 0.05, gl.p[2]]} toward={gl.value < 0} size={cells.glyph * (0.35 + 0.65 * kk)} color={COAX_H_COLOR} rotation={[Math.PI / 2, 0, 0]} /> : null
      })}
      {st && cells && v.coaxShowPoynting && <ArrowField points={st.S.points} vectors={st.S.vectors} magnitudes={st.S.magnitudes} scale={{ min: 0, max: cells.sc.S }} cell={cells.S} lengthMode="linear" sizeFactor={v.arrowScale} girth={GIRTH} solidColor={COAX_S_COLOR} />}
      {!section && zLabel(0, t('coax.view.source', { term: t(`coax.term.${spec.source ?? 'matched'}`) }), 'start')}
      {!section && zLabel(L, t('coax.view.load', { term: t(`coax.term.${spec.load ?? 'matched'}`) }), 'end')}
      {zLabel(z, `z = ${formatSI(z, 'm', 3)}`)}
      <Html position={toDisplay(c * (section ? 1.9 : 2.2), 0, section ? zEnd : L / 2, k, L)} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
        <span className="select-none whitespace-nowrap rounded bg-bg/80 px-1 font-mono text-[11px] text-muted">
          a = {formatSI(a, 'm', 3)} · b = {formatSI(b, 'm', 3)} · c = {formatSI(c, 'm', 3)} · {t('coax.view.radial', { k: k.toFixed(0) })} · +z →
        </span>
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
