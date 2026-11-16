// Gaussian surfaces: drawn from the engine's represented mesh (the same triangles that were
// used for classification and flux integration). Colours encode the sign of E·n sampled at
// each triangle's centroid; they never change a value.
import { Billboard, Html, Line, TransformControls } from '@react-three/drei'
import { useThree, type ThreeEvent } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { SurfaceFlux, Vec3 } from '@/api/types'
import { useT } from '@/i18n'
import { formatSI } from '@/lib/format'
import { crossSection, type FluxData } from '@/sim/gauss'
import { PLANE_BASIS } from '@/sim/request'
import { displayOf, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { CLASS_COLORS, FLUX_COLORS, fluxColors } from './gaussColors'

function arr(flux: FluxData, s: SurfaceFlux, name: string): Float32Array | undefined {
  return flux.result.arrays[`surf${s.index}.${name}`]?.data
}

function SurfaceMesh({ flux, s }: { flux: FluxData; s: SurfaceFlux }) {
  const surface = useSceneStore((st) => st.surfaces.find((x) => x.id === s.surface_id))
  const selected = useSceneStore((st) => st.selectedSurfaceId === s.surface_id)
  const tool = useViewStore((v) => v.tool)
  const patch = useViewStore((v) => (selected ? v.selectedPatch : null))
  const invalidate = useThree((st) => st.invalidate)
  const display = surface ? displayOf(surface) : null
  const tris = arr(flux, s, 'triangles')
  const en = arr(flux, s, 'En')
  const cls = arr(flux, s, 'En_class')
  const normals = arr(flux, s, 'normals')
  const centroids = arr(flux, s, 'centroids')
  const geometry = useMemo(() => {
    if (!tris || !en || !cls) return null
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(tris, 3))
    g.setAttribute('color', new THREE.BufferAttribute(fluxColors(en, cls, display?.color_by_flux ?? true), 3))
    g.computeVertexNormals()
    return g
  }, [tris, en, cls, display?.color_by_flux])
  const edges = useMemo(() => (geometry ? new THREE.EdgesGeometry(geometry, 1) : null), [geometry])
  useEffect(() => {
    invalidate()
    return () => {
      geometry?.dispose()
      edges?.dispose()
    }
  }, [geometry, edges, invalidate])
  if (!geometry || !edges || !display?.visible) return null
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    if (tool !== 'select') return
    e.stopPropagation()
    const store = useSceneStore.getState()
    if (store.selectedSurfaceId !== s.surface_id) store.selectSurface(s.surface_id)
    else if (e.faceIndex !== undefined) useViewStore.getState().set({ selectedPatch: e.faceIndex })
  }
  return (
    <group>
      <mesh geometry={geometry} onClick={onClick} renderOrder={1}>
        <meshBasicMaterial vertexColors transparent opacity={display.opacity} depthWrite={false} side={THREE.DoubleSide} toneMapped={false} />
      </mesh>
      <lineSegments geometry={edges} renderOrder={2} raycast={() => null}>
        <lineBasicMaterial color={selected ? '#e9d5ff' : FLUX_COLORS.neutral} transparent opacity={selected ? 0.55 : 0.3} depthWrite={false} />
      </lineSegments>
      {display.show_normals && normals && centroids && <Normals normals={normals} centroids={centroids} length={(s.mesh?.l_char_m ?? 1) * 0.07} />}
      {patch !== null && tris && patch * 9 + 8 < tris.length && (
        <Line
          points={[0, 1, 2, 0].map((v) => [tris[patch * 9 + 3 * v]!, tris[patch * 9 + 3 * v + 1]!, tris[patch * 9 + 3 * v + 2]!] as Vec3)}
          color="#ffffff"
          lineWidth={2.5}
          renderOrder={7}
          depthTest={false}
        />
      )}
    </group>
  )
}

const UP = new THREE.Vector3(0, 1, 0)

