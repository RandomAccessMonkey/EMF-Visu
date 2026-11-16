import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Badge, Button, NumberField, Row, Section, Select, Slider, Switch } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { ARROW_DENSITIES, HEAT_RESOLUTION, LATTICE_DENSITIES, PLANE_BASIS, type SlicePlane } from '@/sim/request'
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
      <Section title={t('viz.vectors')}>
        <Row label={t('viz.arrows')} hint={t('viz.arrowsHint')}>
          <Switch label={t('viz.arrows')} checked={v.showArrows} onChange={set('showArrows')} />
        </Row>
        <Row label={t('viz.vectorField')} hint={t('viz.vectorFieldHint')}>
          <Select label={t('viz.vectorField')} value={v.vectorField} onChange={set('vectorField')} options={[
            { value: 'E', label: t('viz.vectorE') },
            { value: 'D', label: t('viz.vectorD') },
          ]} />
        </Row>
        <Row label={t('viz.arrowLength')} hint={t('viz.arrowLengthHint')}>
          <Select label={t('viz.arrowLength')} value={v.arrowLength} onChange={set('arrowLength')} options={[
            { value: 'uniform', label: t('viz.arrowUniform') },
            { value: 'log', label: t('viz.arrowLog') },
          ]} />
        </Row>
        <Row label={t('viz.arrowDensity')}>
          <Slider label={t('viz.arrowDensity')} value={ARROW_DENSITIES.indexOf(v.arrowDensity as (typeof ARROW_DENSITIES)[number])} min={0} max={ARROW_DENSITIES.length - 1} step={1} onChange={(i) => v.set({ arrowDensity: ARROW_DENSITIES[i]! })} />
          <span className="w-6 text-right font-mono text-[11px] text-muted">{v.arrowDensity}</span>
        </Row>
        <Row label={t('viz.arrowScale')}>
          <Slider label={t('viz.arrowScale')} value={v.arrowScale} min={0.3} max={2} step={0.1} onChange={set('arrowScale')} />
          <span className="w-6 text-right font-mono text-[11px] text-muted">{v.arrowScale.toFixed(1)}</span>
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('viz.arrowsHint')}</p>
      </Section>
      <Section title={t('viz.calculus')}>
        <Row label={t('viz.showCurl')} hint={t('viz.curlHint')}>
          <Switch label={t('viz.showCurl')} checked={v.showCurl} onChange={set('showCurl')} />
        </Row>
        <Row label={t('viz.curlField')}>
          <Select label={t('viz.curlField')} value={v.curlField} onChange={set('curlField')} options={[
            { value: 'E', label: t('viz.curlE') },
            { value: 'D', label: t('viz.curlD') },
          ]} />
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('viz.curlHint')}</p>
        <Row label={t('viz.sources')}>
          <Switch label={t('viz.sources')} checked={v.showSources} onChange={set('showSources')} />
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('viz.sourcesHint')}</p>
        <p className="text-[11px] leading-snug text-muted">{t('viz.divergenceHint')}</p>
      </Section>
      <Section title={t('viz.fieldLines')}>
        <Row label={t('viz.showFieldLines')}>
          <Switch label={t('viz.showFieldLines')} checked={v.showFieldLines} onChange={set('showFieldLines')} />
        </Row>
        <Row label={t('viz.lineDensity')}>
          <Slider label={t('viz.lineDensity')} value={v.lineDensity} min={0} max={2} step={1} onChange={set('lineDensity')} />
          <span className="w-6 text-right font-mono text-[11px] text-muted">{['×1', '×2', '×4'][v.lineDensity]}</span>
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t(v.mode === '2d' ? 'viz.fieldLinesHint2d' : 'viz.fieldLinesHint3d')}</p>
      </Section>
      <Section title={t('viz.equipotentials')}>
        <Row label={t('viz.contours')}>
          <Switch label={t('viz.contours')} checked={v.showContours} onChange={set('showContours')} />
        </Row>
        {v.mode === '3d' && (
          <Row label={t('viz.isosurfaces')}>
            <Switch label={t('viz.isosurfaces')} checked={v.showIsosurfaces} onChange={set('showIsosurfaces')} />
          </Row>
        )}
        <p className="text-[11px] leading-snug text-muted">{t('viz.equipotentialsHint')}</p>
      </Section>
      <Section title={t('viz.slice')}>
        <Row label={t('viz.heatmap')}>
          <Select label={t('viz.heatmap')} value={v.heatmap} onChange={set('heatmap')} options={[
            { value: 'phi', label: t('viz.heatPhi') },
            { value: 'E', label: t('viz.heatE') },
            { value: 'div_E', label: t('viz.heatDivE') },
            { value: 'curl_E', label: t('viz.heatCurlE') },
            { value: 'div_D', label: t('viz.heatDivD') },
            { value: 'curl_D', label: t('viz.heatCurlD') },
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
            <Slider label={t('viz.latticeDensity')} value={LATTICE_DENSITIES.indexOf(v.latticeDensity as (typeof LATTICE_DENSITIES)[number])} min={0} max={LATTICE_DENSITIES.length - 1} step={1} onChange={(i) => v.set({ latticeDensity: LATTICE_DENSITIES[i]! })} />
            <span className="w-6 text-right font-mono text-[11px] text-muted">{v.latticeDensity}³</span>
          </Row>
          <Row label={t('viz.volumeScalars')} hint={t('viz.volumeScalarsHint')}>
            <Switch label={t('viz.volumeScalars')} checked={v.showVolumeScalars} onChange={set('showVolumeScalars')} />
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
