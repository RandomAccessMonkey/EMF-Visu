import { Line, OrbitControls, OrthographicCamera, PerspectiveCamera } from '@react-three/drei'
import { Canvas, useThree } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import type { SimulationResult } from '@/api/container'
import type { Domain, LatticeSampling, PlaneGridSampling, Vec3 } from '@/api/types'
import { PLANE_BASIS, subsampleLattice, subsamplePlane } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { ArrowField } from './ArrowField'
import type { LogScale } from './colormaps'
import { CurlGlyphs, SourceMarkers, VolumeScalars } from './CalculusLayers'
import { Contours, FieldLines, Isosurfaces } from './FieldProducts'
import { AmpereLayer } from './AmpereLayer'
import { GaussLayer } from './GaussLayer'
import type { AmpereData } from '@/sim/useAmpere'
import type { FluxData } from '@/sim/gauss'
import { isMagneticKind, magnitudes, sampling, type HeatImage } from './fieldImages'
import { SceneObjects } from './SceneObjects'
import { CurrentMarkers, MagneticArrows } from './MagneticLayers'
import { MAGNETIC_LINE_COLOR, MAGNETIC_NUMERICAL_LINE_COLOR } from './magneticColors'

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

const planeMatrix = (g: PlaneGridSampling) => {
  const u = new THREE.Vector3(...g.u_dir)
  const v = new THREE.Vector3(...g.v_dir)
  return new THREE.Matrix4().makeBasis(u, v, new THREE.Vector3().crossVectors(u, v)).setPosition(...g.center_m)
}

/** The colour map is drawn on the grid it was sampled on (the fine slice grid for φ and |E|,
 *  the vector grid for divergence and curl); a separate invisible plane over the whole slice
 *  receives probe clicks. */