/** Outward normals of the oriented surface (subsampled to at most ~400 for legibility). */
function Normals({ normals, centroids, length }: { normals: Float32Array; centroids: Float32Array; length: number }) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const invalidate = useThree((s) => s.invalidate)
  const { lines, heads } = useMemo(() => {
    const n = normals.length / 3
    const step = Math.max(1, Math.ceil(n / 400))
    const lines: number[] = []
    const heads: [THREE.Vector3, THREE.Vector3][] = []
    for (let t = 0; t < n; t += step) {
      const c = new THREE.Vector3(centroids[3 * t], centroids[3 * t + 1], centroids[3 * t + 2])
      const d = new THREE.Vector3(normals[3 * t], normals[3 * t + 1], normals[3 * t + 2])
      const tip = c.clone().addScaledVector(d, length)
      lines.push(c.x, c.y, c.z, tip.x, tip.y, tip.z)
      heads.push([tip, d])
    }
    return { lines, heads }
  }, [normals, centroids, length])
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const sc = new THREE.Vector3(length * 0.18, length * 0.3, length * 0.18)
    heads.forEach(([tip, d], i) => mesh.setMatrixAt(i, m.compose(tip, q.setFromUnitVectors(UP, d), sc)))
    mesh.instanceMatrix.needsUpdate = true
    invalidate()
  }, [heads, length, invalidate])
  return (
    <>
      <Line points={lines} segments color="#e2e8f0" lineWidth={1} transparent opacity={0.8} />
      <instancedMesh key={heads.length} ref={ref} args={[undefined, undefined, heads.length]} frustumCulled={false}>
        <coneGeometry args={[1, 1, 8]} />
        <meshBasicMaterial color="#e2e8f0" toneMapped={false} />
      </instancedMesh>
    </>
  )
}

/** Inside / outside / boundary classification of every charge for the selected surface. */
function ChargeClasses({ s, size }: { s: SurfaceFlux; size: number }) {
  return (
    <>
      {s.charges.map((c) => (
        <group key={c.object_id} position={c.position_m as Vec3}>
          <Billboard>
            <mesh renderOrder={6}>
              <ringGeometry args={[size * 3.0, size * 3.4, 40]} />
              <meshBasicMaterial color={CLASS_COLORS[c.state]} transparent opacity={0.95} depthTest={false} toneMapped={false} />
            </mesh>
            {c.near_boundary && c.state !== 'boundary' && (
              <mesh renderOrder={6}>
                <ringGeometry args={[size * 3.8, size * 4.0, 40]} />
                <meshBasicMaterial color={CLASS_COLORS.near} transparent opacity={0.9} depthTest={false} toneMapped={false} />
              </mesh>
            )}
          </Billboard>
        </group>
      ))}
    </>
  )
}

const FACE_DIRS = ['-x', '+x', '-y', '+y', '-z', '+z'] as const

/** Subdivision cells: all cell edges, and for the selected cell its six faces with their flux. */
function Cells({ flux, s }: { flux: FluxData; s: SurfaceFlux }) {
  const { t } = useT()
  const selectedCell = useViewStore((v) => v.selectedCell)
  const corners = arr(flux, s, 'cells.corners')
  const faceFlux = arr(flux, s, 'cells.face_flux_E')
  const neighbour = arr(flux, s, 'cells.face_neighbor')
  const sub = s.subdivision
  const lines = useMemo(() => {
    if (!corners) return []
    const out: number[] = []
    for (let c = 0; c < corners.length / 24; c++) {
      for (let m = 0; m < 8; m++)
        for (const bit of [1, 2, 4]) {
          if (m & bit) continue
          const a = 24 * c + 3 * m
          const b = 24 * c + 3 * (m | bit)
          out.push(corners[a]!, corners[a + 1]!, corners[a + 2]!, corners[b]!, corners[b + 1]!, corners[b + 2]!)
        }
    }
    return out
  }, [corners])
  if (!sub || !corners || !faceFlux || !neighbour) return null
  const cell = selectedCell !== null && selectedCell < sub.cells.length ? selectedCell : null
  const faceCentre = (c: number, f: number): Vec3 => {
    const axisBit = [1, 2, 4][Math.floor(f / 2)]!
    const want = f % 2 === 1
    const p: Vec3 = [0, 0, 0]
    let k = 0
    for (let m = 0; m < 8; m++) {
      if (Boolean(m & axisBit) !== want) continue
      for (let a = 0; a < 3; a++) p[a] = p[a]! + corners[24 * c + 3 * m + a]!
      k++
    }
    return p.map((x) => x / k) as Vec3
  }
  return (
    <>
      <Line points={lines} segments color="#c4b5fd" lineWidth={1} transparent opacity={0.45} />
      {cell !== null &&
        FACE_DIRS.map((dir, f) => {
          const nb = neighbour[6 * cell + f]!
          const phi = faceFlux[6 * cell + f]!
          const opposite = f % 2 === 0 ? f + 1 : f - 1
          const partner = nb >= 0 ? faceFlux[6 * nb + opposite]! : null
          return (
            <Html key={dir} position={faceCentre(cell, f)} center style={{ pointerEvents: 'none' }} zIndexRange={[20, 0]}>
              <div data-testid="cell-face-label" className={`whitespace-nowrap rounded border px-1 py-0.5 font-mono text-[10px] backdrop-blur ${nb >= 0 ? 'border-accent-2/60 bg-panel/80' : 'border-border bg-panel/80'}`}>
                {dir}: {formatSI(phi, 'V·m')}
                {partner !== null && <div className="text-accent-2">{t('cells.sharedSum', { sum: formatSI(phi + partner, 'V·m') })}</div>}
              </div>
            </Html>
          )
        })}
    </>
  )
}

