// Renderers for the engine's derived products. They only draw vertices the engine computed:
// no integration, interpolation or level finding happens here.
import { Line } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { SimulationResult } from '@/api/container'
import type { FieldLineInfo } from '@/api/types'

const NUMERICAL_ENDS = new Set(['max_length', 'integration_failure'])
// A magnetic field line has no physical end: only a detected closure or truncation by the
// region of interest is a regular outcome; every other end is numerical.
const REGULAR_B_ENDS = new Set(['closed_loop', 'domain_boundary'])
export const isNumericalEnd = (l: FieldLineInfo) =>
  NUMERICAL_ENDS.has(l.start_reason) || NUMERICAL_ENDS.has(l.end_reason)
export const isNumericalBEnd = (l: FieldLineInfo) =>
  !REGULAR_B_ENDS.has(l.start_reason) || !REGULAR_B_ENDS.has(l.end_reason)

export const FIELD_LINE_COLOR = '#e8f7ff'
export const NUMERICAL_LINE_COLOR = '#fbbf24'
export const LEVEL_COLORS = { positive: '#ffb38a', negative: '#8cc6ff', zero: '#ffffff' } as const

function segmentPairs(points: Float32Array, lines: FieldLineInfo[]): number[] {
  const out: number[] = []
  for (const l of lines) {
    for (let i = l.start; i < l.start + l.count - 1; i++) {
      out.push(points[3 * i]!, points[3 * i + 1]!, points[3 * i + 2]!, points[3 * i + 3]!, points[3 * i + 4]!, points[3 * i + 5]!)
    }
  }
  return out
}

/** Point at half the arc length of a polyline, and the unit tangent there. */
function midpoint(points: Float32Array, l: FieldLineInfo): { p: THREE.Vector3; t: THREE.Vector3 } | null {
  const v = (i: number) => new THREE.Vector3(points[3 * i]!, points[3 * i + 1]!, points[3 * i + 2]!)
  let total = 0
  for (let i = l.start; i < l.start + l.count - 1; i++) total += v(i).distanceTo(v(i + 1))
  if (!(total > 0)) return null
  let run = 0
  for (let i = l.start; i < l.start + l.count - 1; i++) {
    const a = v(i)
    const b = v(i + 1)
    const d = a.distanceTo(b)
    if (run + d >= total / 2 && d > 0) {
      return { p: a.lerp(b, (total / 2 - run) / d), t: b.sub(v(i)).normalize() }
    }
    run += d
  }
  return null
}

const UP = new THREE.Vector3(0, 1, 0)

/** Static direction markers: one arrowhead per line, pointing along +E. They do not move, so
 *  nothing suggests that charge or energy travels along a field line. */
function DirectionMarkers({ points, lines, size, color }: { points: Float32Array; lines: FieldLineInfo[]; size: number; color: string }) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const marks = useMemo(() => lines.map((l) => midpoint(points, l)).filter((m) => m !== null), [points, lines])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const s = new THREE.Vector3(size, size, size)
    marks.forEach((mk, i) => mesh.setMatrixAt(i, m.compose(mk.p, q.setFromUnitVectors(UP, mk.t), s)))
    mesh.instanceMatrix.needsUpdate = true
    invalidate()
  }, [marks, size, invalidate])
  if (marks.length === 0) return null
  return (
    <instancedMesh key={marks.length} ref={ref} args={[undefined, undefined, marks.length]} frustumCulled={false} renderOrder={3}>
      <coneGeometry args={[0.5, 1.6, 10]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </instancedMesh>
  )
}

export function FieldLines({ result, level, markerSize, color = FIELD_LINE_COLOR, numericalColor = NUMERICAL_LINE_COLOR }: { result: SimulationResult; level: number; markerSize: number; color?: string; numericalColor?: string }) {
  const set = result.header.field_lines
  const points = set ? result.arrays[set.array]?.data : undefined
  const data = useMemo(() => {
    if (!set || !points) return null
    const numerical = set.field === 'B' ? isNumericalBEnd : isNumericalEnd
    const shown = set.lines.filter((l) => l.level === Math.min(level, set.levels - 1))
    const good = shown.filter((l) => !numerical(l))
    const bad = shown.filter(numerical)
    return { good, goodPairs: segmentPairs(points, good), badPairs: segmentPairs(points, bad) }
  }, [set, points, level])
  if (!data || !points) return null
  return (
    <>
      {data.goodPairs.length > 0 && (
        <Line points={data.goodPairs} segments color={color} lineWidth={1.4} transparent opacity={0.92} renderOrder={2} />
      )}
      {/* Lines whose end is a numerical outcome are drawn differently, never as normal endings. */}
      {data.badPairs.length > 0 && (
        <Line points={data.badPairs} segments color={numericalColor} lineWidth={1.4} dashed dashSize={0.04} gapSize={0.03} renderOrder={2} />
      )}
      <DirectionMarkers points={points} lines={data.good} size={markerSize} color={color} />
    </>
  )
}

const levelColor = (v: number) => (v > 0 ? LEVEL_COLORS.positive : v < 0 ? LEVEL_COLORS.negative : LEVEL_COLORS.zero)

export function Contours({ result }: { result: SimulationResult }) {
  const set = result.header.equipotentials
  const segments = set ? result.arrays[set.array]?.data : undefined
  const data = useMemo(() => {
    if (!set || !segments || segments.length === 0) return null
    const colors: [number, number, number][] = []
    const c = new THREE.Color()
    for (const lv of set.levels) {
      c.set(levelColor(lv.value_V))
      for (let i = 0; i < lv.count * 2; i++) colors.push([c.r, c.g, c.b])
    }
    return { points: Array.from(segments), colors }
  }, [set, segments])
  if (!data) return null
  return <Line points={data.points} segments vertexColors={data.colors} lineWidth={1} transparent opacity={0.75} renderOrder={1} />
}

export function Isosurfaces({ result }: { result: SimulationResult }) {
  const set = result.header.isosurfaces
  const triangles = set ? result.arrays[set.array]?.data : undefined
  const normals = set ? result.arrays[set.normals_array]?.data : undefined
  const invalidate = useThree((s) => s.invalidate)
  const geometry = useMemo(() => {
    if (!set || !triangles || !normals || triangles.length === 0) return null
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(triangles, 3))
    g.setAttribute('normal', new THREE.BufferAttribute(normals, 3))
    const colors = new Float32Array(triangles.length)
    const c = new THREE.Color()
    for (const lv of set.levels) {
      c.set(levelColor(lv.value_V))
      for (let i = lv.start * 9; i < (lv.start + lv.count) * 9; i += 3) {
        colors[i] = c.r
        colors[i + 1] = c.g
        colors[i + 2] = c.b
      }
    }
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return g
  }, [set, triangles, normals])
  useEffect(() => {
    invalidate()
    return () => geometry?.dispose()
  }, [geometry, invalidate])
  if (!geometry) return null
  return (
    <mesh geometry={geometry} renderOrder={0}>
      <meshStandardMaterial vertexColors transparent opacity={0.26} depthWrite={false} side={THREE.DoubleSide} roughness={0.5} />
    </mesh>
  )
}
