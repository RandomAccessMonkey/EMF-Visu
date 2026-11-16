import { create } from 'zustand'
import type { Vec3 } from '@/api/types'
import type { SlicePlane } from '@/sim/request'

export type Lang = 'en' | 'hu'

/** Settings that are saved with a project. */
export interface ViewSettings {
  mode: '2d' | '3d'
  plane: SlicePlane
  offset: number
  showArrows: boolean
  heatmap: 'phi' | 'E' | 'none'
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
  heatmap: 'phi',
  showLattice: true,
  showSliceIn3d: true,
  showGrid: true,
  arrowDensity: 21,
  latticeDensity: 7,
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
  return out as Partial<ViewSettings>
}
