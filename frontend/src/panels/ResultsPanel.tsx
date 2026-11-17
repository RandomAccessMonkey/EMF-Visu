import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type React from 'react'
import { api, ApiError } from '@/api/client'
import type { CurrentSourceInfo, MethodInfo, ProbeMagnetic, ProbeValue, ResultHeader, Vec3 } from '@/api/types'
import { Badge, Button, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatNumber, formatSI, formatVector, prettyUnit } from '@/lib/format'
import { isTimeDependent, scenePhysics } from '@/sim/request'
import type { FluxData } from '@/sim/gauss'
import type { Simulation } from '@/sim/useSimulation'
import { AxisProfile } from './AxisProfile'
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

/** Same threshold as the engine's PRECISION_WARN: below it the float64 limit is not worth a note. */
const PRECISION_WARN = 1e-8

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
  // Phase 4A: the probe follows the simulation time of time-dependent scenes (0 otherwise, so
  // static scenes keep one cache entry).
  const timeS = useViewStore((s) => s.timeS)
  const probeTime = isTimeDependent(scene) ? timeS : 0
  const probe = useQuery({
    queryKey: ['probe', key, point, probeTime],
    queryFn: ({ signal }) => api.probe(scene, point!, signal, probeTime),
    enabled: point !== null && !dragging,
    placeholderData: keepPreviousData,
    retry: false,
  })
  // The engine's exact world position of the selected charge, so the probe can be placed on it.
  const selectedSource = sim.result?.header.point_sources.find((s) => s.object_id === selectedId)
  // A point on the selected wire's axis, or on the selected loop (from the engine's table).
  const selectedCurrent = sim.magnetic.result?.header.current_sources.find((s) => s.object_id === selectedId)
  const onCurrent: Vec3 | null = selectedCurrent ? sourcePoint(selectedCurrent) : null
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
      {onCurrent && (
        <Button onClick={() => useViewStore.getState().set({ probePoint: onCurrent })}>
          {t('probe.atCurrent')}
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
          {data?.magnetic && <h4 className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('probe.electricTitle')}</h4>}
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
          {data?.magnetic && <MagneticProbe m={data.magnetic} />}
          <p className="text-[11px] text-muted">{t('probe.exactNote')}</p>
        </>
      )}
    </Section>
  )
}

/** A point on the selected source where the probe shows its singular or boundary behaviour
 *  (geometry only): on a wire's axis, on a loop or the first turn of a coil or finite toroid,
 *  on a magnet's side wall (its current sheet). None for the ideal toroid. */
function sourcePoint(s: CurrentSourceInfo): Vec3 | null {
  if (s.kind === 'infinite_wire') return s.point_m as Vec3
  if (s.kind === 'toroid_ideal') return null
  const turn = s.turns_geometry[0]
  if (turn) return loopPoint(turn.center_m as Vec3, turn.normal as Vec3, turn.radius_m)
  return loopPoint(s.point_m as Vec3, s.direction as Vec3, s.radius_m ?? 0)
}

/** A point on a loop (geometry only): centre + radius × a unit vector perpendicular to n. */
function loopPoint(c: Vec3, n: Vec3, a: number): Vec3 {
  const ref: Vec3 = Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0]
  const e: Vec3 = [n[1] * ref[2] - n[2] * ref[1], n[2] * ref[0] - n[0] * ref[2], n[0] * ref[1] - n[1] * ref[0]]
  const l = Math.hypot(...e)
  return [c[0] + (a * e[0]) / l, c[1] + (a * e[1]) / l, c[2] + (a * e[2]) / l]
}

/** Magnetic part of the probe: B and H (separate quantities, units and roles), B = μ₀H, ∇·B,
 *  the nearest current source, and each source's own field. */
