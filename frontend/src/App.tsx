import * as Tabs from '@radix-ui/react-tabs'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo } from 'react'
import { useT, type MessageKey } from '@/i18n'
import { EquationsPanel } from '@/panels/EquationsPanel'
import { Legend, ViewStatement } from '@/panels/Legend'
import { ObjectsPanel } from '@/panels/ObjectsPanel'
import { ParametersPanel } from '@/panels/ParametersPanel'
import { ResultsPanel, SimulationError } from '@/panels/ResultsPanel'
import { StatusBar } from '@/panels/StatusBar'
import { TopBar } from '@/panels/TopBar'
import { VisualizationPanel } from '@/panels/VisualizationPanel'
import { heatImage, magnitudeScale, magnitudes } from '@/render/fieldImages'
import { Viewport } from '@/render/Viewport'
import { useSimulation } from '@/sim/useSimulation'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const TABS = ['parameters', 'visualization', 'equations', 'results'] as const

function useKeyboardShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      const scene = useSceneStore.getState()
      const view = useViewStore.getState()
      if ((e.key === 'Delete' || e.key === 'Backspace') && scene.selectedId) scene.remove(scene.selectedId)
      else if (e.key === 'Escape') scene.select(null)
      else if (e.key === '2') view.set({ mode: '2d' })
      else if (e.key === '3') view.set({ mode: '3d' })
      else if (e.key === 'p') view.set({ tool: view.tool === 'probe' ? 'select' : 'probe' })
      else if (scene.selectedId && e.key.startsWith('Arrow')) {
        // Nudge the selected object by one snap step along x / y.
        const o = scene.scene.objects.find((x) => x.id === scene.selectedId)
        if (!o) return
        const step = view.snapStep * (e.shiftKey ? 10 : 1)
        const [x, y, z] = o.transform.position_m
        const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key]
        if (!d) return
        e.preventDefault()
        scene.setTransform(o.id, { position_m: [x + d[0]!, y + d[1]!, z] })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

export default function App() {
  const { t, lang } = useT()
  const sim = useSimulation()
  const heatKind = useViewStore((s) => s.heatmap)
  useKeyboardShortcuts()
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  // Colour mapping of cached engine arrays: recomputed on visual changes without any re-solve.
  const image = useMemo(
    () => (sim.result && heatKind !== 'none' ? heatImage(sim.result, heatKind) : null),
    [sim.result, heatKind],
  )
  const arrowScale = useMemo(() => {
    const field = sim.result?.arrays['arrows.E']
    return field ? magnitudeScale(magnitudes(field.data)) : null
  }, [sim.result])

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside aria-label={t('layout.objects')} className="order-2 max-h-64 w-full shrink-0 border-border bg-panel lg:order-1 lg:max-h-none lg:w-72 lg:border-r">
          <ObjectsPanel />
        </aside>
        <main className="order-1 flex min-h-[45vh] min-w-0 flex-1 flex-col lg:order-2">
          <ViewStatement />
          <div className="relative min-h-0 flex-1">
          <Viewport result={sim.error ? undefined : sim.result} image={sim.error ? null : image} arrowScale={sim.error ? null : arrowScale} />
          <Legend heat={sim.error ? null : (image?.legend ?? null)} arrows={sim.error ? null : arrowScale} />
          <AnimatePresence>
            {sim.error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="absolute right-3 top-3 w-80 max-w-[90%] rounded-lg bg-panel shadow-xl"
              >
                <SimulationError error={sim.error} />
              </motion.div>
            )}
          </AnimatePresence>
          </div>
        </main>
        <Tabs.Root defaultValue="parameters" className="order-3 flex max-h-[45vh] w-full shrink-0 flex-col border-border bg-panel lg:max-h-none lg:w-80 lg:border-l">
          <Tabs.List aria-label={t('layout.panels')} className="flex border-b border-border">
            {TABS.map((tab) => (
              <Tabs.Trigger
                key={tab}
                value={tab}
                className="flex-1 border-b-2 border-transparent px-1 py-2 text-[11px] font-medium text-muted transition-colors hover:text-text data-[state=active]:border-accent data-[state=active]:text-accent"
              >
                {t(`tab.${tab}` as MessageKey)}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Tabs.Content value="parameters"><ParametersPanel /></Tabs.Content>
            <Tabs.Content value="visualization"><VisualizationPanel sim={sim} /></Tabs.Content>
            <Tabs.Content value="equations"><EquationsPanel /></Tabs.Content>
            <Tabs.Content value="results"><ResultsPanel sim={sim} /></Tabs.Content>
          </div>
        </Tabs.Root>
      </div>
      <StatusBar sim={sim} />
    </div>
  )
}
