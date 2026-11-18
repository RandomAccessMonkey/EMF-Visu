import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '@/api/client'
import type { EquationStatus, EquationView } from '@/api/types'
import { Tex } from '@/components/Tex'
import { Badge, Dialog, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { prettyUnit } from '@/lib/format'
import { surfacePhysics } from '@/sim/gauss'
import { scenePhysics } from '@/sim/request'
import { pathPhysics, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const TONE: Record<EquationStatus, 'ok' | 'accent' | 'muted' | 'warn'> = {
  applicable: 'ok',
  applicable_under_assumptions: 'accent',
  not_applicable: 'muted',
  not_evaluated: 'warn',
}
const ORDER: EquationView['category'][] = ['electrostatics', 'maxwell', 'constitutive', 'magnetostatics', 'induction', 'motion', 'circuits', 'additional']

function Details({ eq }: { eq: EquationView }) {
  const { t, loc } = useT()
  const list = (title: MessageKey, items: EquationView['assumptions']) =>
    items.length > 0 && (
      <div>
        <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t(title)}</h4>
        <ul className="list-disc space-y-0.5 pl-4 text-xs">
          {items.map((a, i) => (
            <li key={i}>{loc(a)}</li>
          ))}
        </ul>
      </div>
    )
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="rounded-lg border border-border bg-bg px-3 py-4 text-center text-base">
        <Tex latex={eq.latex} block />
        {eq.latex_integral && (
          <div className="mt-2 border-t border-border pt-2">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t('eq.integralForm')}</p>
            <Tex latex={eq.latex_integral} block />
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={TONE[eq.status]}>{t(`eq.status.${eq.status}` as MessageKey)}</Badge>
        {eq.usage !== 'not_used' && <Badge tone={eq.usage === 'evaluated' ? 'accent' : eq.usage === 'checked' ? 'ok' : eq.usage === 'approximation' ? 'warn' : 'muted'}>{t(`eq.usage.${eq.usage}` as MessageKey)}</Badge>}
      </div>
      {eq.usage !== 'not_used' && <p className="text-xs text-muted">{loc(eq.usage_note)}</p>}
      {eq.status_reason && <p className="rounded-md border border-border bg-panel-2 p-2 text-xs">{loc(eq.status_reason)}</p>}
      <p>{loc(eq.meaning)}</p>
      <p className="text-xs italic text-text/80">{loc(eq.intuition)}</p>
      <div>
        <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('eq.symbols')}</h4>
        <table className="w-full text-xs">
          <tbody>
            {eq.symbols.map((s) => (
              <tr key={s.latex} className="border-t border-border/60">
                <td className="w-12 py-1"><Tex latex={s.latex} /></td>
                <td className="py-1">{loc(s.meaning)}</td>
                <td className="py-1 text-right font-mono text-muted">{s.unit === '1' ? '–' : prettyUnit(s.unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list('eq.assumptions', eq.assumptions)}
      {list('eq.conditions', eq.conditions)}
      {list('eq.limitations', eq.limitations)}
      {list('eq.derivation', eq.derivation)}
      {eq.used_by.length > 0 && (
        <p className="text-[11px] text-muted">
          {t('eq.implementedBy')}: <span className="font-mono">{eq.used_by.join(', ')}</span>
        </p>
      )}
    </div>
  )
}

export function EquationsPanel() {
  const { t, loc } = useT()
  const scene = useSceneStore((s) => s.scene)
  const surfaces = useSceneStore((s) => s.surfaces)
  const paths = useSceneStore((s) => s.paths)
  const fluxSurfaces = useSceneStore((s) => s.fluxSurfaces)
  const testCharge = useSceneStore((s) => s.testCharge)
  const circuits = useSceneStore((s) => s.circuits)
  const disks = useSceneStore((s) => s.eddyDisks)
  const dragging = useViewStore((s) => s.dragging)
  const beginner = useViewStore((s) => s.level === 'beginner')
  // Statuses depend on the physical model, not on where objects are: key on the physics subset.
  const key = useMemo(
    () => JSON.stringify({ scene: scenePhysics(scene), surfaces: surfaces.map(surfacePhysics), paths: paths.map(pathPhysics), flux: fluxSurfaces.map(pathPhysics), tc: testCharge ? { on: testCharge.enabled, traj: testCharge.trajectory.enabled } : null, c: circuits, d: disks }),
    [scene, surfaces, paths, fluxSurfaces, testCharge, circuits, disks],
  )
  const query = useQuery({
    queryKey: ['equations', key],
    queryFn: ({ signal }) => api.equations(scene, signal, surfaces.map(surfacePhysics), paths, fluxSurfaces, testCharge, circuits, disks),
    enabled: !dragging,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
  const [openId, setOpenId] = useState<string | null>(null)
  const data = query.data
  if (query.isError) return <p className="p-3 text-xs text-danger">{t('error.api')}</p>
  if (!data) return <p className="p-3 text-xs text-muted">{t('common.loading')}</p>
  if (!data.supported)
    return (
      <div className="p-3 text-xs">
        <p className="mb-2 font-semibold text-warn">{t('results.unsupported')}</p>
        <ul className="list-disc space-y-1 pl-4">
          {data.unsupported_reasons.map((r, i) => (
            <li key={i}>{loc(r)}</li>
          ))}
        </ul>
      </div>
    )
  const visible = data.equations.filter((e) => !beginner || e.status === 'applicable' || e.status === 'applicable_under_assumptions')
  const open = data.equations.find((e) => e.id === openId)
  return (
    <div>
      <p className="border-b border-border px-3 py-2 text-[11px] leading-snug text-muted">{t(beginner ? 'eq.introBeginner' : 'eq.intro')}</p>
      {ORDER.map((cat) => {
        const eqs = visible.filter((e) => e.category === cat)
        if (eqs.length === 0) return null
        return (
          <Section key={cat} title={t(`eq.category.${cat}` as MessageKey)}>
            {eqs.map((eq) => (
              <button
                key={eq.id}
                type="button"
                onClick={() => setOpenId(eq.id)}
                className="rounded-md border border-border bg-panel-2/60 p-2 text-left transition-colors hover:border-accent/50"
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <span className="text-xs font-medium">{loc(eq.name)}</span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <Badge tone={TONE[eq.status]}>{t(`eq.status.${eq.status}` as MessageKey)}</Badge>
                    {eq.usage !== 'not_used' && <Badge tone={eq.usage === 'evaluated' ? 'accent' : eq.usage === 'checked' ? 'ok' : eq.usage === 'approximation' ? 'warn' : 'muted'}>{t(`eq.usage.${eq.usage}` as MessageKey)}</Badge>}
                  </span>
                </div>
                <div className="overflow-x-auto py-1 text-[13px]">
                  <Tex latex={eq.latex} />
                </div>
                {eq.status_reason && <p className="mt-1 text-[11px] leading-snug text-muted">{loc(eq.status_reason)}</p>}
              </button>
            ))}
          </Section>
        )
      })}
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpenId(null)} title={open ? loc(open.name) : ''} closeLabel={t('common.close')}>
        {open && <Details eq={open} />}
      </Dialog>
    </div>
  )
}