function MagneticProbe({ m }: { m: ProbeMagnetic }) {
  const { t } = useT()
  const vectors = m.values.filter((v) => !v.quantity.startsWith('div_'))
  const divs = m.values.filter((v) => v.quantity.startsWith('div_'))
  const nearest = m.contributions.find((c) => c.object_id === m.nearest_source_id)
  const singular = m.contributions.find((c) => c.object_id === m.singular_object_id)
  return (
    <div className="rounded-md border border-[#c084fc]/40 p-2" data-testid="magnetic-probe">
      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#c084fc]">{t('probe.magneticTitle')}</h4>
      {!m.defined && singular && (
        <div role="note" className="mb-1 rounded-md border border-warn/40 bg-warn/5 p-2 text-[11px] leading-snug">
          <p className="font-semibold text-warn">{t('probe.mSingularTitle')}</p>
          <p>{t(m.singular_kind === 'infinite_wire' ? 'probe.mSingularWire' : 'probe.mSingularLoop', { name: singular.name, i: formatSI(singular.current_A, 'A') })}</p>
          <p className="mt-1 text-muted">{t('probe.mSingularExplain')}</p>
        </div>
      )}
      {m.status !== 'defined' && m.status !== 'singular' && <BoundaryNote m={m} />}
      {!m.quadrature_converged && <p className="mb-1 text-[11px] text-warn">{t('probe.mNotConverged')}</p>}
      {m.relative_precision_bound != null && m.relative_precision_bound > PRECISION_WARN && (
        <p className="mb-1 text-[11px] leading-snug text-warn" data-testid="probe-precision">
          {t('probe.mPrecision', { bound: m.relative_precision_bound.toExponential(1) })}
        </p>
      )}
      <table className="w-full text-xs" aria-label={t('probe.magneticFields')}>
        <tbody>
          {vectors.map((v) => (
            <ProbeValueRow key={v.quantity} v={v} />
          ))}
          {divs.map((v) => (
            <ProbeValueRow key={v.quantity} v={v} />
          ))}
        </tbody>
      </table>
      {m.time_dependent && <TimeProbe m={m} />}
      <MaterialInfo m={m} />
      <p className="mt-1 font-mono text-[11px] text-muted">
        {m.constitutive === 'magnetization' ? 'H = B/μ₀ − M' : m.constitutive === 'linear_core' ? 'B = μ₀μᵣH' : 'B = μ₀H'}, μ₀ = {m.mu0_H_per_m.toExponential(10)} H/m
      </p>
      <p className="text-[11px] leading-snug text-muted">{t(m.defined ? 'probe.mDivNote' : 'probe.mDivSingularNote')}</p>
      {nearest && m.nearest_source_distance_m !== null && (
        <p className="mt-1 text-[11px]">
          {t('probe.nearestSource', { name: nearest.name, d: formatSI(m.nearest_source_distance_m, 'm', 4) })}
        </p>
      )}
      {m.contributions.length > 0 && (
        <>
          <h4 className="mb-1 mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('probe.mSuperposition')}</h4>
          <table className="w-full text-[11px]" aria-label={t('probe.mSuperposition')}>
            <thead>
              <tr className="text-left text-muted">
                <th className="font-normal">{t('probe.source')}</th>
                <th className="text-right font-normal">|Bᵢ|</th>
                <th className="text-right font-normal">|Hᵢ|</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {m.contributions.map((c) => (
                <tr key={c.object_id} className="border-t border-border/60 align-top">
                  <td className="max-w-28 font-sans">
                    <div className="truncate">
                      {c.name}{' '}
                      <span className="text-muted">
                        ({c.kind === 'permanent_magnet' ? `M = ${formatSI(c.magnetization_A_per_m ?? 0, 'A/m')}` : `${c.turns > 1 ? `${c.turns} × ` : ''}${formatSI(c.current_A, 'A')}`})
                      </span>
                    </div>
                    {c.B_T && <div className="text-[10px] text-muted">Bᵢ = {formatVector(c.B_T)} T</div>}
                  </td>
                  <td className="text-right">{c.B_magnitude_T === null ? t('probe.singular') : formatSI(c.B_magnitude_T, 'T', 4)}</td>
                  <td className="text-right">{c.H_magnitude_A_per_m === null ? t('probe.singular') : formatSI(c.H_magnitude_A_per_m, 'A/m', 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] leading-snug text-muted">{t('probe.mSuperpositionNote')}</p>
        </>
      )}
      <Comparisons m={m} />
    </div>
  )
}

/** Phase 4A: the simulation time, dB/dt and the induced field E_ind at the probe, and each
 *  source's current and its rate of change (all from the engine). */
function TimeProbe({ m }: { m: ProbeMagnetic }) {
  const { t } = useT()
  const objects = useSceneStore((s) => s.scene.objects)
  const names = useMemo(() => Object.fromEntries(objects.map((o) => [o.id, o.name || o.id])), [objects])
  const eByObject = new Map(m.contributions.map((c) => [c.object_id, c.E_ind_V_per_m]))
  return (
    <div className="mt-1 rounded-md border border-[#fb923c]/40 p-2" data-testid="probe-time">
      <p className="text-[11px] font-semibold text-[#fb923c]">{t('probe.timeTitle', { t: formatNumber(m.time_s, 6) })}</p>
      <table className="w-full text-xs" aria-label={t('probe.timeValues')}>
        <tbody>
          {m.time_values.map((v) => (
            <ProbeValueRow key={v.quantity} v={v} />
          ))}
        </tbody>
      </table>
      {!m.e_ind_available && <p className="text-[11px] leading-snug text-warn/90">{t('probe.eIndUnsupported')}</p>}
      {!m.derivative_unique && <p className="text-[11px] leading-snug text-warn/90">{t('faraday.corner')}</p>}
      <p className="text-[11px] leading-snug text-muted">{t('probe.eIndNote')}</p>
      <table className="mt-1 w-full text-[11px]" aria-label={t('probe.timeSources')}>
        <thead>
          <tr className="text-left text-muted">
            <th className="font-normal">{t('probe.source')}</th>
            <th className="text-right font-normal">I(t)</th>
            <th className="text-right font-normal">dI/dt</th>
            <th className="text-right font-normal">|E_ind,i|</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {m.time_sources.map((s) => {
            const e = eByObject.get(s.object_id)
            return (
              <tr key={s.object_id} className="border-t border-border/60">
                <td className="max-w-24 truncate font-sans">{names[s.object_id] ?? s.object_id}</td>
                <td className="text-right">{formatSI(s.current_A, 'A', 4)}</td>
                <td className="text-right">{formatSI(s.dI_dt_A_per_s, 'A/s', 4)}{s.derivative_unique ? '' : '*'}</td>
                <td className="text-right">{e ? formatSI(Math.hypot(...e), 'V/m', 4) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Where the probe is (vacuum, inside a magnet, inside the ideal core) and the material data
 *  used there, from the engine. */
function MaterialInfo({ m }: { m: ProbeMagnetic }) {
  const { t } = useT()
  if (m.material === 'vacuum' && !m.nearest_magnet_id) return null
  return (
    <div className="mt-1 text-[11px]">
      <p>
        {t('probe.mMaterial')}: <span className="font-semibold">{t(`probe.material.${m.material}` as MessageKey)}</span>
      </p>
      {m.M_A_per_m && <p className="font-mono">M = {formatVector(m.M_A_per_m)} A/m</p>}
      {m.relative_permeability !== null && m.relative_permeability !== undefined && <p className="font-mono">μᵣ = {formatNumber(m.relative_permeability, 6)}</p>}
      {m.nearest_magnet_boundary_m !== null && m.nearest_magnet_boundary_m !== undefined && (
        <p className="text-muted">{t('probe.mNearestBoundary', { d: formatSI(m.nearest_magnet_boundary_m, 'm', 4) })}</p>
      )}
    </div>
  )
}

/** On a magnet's current sheet, its end face or the ideal core surface the field has no single
 *  value: the engine reports the one-sided limits instead. */
function BoundaryNote({ m }: { m: ProbeMagnetic }) {
  const { t } = useT()
  return (
    <div role="note" className="mb-1 rounded-md border border-warn/40 bg-warn/5 p-2 text-[11px] leading-snug" data-testid="probe-boundary">
      <p className="font-semibold text-warn">{t(`probe.mStatus.${m.status}` as MessageKey)}</p>
      <p className="text-muted">{t(`probe.mStatusExplain.${m.status}` as MessageKey, { tol: formatSI(m.boundary_tolerance_m ?? 0, 'm', 2) })}</p>
      {m.one_sided.length > 0 && (
        <table className="mt-1 w-full font-mono text-[10px]" aria-label={t('probe.mOneSided')}>
          <thead>
            <tr className="text-left text-muted">
              <th className="font-sans font-normal">{t('probe.mSide')}</th>
              <th className="font-normal">B (T)</th>
              <th className="font-normal">H (A/m)</th>
            </tr>
          </thead>
          <tbody>
            {m.one_sided.map((o) => (
              <tr key={o.side} className="border-t border-border/60 align-top">
                <td className="font-sans">{t(`probe.side.${o.side}` as MessageKey)}</td>
                <td>{o.B_T ? formatVector(o.B_T) : '—'}</td>
                <td>{o.H_A_per_m ? formatVector(o.H_A_per_m) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

/** Idealized models evaluated at the probe point for comparison; never the solver's field. */
function Comparisons({ m }: { m: ProbeMagnetic }) {
  const { t, loc } = useT()
  if (m.comparisons.length === 0) return null
  return (
    <div className="mt-1" data-testid="probe-comparisons">
      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('probe.mComparisons')}</h4>
      {m.comparisons.map((c) => (
        <div key={`${c.object_id}:${c.kind}`} className="border-t border-border/60 py-1 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold">{t(`probe.comparison.${c.kind}` as MessageKey)}</span>
            <Badge tone={c.applicable ? 'muted' : 'warn'}>{t(c.applicable ? 'probe.cApplicable' : 'probe.cNotApplicable')}</Badge>
          </div>
          {c.B_T && <p className="font-mono">B = {formatVector(c.B_T)} T</p>}
          {c.H_A_per_m && <p className="font-mono">H = {formatVector(c.H_A_per_m)} A/m</p>}
          <p className="text-muted">{loc(c.note)}</p>
        </div>
      ))}
    </div>
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
function DerivedProducts({ header: h, title }: { header: ResultHeader | undefined; title: string }) {
  const { t } = useT()
  const level = useViewStore((s) => s.lineDensity)
  if (!h || (!h.field_lines && !h.equipotentials && !h.isosurfaces)) return null
  const fl = h.field_lines
  const shown = fl ? fl.lines.filter((l) => l.level === Math.min(level, fl.levels - 1)) : []
  const counts = new Map<string, number>()
  for (const l of shown) {
    const key = `${l.start_reason}>${l.end_reason}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return (
    <Section title={title}>
      <p className="text-[11px] leading-snug text-muted">{t('derived.intro')}</p>
      {fl && (
        <Method
          title={t(fl.field === 'B' ? 'derived.bLines' : 'derived.fieldLines')}
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
                    const numericalEnds = fl.field === 'B' ? ['max_length', 'integration_failure', 'source_singularity', 'stagnation_point'] : ['max_length', 'integration_failure']
                    const numerical = numericalEnds.some((r) => r === from || r === to)
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
              {shown.length === 0 && <p className="text-[11px] text-muted">{t(fl.field === 'B' ? 'derived.noBLines' : 'derived.noLines')}</p>}
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

/** Model, classification, assumptions and warnings of one result (electric or magnetic). */
function ModelSections({ h, title }: { h: ResultHeader; title: string }) {
  const { t, loc } = useT()
  const advanced = useViewStore((s) => s.level === 'advanced')
  return (
    <>
      <Section title={title}>
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
        <ul className="list-disc space-y-1 pl-4 text-xs">
          {h.assumptions.map((a, i) => (
            <li key={i}>{loc(a)}</li>
          ))}
        </ul>
        {h.warnings.length > 0 && (
          <ul className="list-disc space-y-1 pl-4 text-xs text-warn">
            {h.warnings.map((w, i) => (
              <li key={i}>{loc(w)}</li>
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}

export function ResultsPanel({ sim, flux }: { sim: Simulation; flux?: FluxData }) {
  const { t, loc } = useT()
  const advanced = useViewStore((s) => s.level === 'advanced')
  const h = sim.result?.header
  const selectedId = useSceneStore((s) => s.selectedId)
  const profiled = sim.magnetic.error
    ? undefined
    : sim.magnetic.result?.header.current_sources.find((c) => c.object_id === selectedId && (c.kind === 'solenoid' || c.kind === 'permanent_magnet'))
  return (
    <div>
      {!sim.error && <FluxResults flux={flux} />}
      {profiled && <AxisProfile key={profiled.object_id} info={profiled} />}
      {sim.error && (
        <div className="border-b border-border p-3">
          <SimulationError error={sim.error} />
        </div>
      )}
      {h && !sim.error && (
        <>
          <Section title={t(sim.magnetic.active ? 'results.electricModel' : 'results.model')}>
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
      {!sim.error && <DerivedProducts header={h} title={t('derived.title')} />}
      {sim.magnetic.error && (
        <div className="border-b border-border p-3">
          <SimulationError error={sim.magnetic.error} />
        </div>
      )}
      {sim.magnetic.result && !sim.magnetic.error && (
        <>
          <ModelSections h={sim.magnetic.result.header} title={t('results.magneticModel')} />
          <DerivedProducts header={sim.magnetic.result.header} title={t('derived.magneticTitle')} />
        </>
      )}
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
