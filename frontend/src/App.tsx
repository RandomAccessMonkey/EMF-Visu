import * as Tabs from '@radix-ui/react-tabs'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo } from 'react'
import { useT, type MessageKey } from '@/i18n'
import { AmperePanel } from '@/panels/AmperePanel'
import { FaradayPanel } from '@/panels/FaradayPanel'
import { TimeBar } from '@/panels/TimeBar'
import { EquationsPanel } from '@/panels/EquationsPanel'
import { GaussPanel } from '@/panels/GaussPanel'
import { Legend, ViewStatement } from '@/panels/Legend'
import { ObjectsPanel } from '@/panels/ObjectsPanel'
import { ParametersPanel } from '@/panels/ParametersPanel'
import { ResultsPanel, SimulationError } from '@/panels/ResultsPanel'
import { StatusBar } from '@/panels/StatusBar'
import { TopBar } from '@/panels/TopBar'
import { VisualizationPanel } from '@/panels/VisualizationPanel'
import { heatImage, isMagneticKind, magnitudeScale, magnitudes } from '@/render/fieldImages'
import { effectiveContribution, magneticArrayName } from '@/render/MagneticLayers'
import { Viewport } from '@/render/Viewport'
import { useAmpere } from '@/sim/useAmpere'
import { useInduction } from '@/sim/useInduction'
import { useLorentz } from '@/sim/useLorentz'
import { LorentzPanel } from '@/panels/LorentzPanel'
import { isTimeDependent } from '@/sim/request'
import { useFlux } from '@/sim/useFlux'
import { useSimulation } from '@/sim/useSimulation'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const TABS = ['parameters', 'visualization', 'gauss', 'ampere', 'faraday', 'lorentz', 'equations', 'results'] as const

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
  const flux = useFlux()
  const ampere = useAmpere()
  const induction = useInduction()
  const lorentz = useLorentz()
  const trajectoryOn = useSceneStore((s) => !!s.testCharge?.enabled && !!s.testCharge.trajectory.enabled)
  const timeDependent = useSceneStore((s) => isTimeDependent(s.scene))
  const hasFluxSurfaces = useSceneStore((s) => s.fluxSurfaces.length > 0)
  const heatKind = useViewStore((s) => s.heatmap)
  useKeyboardShortcuts()
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  // Colour mapping of cached engine arrays: recomputed on visual changes without any re-solve.
  // Magnetic maps (|B|, |H|, ∇·B) come from the magnetic result, the others from the electric.
  const contributionChoice = useViewStore((s) => s.contribution)
  const sourceIds = useMemo(() => sim.magnetic.result?.header.current_sources.map((c) => c.object_id) ?? [], [sim.magnetic.result])
  const contribution = effectiveContribution(contributionChoice, sourceIds)
  const heatResult = heatKind !== 'none' && isMagneticKind(heatKind) ? sim.magnetic.result : sim.result
  const image = useMemo(
    () => (heatResult && heatKind !== 'none' ? heatImage(heatResult, heatKind, contribution) : null),
    [heatResult, heatKind, contribution],
  )
  const vectorField = useViewStore((s) => s.vectorField)
  const arrowScale = useMemo(() => {
    const field = sim.result?.arrays[`arrows.${vectorField}`]
    return field ? magnitudeScale(magnitudes(field.data)) : null
  }, [sim.result, vectorField])
  // B/H arrows have their own scale and legend; with one source shown, that source's own field.
  const magneticField = useViewStore((s) => s.magneticField)
  const magneticArrowScale = useMemo(() => {
    const field = sim.magnetic.result?.arrays[magneticArrayName('arrows', magneticField, contribution)]
    return field ? magnitudeScale(magnitudes(field.data)) : null
  }, [sim.magnetic.result, magneticField, contribution])
  const error = sim.error ?? sim.magnetic.error

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside aria-label={t('layout.objects')} className="order-2 max-h-64 w-full shrink-0 border-border bg-panel lg:order-1 lg:max-h-none lg:w-72 lg:border-r">
          <ObjectsPanel />
        </aside>
        <main className="order-1 flex min-h-[45vh] min-w-0 flex-1 flex-col lg:order-2">
          <ViewStatement />
          {(timeDependent || hasFluxSurfaces || trajectoryOn) && <TimeBar waiting={sim.magnetic.isFetching || sim.magnetic.isStale || induction.isFetching || lorentz.trajectoryFetching} />}
          <div className="relative min-h-0 flex-1">
          <Viewport
            flux={sim.error ? undefined : flux.data}
            result={sim.error ? undefined : sim.result}
            magnetic={sim.magnetic.error ? undefined : sim.magnetic.result}
            image={(isMagneticKind(heatKind) ? sim.magnetic.error : sim.error) ? null : image}
            arrowScale={sim.error ? null : arrowScale}
            magneticArrowScale={sim.magnetic.error ? null : magneticArrowScale}
            ampere={ampere.data}
            induction={induction.data}
            lorentz={lorentz}
          />
          <Legend
            heat={(isMagneticKind(heatKind) ? sim.magnetic.error : sim.error) ? null : (image?.legend ?? null)}
            arrows={sim.error ? null : arrowScale}
            result={sim.error ? undefined : sim.result}
            flux={sim.error ? undefined : flux.data}
            magnetic={sim.magnetic.error ? undefined : sim.magnetic.result}
            magneticArrows={sim.magnetic.error ? null : magneticArrowScale}
          />
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="absolute right-3 top-3 w-80 max-w-[90%] rounded-lg bg-panel shadow-xl"
              >
                <SimulationError error={error} />
              </motion.div>
            )}
          </AnimatePresence>
          </div>
        </main>
        <Tabs.Root defaultValue="parameters" className="order-3 flex max-h-[45vh] w-full shrink-0 flex-col border-border bg-panel lg:max-h-none lg:w-80 lg:border-l">
          <Tabs.List aria-label={t('layout.panels')} className="flex flex-wrap border-b border-border">
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
            <Tabs.Content value="parameters"><ParametersPanel magnetic={sim.magnetic.error ? undefined : sim.magnetic.result} /></Tabs.Content>
            <Tabs.Content value="visualization"><VisualizationPanel sim={sim} /></Tabs.Content>
            <Tabs.Content value="gauss"><GaussPanel flux={flux.data} /></Tabs.Content>
            <Tabs.Content value="ampere"><AmperePanel ampere={ampere.data} stale={ampere.isStale} error={ampere.error} /></Tabs.Content>
            <Tabs.Content value="faraday"><FaradayPanel induction={induction.data} stale={induction.isStale} error={induction.error} /></Tabs.Content>
            <Tabs.Content value="lorentz"><LorentzPanel data={lorentz} /></Tabs.Content>
            <Tabs.Content value="equations"><EquationsPanel /></Tabs.Content>
            <Tabs.Content value="results"><ResultsPanel sim={sim} flux={flux.data} /></Tabs.Content>
          </div>
        </Tabs.Root>
      </div>
      <StatusBar sim={sim} />
    </div>
  )
}
