import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type React from 'react'
import { api, ApiError } from '@/api/client'
import type { MethodInfo, ProbeValue, Vec3 } from '@/api/types'
import { Badge, Button, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatNumber, formatSI, formatVector, prettyUnit } from '@/lib/format'
import { scenePhysics } from '@/sim/request'
import type { FluxData } from '@/sim/gauss'
import type { Simulation } from '@/sim/useSimulation'
import { FluxResults } from './FluxResults'
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

const isCalculus = (q: string) => q.startsWith('div_') || q.startsWith('curl_')

function ProbeValueRow({ v }: { v: ProbeValue }) {
  const { t } = useT()
  const unit = prettyUnit(v.unit)
  let body: React.ReactNode
  if (v.status !== 'defined') {
    body = <span className="text-warn">{t(v.status === 'singular' ? 'probe.singular' : 'probe.notEvaluated')}</span>
  } else if (Array.isArray(v.value)) {
    body = (
      <>
        <div>
          |{v.symbol}| = {formatSI(v.magnitude, unit, 4)}
        </div>
        <div className="text-[11px] text-muted">
          {formatVector(v.value)} {unit}
        </div>
      </>
    )
  } else {
    body = formatSI(v.value, unit, 5)
  }
  return (
    <tr className="border-t border-border/60 align-top">
      <td className="w-12 py-1 font-semibold">
        {v.symbol}
        <div className="text-[9px] font-normal uppercase tracking-wide text-muted">{t(v.kind === 'vector' ? 'probe.vector' : 'probe.scalar')}</div>
      </td>
      <td className="py-1 font-mono">{body}</td>
    </tr>
  )
}