function SlicePlane({ image, grid, visible }: { image: HeatImage | null; grid: PlaneGridSampling; visible: boolean }) {
  const mode = useViewStore((s) => s.mode)
  const tool = useViewStore((s) => s.tool)
  const invalidate = useThree((s) => s.invalidate)
  const texture = useMemo(() => {
    if (!image) return null
    const data = new Uint8Array(image.pixels.buffer, image.pixels.byteOffset, image.pixels.byteLength)
    const tex = new THREE.DataTexture(data, image.width, image.height, THREE.RGBAFormat)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.magFilter = image.nearest ? THREE.NearestFilter : THREE.LinearFilter
    tex.minFilter = image.nearest ? THREE.NearestFilter : THREE.LinearFilter
    tex.needsUpdate = true
    return tex
  }, [image])
  useEffect(() => {
    invalidate()
    return () => texture?.dispose()
  }, [texture, invalidate])
  const pickMatrix = useMemo(() => planeMatrix(grid), [grid])
  const imageGrid = image?.grid
  const imageMatrix = useMemo(() => (imageGrid ? planeMatrix(imageGrid) : null), [imageGrid])
  // Each texel is centred on its sample: the textured quad extends half a cell beyond the
  // outermost samples.
  const texSize: [number, number] | null = imageGrid
    ? [imageGrid.u_extent_m * (imageGrid.nu / (imageGrid.nu - 1)), imageGrid.v_extent_m * (imageGrid.nv / (imageGrid.nv - 1))]
    : null
  const sampledAtNodes = imageGrid && image && !image.nearest
  return (
    <>
      <mesh
        matrix={pickMatrix}
        matrixAutoUpdate={false}
        onClick={(e) => {
          if (tool !== 'probe') return
          e.stopPropagation()
          useViewStore.getState().set({ probePoint: e.point.toArray() as Vec3 })
        }}
      >
        <planeGeometry args={[grid.u_extent_m, grid.v_extent_m]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      {visible && texture && imageMatrix && imageGrid && texSize && (
        <mesh matrix={imageMatrix} matrixAutoUpdate={false} renderOrder={-1} raycast={() => null}>
          <planeGeometry args={sampledAtNodes ? [imageGrid.u_extent_m, imageGrid.v_extent_m] : texSize} />
          <meshBasicMaterial map={texture} toneMapped={false} transparent opacity={mode === '3d' ? 0.82 : 1} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
      )}
    </>
  )
}

function Arrows({ result, id, scale }: { result: SimulationResult; id: 'arrows' | 'vol'; scale: LogScale }) {
  const lengthMode = useViewStore((s) => s.arrowLength)
  const sizeFactor = useViewStore((s) => s.arrowScale)
  const quantity = useViewStore((s) => s.vectorField)
  const density = useViewStore((s) => (id === 'arrows' ? s.arrowDensity : s.latticeDensity))
  // Changing the density or the displayed vector field only re-reads the cached arrays.
  const data = useMemo(() => {
    const field = result.arrays[`${id}.${quantity}`]
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
  }, [result, id, quantity, density])
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
  flux?: FluxData | undefined
  result: SimulationResult | undefined
  /** Magnetic result (Phase 3A), solved and cached independently of the electric one. */
  magnetic?: SimulationResult | undefined
  image: HeatImage | null
  arrowScale: LogScale | null
  magneticArrowScale?: LogScale | null
  /** Ampère's law results (Phase 3B), for the crossing markers of the paths. */
  ampere?: AmpereData | undefined
}

export function Viewport({ result, magnetic, image, arrowScale, magneticArrowScale, flux, ampere }: Props) {
  const surfaces = useSceneStore((s) => s.surfaces)
  const paths = useSceneStore((s) => s.paths)
  const selectedPathId = useSceneStore((s) => s.selectedPathId)
  const selectedSurfaceId = useSceneStore((s) => s.selectedSurfaceId)
  const patch = useViewStore((s) => s.selectedPatch)
  const cell = useViewStore((s) => s.selectedCell)
  const scene = useSceneStore((s) => s.scene)
  const selectedId = useSceneStore((s) => s.selectedId)
  const v = useViewStore()
  const domain = scene.domain
  const diag = Math.hypot(extent(domain, 0), extent(domain, 1), extent(domain, 2))
  const marker = diag * 0.011
  // Both results sample the same slice; either one provides the plane (for probe clicks too).
  const grid = result ? sampling<PlaneGridSampling>(result, 'heat') : magnetic ? sampling<PlaneGridSampling>(magnetic, 'heat') : undefined
  const sliceVisible = v.mode === '2d' || v.showSliceIn3d
  // Charges off the slice plane, according to the engine's source table.
  const offSlice = useMemo(
    () => new Set((result?.header.point_sources ?? []).filter((s) => s.in_plane['heat'] === false).map((s) => s.object_id)),
    [result],
  )
  return (
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      onPointerMissed={() => {
        if (v.tool !== 'select') return
        useSceneStore.getState().select(null)
        useSceneStore.getState().selectSurface(null)
        useViewStore.getState().set({ selectedPatch: null })
      }}
      style={{ cursor: v.tool === 'probe' ? 'crosshair' : 'default', touchAction: 'none' }}
    >
      <color attach="background" args={['#070b14']} />
      <ambientLight intensity={1.4} />
      <directionalLight position={[3, -4, 6]} intensity={1.6} />
      <Cameras domain={domain} />
      <Invalidator deps={[scene, selectedId, v.mode, v.plane, v.offset, v.probePoint, v.showGrid, v.tool, result, v.showFieldLines, v.lineDensity, v.showContours, v.showIsosurfaces, v.showCurl, v.curlField, v.showSources, v.showVolumeScalars, v.heatmap, flux, surfaces, selectedSurfaceId, patch, cell, magnetic, v.showBArrows, v.magneticField, v.showBLines, v.showCurrents, v.showCurrentDirection, v.contribution, paths, ampere, selectedPathId]} />
      {v.mode === '3d' && <DomainFrame domain={domain} />}
      {v.showGrid && <GridAxes domain={domain} />}
      {grid && <SlicePlane image={image} grid={grid} visible={sliceVisible && v.heatmap !== 'none'} />}
      {result && arrowScale && v.showArrows && sliceVisible && (
        <Arrows result={result} id="arrows" scale={arrowScale} />
      )}
      {result && arrowScale && v.mode === '3d' && v.showLattice && (
        <Arrows result={result} id="vol" scale={arrowScale} />
      )}
      {result && v.showContours && sliceVisible && <Contours result={result} />}
      {result && v.showFieldLines && <FieldLines result={result} level={v.lineDensity} markerSize={marker * 0.9} />}
      {result && v.mode === '3d' && v.showIsosurfaces && <Isosurfaces result={result} />}
      {result && v.showCurl && sliceVisible && <CurlGlyphs result={result} id="arrows" field={v.curlField} />}
      {result && v.showCurl && v.mode === '3d' && v.showLattice && <CurlGlyphs result={result} id="vol" field={v.curlField} />}
      {v.mode === '3d' && v.showVolumeScalars && v.heatmap !== 'none' && (isMagneticKind(v.heatmap) ? magnetic : result) && (
        <VolumeScalars result={(isMagneticKind(v.heatmap) ? magnetic : result)!} kind={v.heatmap} />
      )}
      {result && v.showSources && <SourceMarkers result={result} size={marker} />}
      {magnetic && magneticArrowScale && v.showBArrows && sliceVisible && <MagneticArrows result={magnetic} id="arrows" scale={magneticArrowScale} />}
      {magnetic && magneticArrowScale && v.showBArrows && v.mode === '3d' && v.showLattice && <MagneticArrows result={magnetic} id="vol" scale={magneticArrowScale} />}
      {magnetic && v.showBLines && <FieldLines result={magnetic} level={v.lineDensity} markerSize={marker * 0.9} color={MAGNETIC_LINE_COLOR} numericalColor={MAGNETIC_NUMERICAL_LINE_COLOR} />}
      {magnetic && <CurrentMarkers result={magnetic} size={marker} />}
      <GaussLayer flux={flux} marker={marker} />
      <AmpereLayer ampere={ampere} marker={marker} />
      <SceneObjects marker={marker} offSlice={offSlice} wireLength={diag} />
      <ProbeMarker size={marker} />
    </Canvas>
  )
}
