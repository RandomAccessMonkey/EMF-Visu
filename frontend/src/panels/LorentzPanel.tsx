// Lorentz force on a test charge and its optional nonrelativistic trajectory (Phase 4B). The
// test charge's velocity v is its own laboratory-frame velocity, never a conductor velocity.
// Every number shown comes from the engine; unsupported values are shown as such, never as 0.
import type { TestCharge, TrajectoryResult, Vec3 } from '@/api/types'
import { Badge, Button, NumberField, Row, Section, Switch } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatPlain, formatSI } from '@/lib/format'
import type { LorentzData } from '@/sim/useLorentz'
import { DEFAULT_TEST_CHARGE, useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { VecRows } from './AmperePanel'

const E_CHARGE = 1.602176634e-19
const SPECIES: { key: 'proton' | 'electron' | 'alpha'; q: number; m: number }[] = [
  { key: 'proton', q: E_CHARGE, m: 1.67262192369e-27 },
  { key: 'electron', q: -E_CHARGE, m: 9.1093837015e-31 },
  { key: 'alpha', q: 2 * E_CHARGE, m: 6.6446573357e-27 },
]

const set = (patch: Partial<TestCharge>) => {
  const cur = useSceneStore.getState().testCharge ?? DEFAULT_TEST_CHARGE
  useSceneStore.getState().setTestCharge({ ...cur, ...patch })
}
const setTraj = (patch: Partial<TestCharge['trajectory']>) => {
  const cur = useSceneStore.getState().testCharge ?? DEFAULT_TEST_CHARGE
  useSceneStore.getState().setTestCharge({ ...cur, trajectory: { ...cur.trajectory, ...patch } })
}

const vecText = (v: number[] | null | undefined, unit: string) => (v ? `(${v.map((x) => formatSI(x, '', 4)).join(', ')}) ${unit}` : null)

function VecLine({ label, v, unit, missing }: { label: string; v: number[] | null | undefined; unit: string; missing: string }) {
  return (
    <tr>
      <td className="pr-2 text-muted">{label}</td>
      <td>{vecText(v, unit) ?? missing}</td>
    </tr>
  )
}

function Energy({ traj }: { traj: TrajectoryResult }) {
  const { t } = useT()
  const s = traj.samples
  if (s.length < 2) return null
  const W = 260
  const H = 60
  const t0 = s[0]!.t_s
  const t1 = s[s.length - 1]!.t_s
  const k = s.map((x) => x.kinetic_energy_J)
  const lo = Math.min(...k)
  const hi = Math.max(...k)
  const flat = hi - lo <= 1e-9 * Math.max(Math.abs(hi), 1e-300)
  const x = (v: number) => 4 + ((v - t0) / (t1 - t0 || 1)) * (W - 8)
  const y = (v: number) => (flat ? H / 2 : 4 + ((hi - v) / (hi - lo)) * (H - 8))
  const d = s.map((p, i) => `${i ? 'L' : 'M'}${x(p.t_s).toFixed(1)},${y(p.kinetic_energy_J).toFixed(1)}`).join('')
  return (
    <div>
      <svg width={W} height={H} role="img" aria-label={t('lorentz.energyPlot')} className="text-muted">
        <path d={d} fill="none" stroke="#fde047" strokeWidth={1.4} />
      </svg>
      <p className="text-[10px] text-muted">
        K: {formatSI(lo, 'J', 4)} … {formatSI(hi, 'J', 4)} {flat && `(${t('lorentz.energyConstant')})`}
      </p>
    </div>
  )
}

export function LorentzPanel({ data }: { data: LorentzData }) {
  const { t, loc } = useT()
  const tc = useSceneStore((s) => s.testCharge)
  const timeS = useViewStore((s) => s.timeS)
  const p = data.probe
  const traj = data.trajectory
  const cur = data.current
  const na = t('lorentz.unsupported')
  if (!tc) {
    return (
      <Section title={t('lorentz.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('lorentz.intro')}</p>
        <Button variant="primary" onClick={() => useSceneStore.getState().setTestCharge(DEFAULT_TEST_CHARGE)}>
          {t('lorentz.add')}
        </Button>
      </Section>
    )
  }
  return (
    <div>
      <Section title={t('lorentz.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('lorentz.intro')}</p>
        <Row label={t('lorentz.enabled')}>
          <Switch label={t('lorentz.enabled')} checked={tc.enabled} onChange={(v) => set({ enabled: v })} />
        </Row>
        <div className="flex flex-wrap gap-1" role="group" aria-label={t('lorentz.species')}>
          {SPECIES.map((sp) => (
            <Button key={sp.key} onClick={() => set({ charge_C: sp.q, mass_kg: sp.m })}>
              {t(`lorentz.sp.${sp.key}` as MessageKey)}
            </Button>
          ))}
          <Button variant="danger" onClick={() => useSceneStore.getState().setTestCharge(null)}>
            {t('lorentz.remove')}
          </Button>
        </div>
        <Row label="q" hint={t('lorentz.chargeHint')}>
          <NumberField label={t('lorentz.charge')} value={tc.charge_C} unit="C" step={1e-19} onChange={(v) => set({ charge_C: v })} />
        </Row>
        <Row label="m">
          <NumberField label={t('lorentz.mass')} value={tc.mass_kg} unit="kg" min={1e-40} step={1e-27} onChange={(v) => v > 0 && set({ mass_kg: v })} />
        </Row>
        <VecRows label={t('lorentz.position')} value={tc.position_m as Vec3} unit="m" step={0.01} onChange={(v) => set({ position_m: v })} />
        <VecRows label={t('lorentz.velocity')} value={tc.velocity_m_per_s as Vec3} unit="m/s" step={100} onChange={(v) => set({ velocity_m_per_s: v })} />
      </Section>
      {tc.enabled && (
        <Section title={t('lorentz.forceTitle')}>
          {data.probeError && <p className="text-xs text-danger">{data.probeError.message}</p>}
          {p && (
            <div className="flex flex-col gap-1 text-xs" data-testid="lorentz-result" aria-live="polite">
              <div className="flex items-center gap-2">
                <Badge tone={p.status === 'complete' ? 'ok' : p.status === 'partial' ? 'warn' : 'danger'}>{t(`lorentz.status.${p.status}` as MessageKey)}</Badge>
                <span className="font-mono text-[11px] text-muted">t = {formatPlain(p.time_s, 's', 6)}</span>
              </div>
              {p.status_reason && <p className="text-[11px] leading-snug text-warn/90">{loc(p.status_reason)}</p>}
              {p.warnings.map((w, i) => (
                <p key={i} className="text-[11px] text-warn/90">{loc(w)}</p>
              ))}
              <table className="w-full font-mono text-[11px]" aria-label={t('lorentz.forceTitle')}>
                <tbody>
                  <VecLine label="E_static" v={p.E_static_V_per_m} unit="V/m" missing={t('lorentz.singular')} />
                  <VecLine label="E_ind" v={p.E_ind_V_per_m} unit="V/m" missing={na} />
                  <VecLine label="B" v={p.B_T} unit="T" missing={t('lorentz.singular')} />
                  <VecLine label="F_E = qE" v={p.F_E_N} unit="N" missing={na} />
                  <VecLine label="F_B = qv×B" v={p.F_B_N} unit="N" missing={t('lorentz.singular')} />
                  <VecLine label="F" v={p.F_total_N} unit="N" missing={p.status === 'partial' ? t('lorentz.partial') : na} />
                  <tr><td className="pr-2 text-muted">|F|</td><td data-testid="force-magnitude">{p.F_total_magnitude_N == null ? '—' : formatSI(p.F_total_magnitude_N, 'N', 5)}</td></tr>
                  <tr><td className="pr-2 text-muted">P_E = qE·v</td><td>{p.power_E_W == null ? na : formatSI(p.power_E_W, 'W', 4)}</td></tr>
                  <tr><td className="pr-2 text-muted">P_B = q(v×B)·v</td><td>{p.power_B_W == null ? '—' : `${formatSI(p.power_B_W, 'W', 2)} (|·| ≤ ${formatSI(p.power_B_bound_W ?? 0, 'W', 1)})`}</td></tr>
                  <tr><td className="pr-2 text-muted">P</td><td>{p.power_total_W == null ? na : formatSI(p.power_total_W, 'W', 4)}</td></tr>
                </tbody>
              </table>
              <p className="text-[11px] leading-snug text-muted">{t('lorentz.noWork')}</p>
            </div>
          )}
        </Section>
      )}
      {tc.enabled && (
        <Section title={t('lorentz.trajTitle')}>
          <p className="text-[11px] leading-snug text-muted">{t('lorentz.trajIntro')}</p>
          <Row label={t('lorentz.trajEnabled')}>
            <Switch label={t('lorentz.trajEnabled')} checked={tc.trajectory.enabled} onChange={(v) => setTraj({ enabled: v })} />
          </Row>
          {tc.trajectory.enabled && (
            <>
              <Row label={t('lorentz.start')}>
                <NumberField label={t('lorentz.start')} value={tc.trajectory.start_s} unit="s" step={1e-6} onChange={(v) => v < tc.trajectory.end_s && setTraj({ start_s: v })} />
              </Row>
              <Row label={t('lorentz.end')}>
                <NumberField label={t('lorentz.end')} value={tc.trajectory.end_s} unit="s" step={1e-6} onChange={(v) => v > tc.trajectory.start_s && setTraj({ end_s: v })} />
              </Row>
              <Row label={t('lorentz.tolerance')} hint={t('lorentz.toleranceHint')}>
                <NumberField label={t('lorentz.tolerance')} value={tc.trajectory.tolerance} min={1e-5} max={0.5} step={0.005} onChange={(v) => setTraj({ tolerance: v })} />
              </Row>
              <Row label={t('lorentz.maxSteps')}>
                <NumberField label={t('lorentz.maxSteps')} value={tc.trajectory.max_steps} min={10} max={200000} step={1000} onChange={(v) => Number.isInteger(v) && setTraj({ max_steps: v })} />
              </Row>
              <Row label={t('lorentz.trail')}>
                <Switch label={t('lorentz.trail')} checked={tc.trajectory.show_trail} onChange={(v) => setTraj({ show_trail: v })} />
              </Row>
              <Row label={t('lorentz.forces')}>
                <Switch label={t('lorentz.forces')} checked={tc.trajectory.show_forces} onChange={(v) => setTraj({ show_forces: v })} />
              </Row>
              <Button
                onClick={() =>
                  useViewStore.getState().set({
                    timeStart: tc.trajectory.start_s,
                    timeEnd: tc.trajectory.end_s,
                    timeStep: (tc.trajectory.end_s - tc.trajectory.start_s) / 200,
                    timeS: tc.trajectory.start_s,
                    playing: false,
                  })
                }
              >
                {t('lorentz.useRange')}
              </Button>
              {data.trajectoryFetching && <p className="text-[11px] text-muted">{t('lorentz.computing')}</p>}
              {data.trajectoryError && <p className="text-xs text-danger">{data.trajectoryError.message}</p>}
              {traj && (
                <div className="flex flex-col gap-1 text-xs" data-testid="trajectory-result">
                  <div className="flex items-center gap-2">
                    <Badge tone={traj.status === 'completed' ? 'ok' : traj.status === 'max_steps' ? 'warn' : 'danger'}>{t(`lorentz.traj.${traj.status}` as MessageKey)}</Badge>
                    <span className="text-[11px] text-muted">{t('lorentz.steps', { n: traj.steps })}</span>
                  </div>
                  {traj.status_reason && <p className="text-[11px] leading-snug text-warn/90">{loc(traj.status_reason)}</p>}
                  {traj.warnings.map((w, i) => (
                    <p key={i} className="text-[11px] text-warn/90">{loc(w)}</p>
                  ))}
                  <table className="w-full font-mono text-[11px]" aria-label={t('lorentz.trajTitle')}>
                    <tbody>
                      {traj.gyrofrequency_rad_per_s != null && <tr><td className="pr-2 text-muted">ω_c</td><td>{formatSI(traj.gyrofrequency_rad_per_s, 'rad/s', 4)}</td></tr>}
                      {traj.gyroradius_m != null && <tr><td className="pr-2 text-muted">r_c</td><td>{formatSI(traj.gyroradius_m, 'm', 4)}</td></tr>}
                      {traj.gyroperiod_s != null && <tr><td className="pr-2 text-muted">T_c</td><td>{formatSI(traj.gyroperiod_s, 's', 4)}</td></tr>}
                      <tr><td className="pr-2 text-muted">ΔK/K</td><td data-testid="energy-change">{traj.energy_relative_change == null ? '—' : traj.energy_relative_change.toExponential(2)}</td></tr>
                      <tr><td className="pr-2 text-muted">|v|max/c</td><td>{traj.max_speed_fraction_c.toExponential(2)}</td></tr>
                      {cur && (
                        <>
                          <tr><td className="pr-2 text-muted">t_n</td><td>{formatSI(cur.t_s, 's', 6)} ({t('lorentz.sampleNote', { t: formatSI(timeS, 's', 4) })})</td></tr>
                          <tr><td className="pr-2 text-muted">r</td><td>{vecText(cur.position_m, 'm')}</td></tr>
                          <tr><td className="pr-2 text-muted">v</td><td>{vecText(cur.velocity_m_per_s, 'm/s')}</td></tr>
                          <tr><td className="pr-2 text-muted">|v|, K</td><td>{formatSI(cur.speed_m_per_s, 'm/s', 5)}, {formatSI(cur.kinetic_energy_J, 'J', 5)}</td></tr>
                        </>
                      )}
                    </tbody>
                  </table>
                  {traj.magnetic_only && <p className="text-[11px] text-muted">{t('lorentz.magneticOnly')}</p>}
                  <Energy traj={traj} />
                  <p className="text-[11px] leading-snug text-muted">{loc(traj.method)}</p>
                </div>
              )}
            </>
          )}
        </Section>
      )}
    </div>
  )
}
