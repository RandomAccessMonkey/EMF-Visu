import { useT } from '@/i18n'
import { formatSI, prettyUnit } from '@/lib/format'
import { cssGradient, type LogScale } from '@/render/colormaps'
import type { Legend as LegendData } from '@/render/fieldImages'
import type { SimulationResult } from '@/api/container'
import { SOURCE_COLORS, ZERO_VECTOR_COLOR } from '@/render/CalculusLayers'
import { ZERO_CSS } from '@/render/fieldImages'
import { FIELD_LINE_COLOR, isNumericalEnd, LEVEL_COLORS, NUMERICAL_LINE_COLOR } from '@/render/FieldProducts'
import { PLANE_BASIS } from '@/sim/request'
import { useViewStore } from '@/state/viewStore'

function Bar({ title, kind, ticks, note }: { title: string; kind: 'sequential' | 'diverging'; ticks: string[]; note: string }) {
  return (
    <div className="w-56">
      <div className="mb-0.5 flex justify-between text-[11px]">
        <span className="font-semibold text-text">{title}</span>
        <span className="text-muted">{note}</span>
      </div>
      <div className="h-2 rounded-sm" style={{ background: cssGradient(kind) }} />
      <div className="mt-0.5 flex justify-between font-mono text-[10px] text-muted">
        {ticks.map((tick, i) => (
          <span key={i}>{tick}</span>
        ))}
      </div>
    </div>
  )
}

/** States what kind of view this is (2D cross-section of a 3D model, or 3D) and how to use it. */
export function ViewStatement() {
  const { t } = useT()
  const v = useViewStore()
  const axis = 'xyz'[PLANE_BASIS[v.plane].nAxis]!
  const where = `${axis} = ${v.offset.toFixed(2)} m`
  return (
    <div className="border-b border-border bg-panel/70 px-3 py-1.5 text-[11px] leading-snug text-muted">
      <span className="font-semibold text-text">{t(v.mode === '2d' ? 'view.crossSectionTitle' : 'view.3dTitle')}. </span>
      {t(v.mode === '2d' ? 'view.crossSection' : 'view.3d', { where })}{' '}
      <span className="text-accent/80">{t(v.mode === '2d' ? 'view.controls2d' : 'view.controls3d')}</span>
    </div>
  )
}

/** Overlay with the colour scales (with units) and a statement of which elements are
 *  visualization aids rather than physical quantities. */
const Swatch = ({ color, dashed }: { color: string; dashed?: boolean }) => (
  <span className="mr-1 inline-block w-4 align-middle" style={{ borderTop: `2px ${dashed ? 'dashed' : 'solid'} ${color}` }} />
)

export function Legend({ heat, arrows, result }: { heat: LegendData | null; arrows: LogScale | null; result: SimulationResult | undefined }) {
  const { t } = useT()
  const v = useViewStore()
  const lines = result?.header.field_lines
  const hasNumerical = !!lines?.lines.some((l) => l.level === v.lineDensity && isNumericalEnd(l))
  const unit = v.vectorField === 'E' ? 'V/m' : 'C/m²'
  const sliceShown = v.mode === '2d' || v.showSliceIn3d
  return (
    <>
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-2 rounded-md border border-border bg-panel/85 p-2.5 backdrop-blur">
        {heat && v.heatmap !== 'none' && (v.mode === '2d' || v.showSliceIn3d) && !heat.zeroAware && (
          <Bar
            title={`${heat.symbol} [${prettyUnit(heat.unit)}]`}
            kind={heat.kind}
            note={t(heat.scale === 'symlog' ? 'legend.symlog' : 'legend.log')}
            ticks={heat.kind === 'diverging'
              ? [formatSI(heat.min, prettyUnit(heat.unit)), '0', formatSI(heat.max, prettyUnit(heat.unit))]
              : [formatSI(heat.min, prettyUnit(heat.unit)), formatSI(heat.max, prettyUnit(heat.unit))]}
          />
        )}
        {heat?.zeroAware && v.heatmap !== 'none' && (v.mode === '2d' || v.showSliceIn3d || v.showVolumeScalars) && (
          <div className="w-56 text-[11px]" data-testid="zero-legend">
            <div className="mb-0.5 flex justify-between">
              <span className="font-semibold text-text">{heat.symbol} [{prettyUnit(heat.unit)}]</span>
              <span className="text-muted">{t('legend.exactAnalytical')}</span>
            </div>
            <p className="leading-snug text-muted">
              <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: ZERO_CSS }} />
              {t('legend.exactZero', { n: heat.zeroAware.exactZero })}
              {heat.zeroAware.nonzero > 0 && <> · {t('legend.nonzero', { n: heat.zeroAware.nonzero })}</>}
              {heat.zeroAware.undefined > 0 && <> · {t('legend.undefinedSamples', { n: heat.zeroAware.undefined })}</>}
            </p>
            <p className="mt-0.5 text-[10px] leading-snug text-muted">{t(heat.symbol.startsWith('∇·') ? 'legend.divNote' : 'legend.curlNote')}</p>
          </div>
        )}
        {arrows && (v.showArrows || (v.mode === '3d' && v.showLattice)) && (
          <Bar
            title={`${t('legend.arrows')} |${v.vectorField}| [${unit}]`}
            kind="sequential"
            note={t('legend.log')}
            ticks={[formatSI(arrows.min, unit), formatSI(arrows.max, unit)]}
          />
        )}
        {v.showFieldLines && lines && (
          <p className="max-w-56 text-[10px] leading-snug text-muted">
            <Swatch color={FIELD_LINE_COLOR} />
            {t('legend.fieldLines')}
            {hasNumerical && (
              <>
                <br />
                <Swatch color={NUMERICAL_LINE_COLOR} dashed />
                {t('legend.numericalEnd')}
              </>
            )}
          </p>
        )}
        {result?.header.equipotentials && ((v.showContours && sliceShown) || (v.mode === '3d' && v.showIsosurfaces)) && (
          <p className="max-w-56 text-[10px] leading-snug text-muted">
            {t('legend.equipotentials')}: <Swatch color={LEVEL_COLORS.positive} />φ &gt; 0 <Swatch color={LEVEL_COLORS.zero} />φ = 0 <Swatch color={LEVEL_COLORS.negative} />φ &lt; 0
          </p>
        )}
        <p className="max-w-56 text-[10px] leading-snug text-muted">
          {t(v.arrowLength === 'uniform' ? 'legend.aidUniform' : 'legend.aidLog')} {t('legend.aid')}
        </p>
        {v.showCurl && (
          <p className="max-w-56 text-[10px] leading-snug text-muted">
            <span className="mr-1 inline-block h-2 w-2 rounded-full border-2 align-middle" style={{ borderColor: ZERO_VECTOR_COLOR }} />
            {t('legend.zeroVector', { field: v.curlField })}
          </p>
        )}
        {v.showSources && (result?.header.point_sources.length ?? 0) > 0 && (
          <p className="max-w-56 text-[10px] leading-snug text-muted">
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border-2 align-middle" style={{ borderColor: SOURCE_COLORS.positive }} />
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-full border-2 align-middle" style={{ borderColor: SOURCE_COLORS.negative }} />
            {t(v.mode === '2d' ? 'legend.sources2d' : 'legend.sources3d')}
          </p>
        )}
        <p className="flex items-center gap-3 text-[10px] text-muted">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-positive" />q &gt; 0</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-negative" />q &lt; 0</span>
        </p>
      </div>
    </>
  )
}
