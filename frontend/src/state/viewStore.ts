import { create } from 'zustand'
import type { Vec3 } from '@/api/types'
import { ARROW_DENSITIES, LATTICE_DENSITIES, nearest, type SlicePlane } from '@/sim/request'

export type Lang = 'en' | 'hu'

/** Scalar colour maps. 'E' is |E|; 'curl_E' and 'curl_D' are the curl magnitudes. */
export const SCALAR_MAPS = ['phi', 'E', 'div_E', 'curl_E', 'div_D', 'curl_D', 'none'] as const
export type ScalarMap = (typeof SCALAR_MAPS)[number]

/** Settings that are saved with a project. */
export interface ViewSettings {
  mode: '2d' | '3d'
  plane: SlicePlane
  offset: number
  showArrows: boolean
  vectorField: 'E' | 'D'
  showFieldLines: boolean
  lineDensity: number // density level 0..2 (each level is a complete, precomputed set)
  showContours: boolean
  showIsosurfaces: boolean
  heatmap: ScalarMap
  showCurl: boolean
  curlField: 'E' | 'D'
  showSources: boolean
  showVolumeScalars: boolean
  showLattice: boolean
  showSliceIn3d: boolean
  showGrid: boolean
  arrowDensity: number
  latticeDensity: number
  arrowScale: number
  arrowLength: 'uniform' | 'log'
  snap: boolean
  snapStep: number
}

export const DEFAULT_VIEW: ViewSettings = {
  mode: '2d',
  plane: 'xy',
  offset: 0,
  showArrows: true,
  vectorField: 'E',
  showFieldLines: true,
  lineDensity: 1,
  showContours: true,
  showIsosurfaces: true,
  heatmap: 'phi',
  showCurl: false,
  curlField: 'E',
  showSources: true,
  showVolumeScalars: false,
  showLattice: false,
  showSliceIn3d: true,
  showGrid: true,
  arrowDensity: 13,
  latticeDensity: 5,
  arrowScale: 1,
  arrowLength: 'uniform',
  snap: true,
  snapStep: 0.1,
}

interface ViewState extends ViewSettings {
  lang: Lang
  level: 'beginner' | 'advanced'
  tool: 'select' | 'probe'
  transformMode: 'translate' | 'rotate' | 'scale'
  dragging: boolean
  /** Selected triangle of the selected Gaussian surface, and selected subdivision cell. */
  selectedPatch: number | null
  selectedCell: number | null
  probePoint: Vec3 | null
  cameraResetToken: number
  set: (patch: Partial<ViewState>) => void
  settings: () => ViewSettings
}

const storedLang = (): Lang => {
  try {
    const v = localStorage.getItem('emf.lang')
    if (v === 'en' || v === 'hu') return v
  } catch {
    // storage unavailable: fall through to the browser language
  }
  return typeof navigator !== 'undefined' && navigator.language.startsWith('hu') ? 'hu' : 'en'
}

export const useViewStore = create<ViewState>((set, get) => ({
  ...DEFAULT_VIEW,
  lang: storedLang(),
  level: 'beginner',
  tool: 'select',
  transformMode: 'translate',
  dragging: false,
  selectedPatch: null,
  selectedCell: null,
  probePoint: null,
  cameraResetToken: 0,
  set: (patch) => {
    if (patch.lang) {
      try {
        localStorage.setItem('emf.lang', patch.lang)
      } catch {
        // ignore
      }
    }
    set(patch)
  },
  settings: () => {
    const s = get()
    const out = {} as Record<string, unknown>
    for (const k of Object.keys(DEFAULT_VIEW)) out[k] = s[k as keyof ViewSettings]
    return out as unknown as ViewSettings
  },
}))

/** Accept only known keys with the right primitive type when loading a saved project. */
export function sanitizeView(raw: Record<string, unknown>): Partial<ViewSettings> {
  const out: Record<string, unknown> = {}
  for (const [k, def] of Object.entries(DEFAULT_VIEW)) {
    if (k in raw && typeof raw[k] === typeof def) out[k] = raw[k]
  }
  // Projects saved before Phase 2A may hold densities that are no longer offered.
  if (typeof out.arrowDensity === 'number') out.arrowDensity = nearest(ARROW_DENSITIES, out.arrowDensity)
  if (typeof out.latticeDensity === 'number') out.latticeDensity = nearest(LATTICE_DENSITIES, out.latticeDensity)
  if (typeof out.lineDensity === 'number') out.lineDensity = Math.min(2, Math.max(0, Math.round(out.lineDensity)))
  if (out.vectorField !== undefined && out.vectorField !== 'E' && out.vectorField !== 'D') delete out.vectorField
  if (out.curlField !== undefined && out.curlField !== 'E' && out.curlField !== 'D') delete out.curlField
  if (out.heatmap !== undefined && !(SCALAR_MAPS as readonly string[]).includes(out.heatmap as string)) delete out.heatmap
  return out as Partial<ViewSettings>
}
