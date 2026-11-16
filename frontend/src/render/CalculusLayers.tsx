// Divergence, curl and source layers. Everything drawn here is read from the engine's result:
// the pointwise divergence/curl arrays and the table of distributional point sources.
import { Billboard, Html } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { SimulationResult } from '@/api/container'
import type { LatticeSampling, PlaneGridSampling } from '@/api/types'
import { useT } from '@/i18n'
import { formatSI } from '@/lib/format'
import { PLANE_BASIS, subsampleLattice, subsamplePlane, type VectorSamples } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { ArrowField } from './ArrowField'
import { partitionVectors, sourceMarkers } from './calculus'
import { magnitudes, magnitudeScale, sampling, scalarColoring, scalarSamples, type ScalarKind } from './fieldImages'

/** Glyph colour for "this vector is exactly the zero vector". */
export const ZERO_VECTOR_COLOR = '#7dd3c0'
export const SOURCE_COLORS = { positive: '#ff7a59', negative: '#4aa8ff' } as const

function curlSamples(result: SimulationResult, id: 'arrows' | 'vol', field: 'E' | 'D', density: number): VectorSamples | null {
  const arr = result.arrays[`${id}.curl_${field}`]
  if (!arr) return null
  if (id === 'arrows') {
    const g = sampling<PlaneGridSampling>(result, id)
    return g ? subsamplePlane(g, arr.data, density) : null
  }
  const l = sampling<LatticeSampling>(result, id)
  return l ? subsampleLattice(l, arr.data, density) : null
}

const pick = (src: Float32Array, idx: number[]) => {
  const out = new Float32Array(idx.length * 3)
  idx.forEach((i, k) => out.set(src.subarray(3 * i, 3 * i + 3), 3 * k))
  return out
}

/** Zero vectors are drawn as small rings (a vector of length zero has no direction to draw);
 *  nonzero vectors, if any, as arrows. Nothing rotates or moves. */
export function CurlGlyphs({ result, id, field }: { result: SimulationResult; id: 'arrows' | 'vol'; field: 'E' | 'D' }) {
  const density = useViewStore((s) => (id === 'arrows' ? s.arrowDensity : s.latticeDensity))
  const plane = useViewStore((s) => s.plane)
  const ref = useRef<THREE.InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const data = useMemo(() => {
    const s = curlSamples(result, id, field, density)
    if (!s) return null
    const parts = partitionVectors(s)
    const nzPoints = pick(s.points, parts.nonzero)
    const nzVectors = pick(s.vectors, parts.nonzero)
    return { s, parts, zeroPoints: pick(s.points, parts.zero), nzPoints, nzVectors, nzMags: magnitudes(nzVectors) }
  }, [result, id, field, density])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh || !data) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    // Rings lie in the slice plane on the slice, and face the viewer's default direction in 3D.
    const normal = new THREE.Vector3(...PLANE_BASIS[plane].normal)
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), id === 'arrows' ? normal : new THREE.Vector3(0, 0, 1))
    const size = data.s.cell * (id === 'arrows' ? 0.16 : 0.06)
    const scale = new THREE.Vector3(size, size, size)
    const p = new THREE.Vector3()
    for (let k = 0; k < data.parts.zero.length; k++) {
      p.set(data.zeroPoints[3 * k]!, data.zeroPoints[3 * k + 1]!, data.zeroPoints[3 * k + 2]!)
      mesh.setMatrixAt(k, m.compose(p, q, scale))
    }
    mesh.instanceMatrix.needsUpdate = true
    invalidate()
  }, [data, id, plane, invalidate])
  if (!data) return null
  return (
    <>
      {data.parts.zero.length > 0 && (
        <instancedMesh key={`${data.parts.zero.length}-${id}`} ref={ref} args={[undefined, undefined, data.parts.zero.length]} frustumCulled={false} renderOrder={4}>
          <torusGeometry args={[1, 0.22, 6, 20]} />
          <meshBasicMaterial color={ZERO_VECTOR_COLOR} toneMapped={false} />
        </instancedMesh>
      )}
      {data.parts.nonzero.length > 0 && (
        <ArrowField
          points={data.nzPoints}
          vectors={data.nzVectors}
          magnitudes={data.nzMags}
          scale={magnitudeScale(data.nzMags)}
          cell={data.s.cell}
          lengthMode="log"
          sizeFactor={1}
        />
      )}
    </>
  )
}

/** The selected scalar map shown at the volume samples (3D): one small cube per sample,
 *  coloured with the same scale as the slice map. */