/** Gizmo for the selected surface (3D, translate and rotate). A proxy object is moved; the
 *  new pose goes to the store, and the engine returns the new mesh. */
function SurfaceGizmo() {
  const surface = useSceneStore((st) => st.surfaces.find((x) => x.id === st.selectedSurfaceId))
  const mode = useViewStore((v) => (v.transformMode === 'scale' ? 'translate' : v.transformMode))
  const snap = useViewStore((v) => (v.snap ? v.snapStep : null))
  const [proxy, setProxy] = useState<THREE.Group | null>(null)
  useEffect(() => {
    if (!proxy || !surface) return
    proxy.position.set(...surface.center_m)
    proxy.rotation.set(...surface.rotation_euler_xyz_rad)
  }, [proxy, surface])
  if (!surface) return null
  return (
    <>
      <group ref={setProxy} />
      {proxy && (
        <TransformControls
          object={proxy}
          mode={mode}
          size={0.8}
          translationSnap={snap}
          rotationSnap={snap ? Math.PI / 12 : null}
          onMouseDown={() => useViewStore.getState().set({ dragging: true })}
          onMouseUp={() => useViewStore.getState().set({ dragging: false })}
          onObjectChange={() =>
            useSceneStore.getState().updateSurface(surface.id, {
              center_m: proxy.position.toArray() as Vec3,
              rotation_euler_xyz_rad: [proxy.rotation.x, proxy.rotation.y, proxy.rotation.z],
            })
          }
        />
      )}
    </>
  )
}

/** In 2D: where each (3D) surface crosses the slice plane, coloured like the surface. */
function CrossSections({ flux }: { flux: FluxData }) {
  const plane = useViewStore((v) => v.plane)
  const offset = useViewStore((v) => v.offset)
  const surfaces = useSceneStore((st) => st.surfaces)
  const selectedId = useSceneStore((st) => st.selectedSurfaceId)
  const b = PLANE_BASIS[plane]
  const centre: Vec3 = [0, 0, 0]
  centre[b.nAxis] = offset
  return (
    <>
      {flux.header.surfaces.map((s) => {
        const surface = surfaces.find((x) => x.id === s.surface_id)
        const tris = arr(flux, s, 'triangles')
        const en = arr(flux, s, 'En')
        const cls = arr(flux, s, 'En_class')
        if (!surface || !tris || !en || !cls || !displayOf(surface).visible) return null
        const cut = crossSection(tris, centre, b.normal)
        if (cut.points.length === 0) return null
        const triColors = fluxColors(en, cls, displayOf(surface).color_by_flux)
        const colors = cut.triangle.flatMap((t) => [
          [triColors[9 * t]!, triColors[9 * t + 1]!, triColors[9 * t + 2]!] as [number, number, number],
          [triColors[9 * t]!, triColors[9 * t + 1]!, triColors[9 * t + 2]!] as [number, number, number],
        ])
        const width = s.surface_id === selectedId ? 3.5 : 2
        return (
          <group key={s.surface_id}>
            {/* Dark outline first, so the line stays visible on any colour map. */}
            {/* transparent: drawn in the same pass as, and after, the colour-map plane. */}
            <Line points={cut.points} segments color="#05070d" lineWidth={width + 3} renderOrder={5} transparent opacity={1} />
            <Line
              points={cut.points}
              segments
              vertexColors={colors}
              lineWidth={width}
              renderOrder={6}
              transparent
              opacity={1}
              onClick={(e) => {
                e.stopPropagation()
                useSceneStore.getState().selectSurface(s.surface_id)
              }}
            />
          </group>
        )
      })}
    </>
  )
}

export function GaussLayer({ flux, marker }: { flux: FluxData | undefined; marker: number }) {
  const mode = useViewStore((v) => v.mode)
  const tool = useViewStore((v) => v.tool)
  const selectedId = useSceneStore((st) => st.selectedSurfaceId)
  if (!flux) return mode === '3d' && tool === 'select' ? <SurfaceGizmo /> : null
  const selected = flux.header.surfaces.find((s) => s.surface_id === selectedId)
  return (
    <>
      {mode === '3d' ? flux.header.surfaces.map((s) => (s.mesh ? <SurfaceMesh key={s.surface_id} flux={flux} s={s} /> : null)) : <CrossSections flux={flux} />}
      {selected && <ChargeClasses s={selected} size={marker} />}
      {selected && mode === '3d' && <Cells flux={flux} s={selected} />}
      {mode === '3d' && tool === 'select' && <SurfaceGizmo />}
    </>
  )
}
