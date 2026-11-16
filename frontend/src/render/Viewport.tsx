import { Line, OrbitControls, OrthographicCamera, PerspectiveCamera } from '@react-three/drei'
import { Canvas, useThree } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import type { SimulationResult } from '@/api/container'
import type { Domain, LatticeSampling, PlaneGridSampling, Vec3 } from '@/api/types'
import { latticePoints, PLANE_BASIS, planeGridPoints } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { ArrowField } from './ArrowField'
import type { LogScale } from './colormaps'
import { magnitudes, sampling, type HeatImage } from './fieldImages'
import { SceneObjects } from './SceneObjects'

// Physics convention: right-handed, z up. Three.js is told so once; no axis swapping anywhere.
THREE.Object3D.DEFAULT_UP.set(0, 0, 1)

const center = (d: Domain): Vec3 => [0, 1, 2].map((a) => (d.min_m[a]! + d.max_m[a]!) / 2) as Vec3
const extent = (d: Domain, a: number) => d.max_m[a]! - d.min_m[a]!

function Cameras({ domain }: { domain: Domain }) {
  const mode = useViewStore((s) => s.mode)
  const plane = useViewStore((s) => s.plane)
  const offset = useViewStore((s) => s.offset)
  const token = useViewStore((s) => s.cameraResetToken)
  const size = useThree((s) => s.size)
  const b = PLANE_BASIS[plane]
  const c = center(domain)
  const diag = Math.hypot(extent(domain, 0), extent(domain, 1), extent(domain, 2))
  if (mode === '2d') {
    const target = [...c] as Vec3
    target[b.nAxis] = offset
    const position = target.map((v, a) => v + b.normal[a]! * diag * 2) as Vec3
    const zoom = 0.92 * Math.min(size.width / extent(domain, b.uAxis), size.height / extent(domain, b.vAxis))
    return (
      <group key={`2d-${plane}-${token}`}>
        <OrthographicCamera makeDefault position={position} up={b.v} zoom={zoom} near={0.01} far={diag * 10} />
        <OrbitControls
          makeDefault
          target={target}
          enableRotate={false}
          zoomToCursor
          mouseButtons={{ MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }}
          touches={{ TWO: THREE.TOUCH.DOLLY_PAN }}
        />
      </group>
    )
  }
  const position: Vec3 = [c[0] + diag * 0.75, c[1] - diag * 0.95, c[2] + diag * 0.6]
  return (
    <group key={`3d-${token}`}>
      <PerspectiveCamera makeDefault position={position} up={[0, 0, 1]} fov={42} near={0.01} far={diag * 20} />
      <OrbitControls makeDefault target={c} enableDamping dampingFactor={0.12} />
    </group>
  )
}

function DomainFrame({ domain }: { domain: Domain }) {
  const geometry = useMemo(() => {
    const box = new THREE.BoxGeometry(extent(domain, 0), extent(domain, 1), extent(domain, 2))
    const edges = new THREE.EdgesGeometry(box)
    box.dispose()
    return edges
  }, [domain])
  return (
    <lineSegments geometry={geometry} position={center(domain)}>
      <lineBasicMaterial color="#2a3a5c" />
    </lineSegments>
  )
}

/** Coordinate grid on the slice plane plus coloured axis lines through the origin. */
function GridAxes({ domain }: { domain: Domain }) {
  const plane = useViewStore((s) => s.plane)
  const offset = useViewStore((s) => s.offset)
  const step = useViewStore((s) => s.snapStep)
  const b = PLANE_BASIS[plane]
  const positions = useMemo(() => {
    const spacing = Math.max(step, 1e-3) * Math.ceil(0.5 / Math.max(step, 1e-3)) // ≈ 0.5 m lines
    const pts: number[] = []
    const add = (axis: number, other: number) => {
      const first = Math.ceil(domain.min_m[axis]! / spacing) * spacing
      for (let x = first; x <= domain.max_m[axis]! + 1e-9; x += spacing) {
        const p: number[] = [0, 0, 0]
        const q: number[] = [0, 0, 0]
        p[axis] = q[axis] = x
        p[other] = domain.min_m[other]!
        q[other] = domain.max_m[other]!
        p[b.nAxis] = q[b.nAxis] = offset
        pts.push(...p, ...q)
      }
    }
    add(b.uAxis, b.vAxis)
    add(b.vAxis, b.uAxis)
    return new Float32Array(pts)
  }, [domain, b, offset, step])
  const axes: [Vec3, Vec3, string][] = [
    [[domain.min_m[0], 0, 0], [domain.max_m[0], 0, 0], '#ff6b6b'],
    [[0, domain.min_m[1], 0], [0, domain.max_m[1], 0], '#51cf66'],
    [[0, 0, domain.min_m[2]], [0, 0, domain.max_m[2]], '#5c9dff'],
  ]
  return (
    <>
      <lineSegments key={positions.length} renderOrder={1}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color="#9fb4d8" transparent opacity={0.13} depthWrite={false} />
      </lineSegments>
      {axes.map(([a, c, color]) => (
        <Line key={color} points={[a, c]} color={color} lineWidth={1} transparent opacity={0.55} />
      ))}
    </>
  )
}

