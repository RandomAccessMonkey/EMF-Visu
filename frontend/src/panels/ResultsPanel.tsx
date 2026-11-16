import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type React from 'react'
import { api, ApiError } from '@/api/client'
import type { MethodInfo } from '@/api/types'
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
          {probe.data && !probe.data.defined && (
            <p className="text-xs text-warn">{t('probe.undefined', { tol: probe.data.singular_tolerance_m.toExponential(1) })}</p>
          )}
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
          {probe.data?.defined && probe.data.contributions.length > 0 && (
            <div>
              <h4 className="mb-1 mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('probe.superposition')}</h4>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-left text-muted">
                    <th className="font-normal">{t('probe.source')}</th>
                    <th className="text-right font-normal">|Eᵢ|</th>
                    <th className="text-right font-normal">φᵢ</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {probe.data.contributions.map((c) => (
                    <tr key={c.object_id} className="border-t border-border/60">
                      <td className="max-w-24 truncate font-sans">{c.name} <span className="text-muted">({formatSI(c.charge_C, 'C')})</span></td>
                      <td className="text-right">{formatSI(c.E_magnitude_V_per_m, 'V/m', 4)}</td>
                      <td className="text-right">{formatSI(c.phi_V, 'V', 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-[11px] leading-snug text-muted">{t('probe.superpositionNote')}</p>
            </div>
          )}
          <p className="text-[11px] text-muted">{t('probe.exactNote')}</p>
        </>
      )}
    </Section>
  )
}

function Method({ title, method, extra }: { title: string; method: MethodInfo; extra?: React.ReactNode }) {
  const { t, loc } = useT()
  const advanced = useViewStore((s) => s.level === 'advanced')
  return (
    <div className="rounded-md border border-border bg-panel-2/50 p-2 text-xs">
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <span className="font-semibold">{title}</span>
        <Badge tone="warn">{t(`method.${method.kind}` as MessageKey)}</Badge>
      </div>
      <p className="leading-snug">{loc(method.description)}</p>
      {extra}
      {advanced && (
        <>
          <p className="mt-1 font-mono text-[11px] text-muted">{loc(method.name)}</p>
          <table className="mt-1 w-full text-[11px]">
            <tbody className="font-mono">
              {Object.entries(method.parameters).map(([k, v]) => (
                <tr key={k}>
                  <td className="text-muted">{k}</td>
                  <td className="text-right">{typeof v === 'number' ? (Number.isInteger(v) ? v : v.toExponential(2)) : v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-snug text-muted">
        {method.limitations.map((l, i) => (
          <li key={i}>{loc(l)}</li>
        ))}
      </ul>
    </div>
  )
}

/** Derived visualizations: how each was obtained, separately from the accuracy of the field. */
function DerivedProducts({ sim }: { sim: Simulation }) {
  const { t } = useT()
  const level = useViewStore((s) => s.lineDensity)
  const h = sim.result?.header
  if (!h || (!h.field_lines && !h.equipotentials && !h.isosurfaces)) return null
  const fl = h.field_lines
  const shown = fl ? fl.lines.filter((l) => l.level === Math.min(level, fl.levels - 1)) : []
  const counts = new Map<string, number>()
  for (const l of shown) {
    const key = `${l.start_reason}>${l.end_reason}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return (
    <Section title={t('derived.title')}>
      <p className="text-[11px] leading-snug text-muted">{t('derived.intro')}</p>
      {fl && (
        <Method
          title={t('derived.fieldLines')}
          method={fl.method}
          extra={
            <div className="mt-1">
              <table className="w-full text-[11px]" aria-label={t('derived.terminations')}>
                <thead>
                  <tr className="text-left text-muted">
                    <th className="font-normal">{t('derived.from')}</th>
                    <th className="font-normal">{t('derived.to')}</th>
                    <th className="text-right font-normal">{t('derived.count')}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...counts.entries()].map(([key, n]) => {
                    const [from, to] = key.split('>') as [string, string]
                    const numerical = ['max_length', 'integration_failure'].some((r) => r === from || r === to)
                    return (
                      <tr key={key} className={numerical ? 'text-warn' : ''}>
                        <td>{t(`end.${from}` as MessageKey)}</td>
                        <td>{t(`end.${to}` as MessageKey)}</td>
                        <td className="text-right font-mono">{n}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {shown.length === 0 && <p className="text-[11px] text-muted">{t('derived.noLines')}</p>}
              {fl.lines_stay_in_plane === false && <p className="mt-1 text-[11px] text-warn">{t('derived.leavePlane')}</p>}
            </div>
          }
        />
      )}
      {h.equipotentials && (
        <Method
          title={t('derived.contours')}
          method={h.equipotentials.method}
          extra={
            <p className="mt-1 font-mono text-[11px] text-muted">
              φ = {h.equipotentials.levels.filter((l) => l.count > 0).map((l) => formatSI(l.value_V, 'V', 2)).join(', ') || '—'}
            </p>
          }
        />
      )}
      {h.isosurfaces && (
        <Method
          title={t('derived.isosurfaces')}
          method={h.isosurfaces.method}
          extra={
            <p className="mt-1 font-mono text-[11px] text-muted">
              φ = {h.isosurfaces.levels.filter((l) => l.count > 0).map((l) => formatSI(l.value_V, 'V', 2)).join(', ') || '—'}
            </p>
          }
        />
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
      {!sim.error && <DerivedProducts sim={sim} />}
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
