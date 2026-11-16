import { useT } from '@/i18n'
import { formatSI, prettyUnit } from '@/lib/format'
import { cssGradient, type LogScale } from '@/render/colormaps'
import type { Legend as LegendData } from '@/render/fieldImages'
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
export function Legend({ heat, arrows }: { heat: LegendData | null; arrows: LogScale | null }) {
  const { t } = useT()
  const v = useViewStore()
  return (
    <>
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-2 rounded-md border border-border bg-panel/85 p-2.5 backdrop-blur">
        {heat && v.heatmap !== 'none' && (v.mode === '2d' || v.showSliceIn3d) && (
          <Bar
            title={`${heat.symbol} [${prettyUnit(heat.unit)}]`}
            kind={heat.kind}
            note={t(heat.scale === 'symlog' ? 'legend.symlog' : 'legend.log')}
            ticks={heat.kind === 'diverging'
              ? [formatSI(heat.min, prettyUnit(heat.unit)), '0', formatSI(heat.max, prettyUnit(heat.unit))]
              : [formatSI(heat.min, prettyUnit(heat.unit)), formatSI(heat.max, prettyUnit(heat.unit))]}
          />
        )}
        {arrows && (v.showArrows || (v.mode === '3d' && v.showLattice)) && (
          <Bar
            title={`${t('legend.arrows')} |E| [V/m]`}
            kind="sequential"
            note={t('legend.log')}
            ticks={[formatSI(arrows.min, 'V/m'), formatSI(arrows.max, 'V/m')]}
          />
        )}
        <p className="max-w-56 text-[10px] leading-snug text-muted">
          {t(v.arrowLength === 'uniform' ? 'legend.aidUniform' : 'legend.aidLog')} {t('legend.aid')}
        </p>
        <p className="flex items-center gap-3 text-[10px] text-muted">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-positive" />q &gt; 0</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-negative" />q &lt; 0</span>
        </p>
      </div>
    </>
  )
}