function SlicePlane({ image, grid, visible }: { image: HeatImage | null; grid: PlaneGridSampling; visible: boolean }) {
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const invalidate = useThree((s) => s.invalidate)
  const texture = useMemo(() => {
    if (!image) return null
    const data = new Uint8Array(image.pixels.buffer, image.pixels.byteOffset, image.pixels.byteLength)
    const tex = new THREE.DataTexture(data, image.width, image.height, THREE.RGBAFormat)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.magFilter = THREE.LinearFilter
    tex.minFilter = THREE.LinearFilter
    tex.needsUpdate = true
    return tex
  }, [image])
  useEffect(() => {
    invalidate()
    return () => texture?.dispose()
  }, [texture, invalidate])
  const matrix = useMemo(() => {
    const u = new THREE.Vector3(...grid.u_dir)
    const v = new THREE.Vector3(...grid.v_dir)
    return new THREE.Matrix4()
      .makeBasis(u, v, new THREE.Vector3().crossVectors(u, v))
      .setPosition(...grid.center_m)
  }, [grid])
  const show = visible && texture !== null
  return (
    <mesh
      matrix={matrix}
      matrixAutoUpdate={false}
      renderOrder={-1}
      onClick={(e) => {
        if (tool !== 'probe') return
        e.stopPropagation()
        useViewStore.getState().set({ probePoint: e.point.toArray() as Vec3 })
      }}
    >
      <planeGeometry args={[grid.u_extent_m, grid.v_extent_m]} />
      <meshBasicMaterial
        key={show ? 'heat' : 'pick'}
        map={show ? texture : null}
        toneMapped={false}
        transparent
        opacity={show ? (mode === '3d' ? 0.82 : 1) : 0}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}

function Arrows({ result, id, scale }: { result: SimulationResult; id: 'arrows' | 'vol'; scale: LogScale }) {
  const lengthMode = useViewStore((s) => s.arrowLength)
  const sizeFactor = useViewStore((s) => s.arrowScale)
  const data = useMemo(() => {
    const field = result.arrays[`${id}.E`]
    if (!field) return null
    if (id === 'arrows') {
      const g = sampling<PlaneGridSampling>(result, id)
      if (!g) return null
      const cell = Math.min(g.u_extent_m / (g.nu - 1), g.v_extent_m / (g.nv - 1))
      return { points: planeGridPoints(g), cell, vectors: field.data, mags: magnitudes(field.data) }
    }
    const l = sampling<LatticeSampling>(result, id)
    if (!l) return null
    const cell = Math.min(...[0, 1, 2].map((a) => (l.max_m[a]! - l.min_m[a]!) / ([l.nx, l.ny, l.nz][a]! - 1)))
    return { points: latticePoints(l), cell: cell * 0.7, vectors: field.data, mags: magnitudes(field.data) }
  }, [result, id])
  if (!data) return null
  return (
    <ArrowField
      points={data.points}
      vectors={data.vectors}
      magnitudes={data.mags}
      scale={scale}
      cell={data.cell}
      lengthMode={lengthMode}
      sizeFactor={sizeFactor}
    />
  )
}

function ProbeMarker({ size }: { size: number }) {
  const p = useViewStore((s) => s.probePoint)
  if (!p) return null
  return (
    <mesh position={p} renderOrder={5}>
      <sphereGeometry args={[size * 0.6, 16, 12]} />
      <meshBasicMaterial color="#ffffff" depthTest={false} toneMapped={false} />
    </mesh>
  )
}

function Invalidator({ deps }: { deps: unknown[] }) {
  const invalidate = useThree((s) => s.invalidate)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => invalidate(), deps)
  return null
}

interface Props {
  result: SimulationResult | undefined
  image: HeatImage | null
  arrowScale: LogScale | null
}

export function Viewport({ result, image, arrowScale }: Props) {
  const scene = useSceneStore((s) => s.scene)
  const selectedId = useSceneStore((s) => s.selectedId)
  const v = useViewStore()
  const domain = scene.domain
  const diag = Math.hypot(extent(domain, 0), extent(domain, 1), extent(domain, 2))
  const marker = diag * 0.011
  const grid = result ? sampling<PlaneGridSampling>(result, 'heat') : undefined
  const sliceVisible = v.mode === '2d' || v.showSliceIn3d
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      onPointerMissed={() => v.tool === 'select' && useSceneStore.getState().select(null)}
      style={{ cursor: v.tool === 'probe' ? 'crosshair' : 'default', touchAction: 'none' }}
    >
      <color attach="background" args={['#070b14']} />
      <ambientLight intensity={1.4} />
      <directionalLight position={[3, -4, 6]} intensity={1.6} />
      <Cameras domain={domain} />
      <Invalidator deps={[scene, selectedId, v.mode, v.plane, v.offset, v.probePoint, v.showGrid, v.tool, result]} />
      {v.mode === '3d' && <DomainFrame domain={domain} />}
      {v.showGrid && <GridAxes domain={domain} />}
      {grid && <SlicePlane image={image} grid={grid} visible={sliceVisible && v.heatmap !== 'none'} />}
      {result && arrowScale && v.showArrows && sliceVisible && (
        <Arrows result={result} id="arrows" scale={arrowScale} />
      )}
      {result && arrowScale && v.mode === '3d' && v.showLattice && (
        <Arrows result={result} id="vol" scale={arrowScale} />
      )}
      <SceneObjects marker={marker} />
      <ProbeMarker size={marker} />
    </Canvas>
  )
}
