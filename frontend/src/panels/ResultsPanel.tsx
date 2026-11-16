import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, ApiError } from '@/api/client'
import { Badge, Button, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatSI, prettyUnit } from '@/lib/format'
import { scenePhysics } from '@/sim/request'
import type { Simulation } from '@/sim/useSimulation'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

export function SimulationError({ error }: { error: Error }) {
  const { t, loc } = useT()
  const body = error instanceof ApiError ? error.body : null
  const unsupported = body?.code === 'unsupported'
  return (
    <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-2 text-xs">
      <p className="font-semibold text-danger">{t(unsupported ? 'results.unsupported' : 'results.failed')}</p>
      {body?.reasons.length ? (
        <ul className="mt-1 list-disc space-y-1 pl-4">
          {body.reasons.map((r, i) => (
            <li key={i}>{loc(r)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 font-mono text-[11px]">{error.message}</p>
      )}
      {unsupported && <p className="mt-1 text-muted">{t('results.noApproximation')}</p>}
    </div>
  )
}

function Probe() {
  const { t } = useT()
  const scene = useSceneStore((s) => s.scene)
  const point = useViewStore((s) => s.probePoint)
  const dragging = useViewStore((s) => s.dragging)
  const tool = useViewStore((s) => s.tool)
  const key = useMemo(() => JSON.stringify(scenePhysics(scene)), [scene])
  const probe = useQuery({
    queryKey: ['probe', key, point],
    queryFn: ({ signal }) => api.probe(scene, point!, signal),
    enabled: point !== null && !dragging,
    placeholderData: keepPreviousData,
    retry: false,
  })
  return (
    <Section
      title={t('probe.title')}
      aside={point && <Button variant="ghost" onClick={() => useViewStore.getState().set({ probePoint: null })}>{t('probe.clear')}</Button>}
    >
      {!point ? (
        <p className="text-xs text-muted">{t(tool === 'probe' ? 'probe.clickHint' : 'probe.enableHint')}</p>
      ) : (
        <>
          <p className="font-mono text-[11px] text-muted">r = ({point.map((c) => c.toFixed(3)).join(', ')}) m</p>
          {probe.isError && <p className="text-xs text-danger">{probe.error.message}</p>}
          {probe.data && !probe.data.defined && <p className="text-xs text-warn">{t('probe.undefined')}</p>}
          {probe.data?.defined && (
            <table className="w-full text-xs">
              <tbody>
                {probe.data.values.map((v) => (
                  <tr key={v.quantity} className="border-t border-border/60 align-top">
                    <td className="w-10 py-1 font-semibold">{v.symbol}</td>
                    <td className="py-1 font-mono">
                      {Array.isArray(v.value) ? (
                        <>
                          <div>|{v.symbol}| = {formatSI(v.magnitude, prettyUnit(v.unit), 4)}</div>
                          <div className="text-[11px] text-muted">({v.value.map((c) => c.toExponential(3)).join(', ')}) {prettyUnit(v.unit)}</div>
                        </>
                      ) : (
                        formatSI(v.value, prettyUnit(v.unit), 5)
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="text-[11px] text-muted">{t('probe.exactNote')}</p>
        </>
      )}
    </Section>
  )
}

export function ResultsPanel({ sim }: { sim: Simulation }) {
  const { t, loc } = useT()
  const advanced = useViewStore((s) => s.level === 'advanced')
  const h = sim.result?.header
  return (
    <div>
      {sim.error && (
        <div className="border-b border-border p-3">
          <SimulationError error={sim.error} />
        </div>
      )}
      {h && !sim.error && (
        <>
          <Section title={t('results.model')}>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="ok">{t(`classification.${h.classification}` as MessageKey)}</Badge>
              <Badge tone="muted">{t(`solverKind.${h.solver_kind}` as MessageKey)}</Badge>
            </div>
            <p className="text-xs leading-snug">{loc(h.classification_note)}</p>
            {advanced && (
              <p className="font-mono text-[11px] text-muted">
                {h.solver_id} v{h.solver_version}
              </p>
            )}
          </Section>
          <Section title={t('results.assumptions')}>
            <ul className="list-disc space-y-1 pl-4 text-xs">
              {h.assumptions.map((a, i) => (
                <li key={i}>{loc(a)}</li>
              ))}
            </ul>
          </Section>
          {h.warnings.length > 0 && (
            <Section title={t('results.warnings')}>
              <ul className="list-disc space-y-1 pl-4 text-xs text-warn">
                {h.warnings.map((w, i) => (
                  <li key={i}>{loc(w)}</li>
                ))}
              </ul>
            </Section>
          )}
        </>
      )}
      <Probe />
      {advanced && h && sim.result && (
        <Section title={t('results.diagnostics')}>
          <table className="w-full text-[11px]">
            <tbody className="font-mono">
              <tr><td className="text-muted">{t('diag.quality')}</td><td className="text-right">{h.quality}</td></tr>
              <tr><td className="text-muted">{t('diag.compute')}</td><td className="text-right">{h.compute_time_ms.toFixed(2)} ms</td></tr>
              <tr><td className="text-muted">{t('diag.roundTrip')}</td><td className="text-right">{sim.result.roundTripMs.toFixed(1)} ms</td></tr>
              <tr><td className="text-muted">{t('diag.cache')}</td><td className="text-right">{sim.result.cache}</td></tr>
              <tr><td className="text-muted">{t('diag.payload')}</td><td className="text-right">{(sim.result.byteLength / 1024).toFixed(1)} kB</td></tr>
            </tbody>
          </table>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-left text-muted">
                <th className="font-normal">{t('diag.array')}</th>
                <th className="font-normal">{t('diag.shape')}</th>
                <th className="text-right font-normal">min … max</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {h.arrays.map((a) => (
                <tr key={a.name} className="border-t border-border/60">
                  <td>{a.name}</td>
                  <td>{a.shape.join('×')}</td>
                  <td className="text-right">
                    {a.stats.min?.toExponential(2) ?? '—'} … {a.stats.max?.toExponential(2) ?? '—'} {prettyUnit(a.unit)}
                    {a.stats.non_finite_count > 0 && <span className="text-warn"> ({a.stats.non_finite_count} {t('diag.undefined')})</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] leading-snug text-muted">{t('diag.note')}</p>
        </Section>
      )}
    </div>
  )
}