export function VolumeScalars({ result, kind }: { result: SimulationResult; kind: ScalarKind }) {
  const density = useViewStore((s) => s.latticeDensity)
  const ref = useRef<THREE.InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const data = useMemo(() => {
    const samples = scalarSamples(result, kind, 'vol')
    const l = sampling<LatticeSampling>(result, 'vol')
    if (!samples || !l) return null
    // Reuse the lattice subsampler on (value, 0, 0) triples to pick the same samples as arrows.
    const packed = new Float32Array(samples.values.length * 3)
    samples.values.forEach((v, i) => (packed[3 * i] = v))
    const sub = subsampleLattice(l, packed, density)
    const values = new Float32Array(sub.points.length / 3)
    for (let i = 0; i < values.length; i++) values[i] = sub.vectors[3 * i]!
    return { sub, values, coloring: scalarColoring(kind, samples.values, samples.unit, 'vol') }
  }, [result, kind, density])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh || !data) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const size = data.sub.cell * 0.09
    const scale = new THREE.Vector3(size, size, size)
    const p = new THREE.Vector3()
    const c = new THREE.Color()
    const rgb = [0, 0, 0]
    let k = 0
    for (let i = 0; i < data.values.length; i++) {
      const v = data.values[i]!
      if (!Number.isFinite(v)) continue // a sample on a charge: drawn by its source marker
      p.set(data.sub.points[3 * i]!, data.sub.points[3 * i + 1]!, data.sub.points[3 * i + 2]!)
      mesh.setMatrixAt(k, m.compose(p, q, scale))
      data.coloring.colorAt(v, rgb, 0)
      mesh.setColorAt(k, c.setRGB(rgb[0]! / 255, rgb[1]! / 255, rgb[2]! / 255, THREE.SRGBColorSpace))
      k++
    }
    mesh.count = k
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    invalidate()
  }, [data, invalidate])
  if (!data) return null
  return (
    <instancedMesh key={data.values.length} ref={ref} args={[undefined, undefined, data.values.length]} frustumCulled={false}>
      <boxGeometry args={[1, 1, 1]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  )
}

export function SourceMarkers({ result, size }: { result: SimulationResult; size: number }) {
  const { t } = useT()
  const mode = useViewStore((s) => s.mode)
  const objects = useSceneStore((s) => s.scene.objects)
  const selectedId = useSceneStore((s) => s.selectedId)
  const markers = useMemo(() => {
    const names = Object.fromEntries(objects.map((o) => [o.id, o.name || o.id]))
    return sourceMarkers(result, mode, names)
  }, [result, mode, objects])
  return (
    <>
      {markers.map((m) => {
        const color = m.charge_C > 0 ? SOURCE_COLORS.positive : SOURCE_COLORS.negative
        return (
          <group key={m.id} position={m.shownAt}>
            <Billboard>
              <mesh renderOrder={6}>
                <ringGeometry args={[size * 2.1, size * (m.ghost ? 2.3 : 2.6), 40]} />
                <meshBasicMaterial color={color} transparent opacity={m.ghost ? 0.5 : 0.95} depthTest={false} toneMapped={false} />
              </mesh>
            </Billboard>
            <Html
              position={[0, 0, 0]}
              style={{ pointerEvents: 'none', transform: 'translate(14px, -50%)' }}
              zIndexRange={[20, 0]}
            >
              <div
                data-testid="source-label"
                className={`whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] leading-tight backdrop-blur ${m.ghost ? 'border-dashed border-muted/60 bg-panel/60 text-muted' : 'border-border bg-panel/85 text-text'}`}
              >
                <div>
                  <span style={{ color }}>●</span> {m.name} · {formatSI(m.charge_C, 'C')}
                  {m.ghost && <span className="text-warn/90"> · Δ{m.axis} = {m.delta > 0 ? '+' : ''}{m.delta.toPrecision(3)} m</span>}
                </div>
                {/* Full detail for the selected charge only, to keep labels from overlapping. */}
                {selectedId === m.id && (
                  <>
                    <div>{t(m.charge_C > 0 ? 'source.positive' : 'source.negative')}</div>
                    <div className="font-mono text-muted">
                      {t('source.weights', { e: formatSI(m.divEWeight, 'V·m'), d: formatSI(m.divDWeight, 'C') })}
                    </div>
                    {m.ghost && <div className="text-warn/90">{t('source.ghost')}</div>}
                  </>
                )}
              </div>
            </Html>
          </group>
        )
      })}
    </>
  )
}
