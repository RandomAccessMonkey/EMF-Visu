import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Badge, Button, NumberField, Row, Section, Select, Slider, Switch } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { HEAT_RESOLUTION, PLANE_BASIS, type SlicePlane } from '@/sim/request'
import { useHighAccuracy, type Simulation } from '@/sim/useSimulation'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore, type ViewSettings } from '@/state/viewStore'

function Accuracy({ sim }: { sim: Simulation }) {
  const { t } = useT()
  const high = useHighAccuracy()
  const solvers = useQuery({ queryKey: ['solvers'], queryFn: api.solvers, refetchInterval: 10_000 })
  const solverId = sim.result?.header.solver_id
  const worker = solvers.data?.find((s) => s.descriptor.id === solverId)
  const online = worker?.queue_worker_online ?? false
  const running = high.status?.state === 'queued' || high.status?.state === 'running'
  const current = high.key === sim.highBundle.key
  return (
    <Section title={t('accuracy.title')} aside={<Badge tone={sim.source === 'high' ? 'accent' : 'muted'}>{t(sim.source === 'high' ? 'accuracy.high' : 'accuracy.interactive')}</Badge>}>
      <p className="text-[11px] leading-snug text-muted">
        {t('accuracy.explain', { preview: HEAT_RESOLUTION.preview, normal: HEAT_RESOLUTION.normal, high: HEAT_RESOLUTION.high })}
      </p>
      <div className="flex items-center gap-2">
        <Button variant="primary" disabled={!online || running || !sim.result} onClick={() => void high.run(sim.highBundle)}>
          {t('accuracy.run')}
        </Button>
        {running && (
          <Button variant="danger" onClick={() => void high.cancel()}>
            {t('accuracy.cancel')}
          </Button>
        )}
      </div>
      {!online && <p className="text-[11px] text-warn">{t('accuracy.workerOffline')}</p>}
      {running && current && (
        <div aria-live="polite">
          <div className="h-1.5 overflow-hidden rounded-full bg-border" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((high.status?.progress ?? 0) * 100)}>
            <div className="h-full bg-accent transition-[width]" style={{ width: `${(high.status?.progress ?? 0) * 100}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-muted">
            {t(high.status?.state === 'queued' ? 'accuracy.queued' : 'accuracy.running')} {Math.round((high.status?.progress ?? 0) * 100)}%
          </p>
        </div>
      )}
      {current && high.status?.state === 'cancelled' && <p className="text-[11px] text-warn">{t('accuracy.cancelled')}</p>}
      {current && high.error && <p className="text-[11px] text-danger">{t('accuracy.failed')}: {high.error}</p>}
    </Section>
  )
}

export function VisualizationPanel({ sim }: { sim: Simulation }) {
  const { t } = useT()
  const v = useViewStore()
  const domain = useSceneStore((s) => s.scene.domain)
  const advanced = v.level === 'advanced'
  const set = <K extends keyof ViewSettings>(key: K) => (value: ViewSettings[K]) => v.set({ [key]: value })
  const n = PLANE_BASIS[v.plane].nAxis
  const axisName = 'xyz'[n]!
  return (
    <div>
      <Section title={t('viz.electricField')}>
        <Row label={t('viz.arrows')} hint={t('viz.arrowsHint')}>
          <Switch label={t('viz.arrows')} checked={v.showArrows} onChange={set('showArrows')} />
        </Row>
        <Row label={t('viz.arrowLength')} hint={t('viz.arrowLengthHint')}>
          <Select label={t('viz.arrowLength')} value={v.arrowLength} onChange={set('arrowLength')} options={[
            { value: 'uniform', label: t('viz.arrowUniform') },
            { value: 'log', label: t('viz.arrowLog') },
          ]} />
        </Row>
        <Row label={t('viz.arrowDensity')}>
          <Slider label={t('viz.arrowDensity')} value={v.arrowDensity} min={7} max={41} step={2} onChange={set('arrowDensity')} />
          <span className="w-6 text-right font-mono text-[11px] text-muted">{v.arrowDensity}</span>
        </Row>
        <Row label={t('viz.arrowScale')}>
          <Slider label={t('viz.arrowScale')} value={v.arrowScale} min={0.3} max={2} step={0.1} onChange={set('arrowScale')} />
          <span className="w-6 text-right font-mono text-[11px] text-muted">{v.arrowScale.toFixed(1)}</span>
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('viz.arrowsHint')}</p>
      </Section>
      <Section title={t('viz.slice')}>
        <Row label={t('viz.heatmap')}>
          <Select label={t('viz.heatmap')} value={v.heatmap} onChange={set('heatmap')} options={[
            { value: 'phi', label: t('viz.heatPhi') },
            { value: 'E', label: t('viz.heatE') },
            { value: 'none', label: t('viz.heatNone') },
          ]} />
        </Row>
        <Row label={t('viz.plane')}>
          <Select<SlicePlane> label={t('viz.plane')} value={v.plane} onChange={(plane) => v.set({ plane, offset: 0 })} options={[
            { value: 'xy', label: t('viz.planeXY') },
            { value: 'xz', label: t('viz.planeXZ') },
            { value: 'yz', label: t('viz.planeYZ') },
          ]} />
        </Row>
        <Row label={t('viz.offset', { axis: axisName })}>
          <Slider label={t('viz.offset', { axis: axisName })} value={v.offset} min={domain.min_m[n]!} max={domain.max_m[n]!} step={0.05} onChange={set('offset')} />
          <NumberField label={t('viz.offset', { axis: axisName })} value={v.offset} unit="m" step={0.05} min={domain.min_m[n]} max={domain.max_m[n]} onChange={set('offset')} className="[&>input]:w-14" />
        </Row>
        <Row label={t('viz.grid')}>
          <Switch label={t('viz.grid')} checked={v.showGrid} onChange={set('showGrid')} />
        </Row>
      </Section>
      {v.mode === '3d' && (
        <Section title={t('viz.threeD')}>
          <Row label={t('viz.lattice')}>
            <Switch label={t('viz.lattice')} checked={v.showLattice} onChange={set('showLattice')} />
          </Row>
          <Row label={t('viz.latticeDensity')}>
            <Slider label={t('viz.latticeDensity')} value={v.latticeDensity} min={3} max={13} step={1} onChange={set('latticeDensity')} />
            <span className="w-6 text-right font-mono text-[11px] text-muted">{v.latticeDensity}³</span>
          </Row>
          <Row label={t('viz.sliceIn3d')}>
            <Switch label={t('viz.sliceIn3d')} checked={v.showSliceIn3d} onChange={set('showSliceIn3d')} />
          </Row>
        </Section>
      )}
      <Section title={t('viz.editing')}>
        <Row label={t('viz.snap')}>
          <Switch label={t('viz.snap')} checked={v.snap} onChange={set('snap')} />
          <NumberField label={t('viz.snapStep')} value={v.snapStep} unit="m" min={0.001} step={0.05} onChange={set('snapStep')} className="[&>input]:w-14" />
        </Row>
      </Section>
      {advanced && <Accuracy sim={sim} />}
    </div>
  )
}