function Probe({ sim }: { sim: Simulation }) {
  const { t } = useT()
  const scene = useSceneStore((s) => s.scene)
  const selectedId = useSceneStore((s) => s.selectedId)
  const point = useViewStore((s) => s.probePoint)
  const dragging = useViewStore((s) => s.dragging)
  const tool = useViewStore((s) => s.tool)
  const advanced = useViewStore((s) => s.level === 'advanced')
  const key = useMemo(() => JSON.stringify(scenePhysics(scene)), [scene])
  const probe = useQuery({
    queryKey: ['probe', key, point],
    queryFn: ({ signal }) => api.probe(scene, point!, signal),
    enabled: point !== null && !dragging,
    placeholderData: keepPreviousData,
    retry: false,
  })
  // The engine's exact world position of the selected charge, so the probe can be placed on it.
  const selectedSource = sim.result?.header.point_sources.find((s) => s.object_id === selectedId)
  const data = probe.data
  const fieldValues = data?.values.filter((v) => !isCalculus(v.quantity)) ?? []
  const calculusValues = data?.values.filter((v) => isCalculus(v.quantity)) ?? []
  const dist = data?.distributional
  return (
    <Section
      title={t('probe.title')}
      aside={point && <Button variant="ghost" onClick={() => useViewStore.getState().set({ probePoint: null })}>{t('probe.clear')}</Button>}
    >
      {selectedSource && (
        <Button onClick={() => useViewStore.getState().set({ probePoint: selectedSource.position_m as Vec3 })}>
          {t('probe.atCharge')}
        </Button>
      )}
      {!point ? (
        <p className="text-xs text-muted">{t(tool === 'probe' ? 'probe.clickHint' : 'probe.enableHint')}</p>
      ) : (
        <>
          <p className="font-mono text-[11px] text-muted">r = ({point.map((c) => c.toFixed(3)).join(', ')}) m</p>
          {probe.isError && <p className="text-xs text-danger">{probe.error.message}</p>}
          {data && !data.defined && (
            <p className="text-xs text-warn">{t('probe.undefined', { tol: data.singular_tolerance_m.toExponential(1) })}</p>
          )}
          {data && (
            <table className="w-full text-xs" aria-label={t('probe.fields')}>
              <tbody>
                {fieldValues.map((v) => (
                  <ProbeValueRow key={v.quantity} v={v} />
                ))}
              </tbody>
            </table>
          )}
          {data && (
            <div>
              <h4 className="mb-1 mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('probe.calculus')}</h4>
              <table className="w-full text-xs" aria-label={t('probe.calculus')}>
                <tbody>
                  {calculusValues.map((v) => (
                    <ProbeValueRow key={v.quantity} v={v} />
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-[11px] leading-snug text-muted">{t(data.defined ? 'probe.calculusNote' : 'probe.calculusSingularNote')}</p>
            </div>
          )}
          {dist && (
            <div role="note" className="rounded-md border border-accent-2/40 bg-accent-2/5 p-2 text-[11px] leading-snug">
              <p className="font-semibold text-accent-2">{t('probe.distTitle')}</p>
              <p>{t('probe.distSource', { name: dist.name, q: formatSI(dist.charge_C, 'C') })}</p>
              <p className="font-mono">∇·E ∋ ({formatSI(dist.div_E_weight_V_m, 'V·m')}) · δ³(r − rᵢ)</p>
              <p className="font-mono">∇·D ∋ ({formatSI(dist.div_D_weight_C, 'C')}) · δ³(r − rᵢ)</p>
              <p className="font-mono">∇×E = {formatVector(dist.curl_E_distributional)} · ∇×D = {formatVector(dist.curl_D_distributional)}</p>
              <p className="mt-1 text-muted">{t('probe.distExplain')}</p>
            </div>
          )}
          {data?.defined && data.contributions.length > 0 && (
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
                  {data.contributions.map((c) => (
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
          {advanced && data?.defined && data.diagnostics.length > 0 && (
            <div className="rounded-md border border-warn/30 bg-warn/5 p-2">
              <div className="mb-1 flex items-center gap-1.5">
                <span className="text-[11px] font-semibold">{t('probe.diagTitle')}</span>
                <Badge tone="warn">{t('classification.numerical_approximation')}</Badge>
              </div>
              <table className="w-full text-[11px]" aria-label={t('probe.diagTitle')}>
                <tbody className="font-mono">
                  {data.diagnostics.map((d) => (
                    <tr key={d.quantity} className="border-t border-border/60 align-top">
                      <td className="w-10 py-0.5 font-sans font-semibold">{d.symbol}</td>
                      <td className="py-0.5">
                        {Array.isArray(d.estimate) && Array.isArray(d.uncertainty)
                          ? d.estimate.map((e, i) => (
                              <div key={i}>
                                {formatNumber(e, 3)} ± {formatNumber((d.uncertainty as number[])[i], 2)}
                              </div>
                            ))
                          : `${formatNumber(d.estimate as number, 3)} ± ${formatNumber(d.uncertainty as number, 2)}`}{' '}
                        <span className="text-muted">{prettyUnit(d.unit)}</span>
                      </td>
                      <td className={`py-0.5 text-right font-sans ${d.consistent_with_exact ? 'text-ok' : 'text-danger'}`}>
                        {t(d.consistent_with_exact ? 'probe.diagConsistent' : 'probe.diagInconsistent')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-[11px] leading-snug text-muted">{t('probe.diagNote', { h: formatNumber(data.diagnostics[0]!.step_m, 2) })}</p>
            </div>
          )}
          <p className="text-[11px] text-muted">{t('probe.exactNote')}</p>
        </>
      )}
    </Section>
  )
}

/** The distributional sources of the current model, with their exact delta weights. */
function Sources({ sim }: { sim: Simulation }) {
  const { t } = useT()
  const objects = useSceneStore((s) => s.scene.objects)
  const sources = sim.result?.header.point_sources ?? []
  const names = Object.fromEntries(objects.map((o) => [o.id, o.name || o.id]))
  return (
    <Section title={t('sources.title')}>
      <p className="text-[11px] leading-snug text-muted">{t('sources.intro')}</p>
      {sources.length === 0 ? (
        <p className="text-xs text-muted">{t('sources.none')}</p>
      ) : (
        <table className="w-full text-[11px]" aria-label={t('sources.title')}>
          <thead>
            <tr className="text-left text-muted">
              <th className="font-normal">{t('probe.source')}</th>
              <th className="text-right font-normal">∇·E: qᵢ/ε₀</th>
              <th className="text-right font-normal">∇·D: qᵢ</th>
              <th className="text-right font-normal">{t('sources.slice')}</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {sources.map((s) => (
              <tr key={s.object_id} className="border-t border-border/60">
                <td className="max-w-20 truncate font-sans">{names[s.object_id] ?? s.object_id}</td>
                <td className="text-right">{formatSI(s.div_E_weight_V_m, 'V·m')}</td>
                <td className="text-right">{formatSI(s.div_D_weight_C, 'C')}</td>
                <td className="text-right font-sans">{s.in_plane['heat'] ? t('sources.inSlice') : t('sources.offSlice', { d: formatSI(s.plane_distance_m['heat'] ?? 0, 'm') })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-[11px] leading-snug text-muted">{t('sources.curl')}</p>
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

export function ResultsPanel({ sim, flux }: { sim: Simulation; flux?: FluxData }) {
  const { t, loc } = useT()
  const advanced = useViewStore((s) => s.level === 'advanced')
  const h = sim.result?.header
  return (
    <div>
      {!sim.error && <FluxResults flux={flux} />}
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
      <Probe sim={sim} />
      {!sim.error && sim.result && <Sources sim={sim} />}
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
