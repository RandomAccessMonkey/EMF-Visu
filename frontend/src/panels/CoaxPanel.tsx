// Coaxial-cable TEM model: editor (geometry, dielectric, excitation, terminations, time and
// cross-section position), the transmission-line parameters, V/I with their wave components,
// the Poynting power check, the differential-law checks, the interface quantities and the probe.
// Every number shown is the engine's closed-form result (sim/coax.ts); edits are validated before
// any request is sent.
import { Cable, X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CoaxExcitation, CoaxLawCheck, CoaxSnapshot, CoaxSpec, CoaxTermination } from '@/api/types'
import { Badge, Button, NumberField, Row, Section, Segmented, Select, Slider, Switch } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatSI } from '@/lib/format'
import { DEFAULT_COAX, type CoaxData } from '@/sim/coax'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { SeriesPlot } from './CircuitsPanel'
import { COAX_E_COLOR, COAX_H_COLOR, COAX_S_COLOR } from '@/render/CoaxLayer'

const TERMS: CoaxTermination[] = ['matched', 'open', 'short']

function update(patch: (s: CoaxSpec) => CoaxSpec) {
  const s = useSceneStore.getState().coax
  if (s) useSceneStore.getState().setCoax(patch(s))
}

/** Open the coax model with the default cable and a time range that shows one reflection. */
export function openCoax() {
  useSceneStore.getState().setCoax(DEFAULT_COAX)
  useViewStore.getState().set({ timeStart: 0, timeEnd: 25e-9, timeStep: 0.1e-9, timeS: 7e-9, playing: false, mode: '3d', probePoint: null })
}

function Value({ label, children, hint }: { label: ReactNode; children: ReactNode; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs" title={hint}>
      <span className="text-muted">{label}</span>
      <span className="font-mono text-text">{children}</span>
    </div>
  )
}

function Editor({ spec }: { spec: CoaxSpec }) {
  const { t } = useT()
  const g = spec.geometry
  const m = spec.material
  const e = spec.excitation
  const geo = (k: keyof CoaxSpec['geometry']) => (x: number) => update((s) => ({ ...s, geometry: { ...s.geometry, [k]: x } }))
  const mat = (k: keyof CoaxSpec['material']) => (x: number) => update((s) => ({ ...s, material: { ...s.material, [k]: x } }))
  const exc = (patch: Partial<CoaxExcitation>) => update((s) => ({ ...s, excitation: { ...s.excitation, ...patch } as CoaxExcitation }))
  return (
    <>
      <Section title={t('coax.geometry')}>
        <Row label={t('coax.a')}><NumberField label={t('coax.a')} value={g.inner_radius_m} factor={1e-3} unit="mm" min={0} onChange={geo('inner_radius_m')} /></Row>
        <Row label={t('coax.b')}><NumberField label={t('coax.b')} value={g.shield_inner_radius_m} factor={1e-3} unit="mm" min={0} onChange={geo('shield_inner_radius_m')} /></Row>
        <Row label={t('coax.c')}><NumberField label={t('coax.c')} value={g.shield_outer_radius_m} factor={1e-3} unit="mm" min={0} onChange={geo('shield_outer_radius_m')} /></Row>
        <Row label={t('coax.length')}><NumberField label={t('coax.length')} value={g.length_m} unit="m" min={0} onChange={geo('length_m')} /></Row>
        <Row label={t('coax.epsr')}><NumberField label={t('coax.epsr')} value={m.relative_permittivity} min={0} onChange={mat('relative_permittivity')} /></Row>
        <Row label={t('coax.mur')}><NumberField label={t('coax.mur')} value={m.relative_permeability} min={0} onChange={mat('relative_permeability')} /></Row>
      </Section>
      <Section title={t('coax.excitation')}>
        <Segmented<CoaxExcitation['type']>
          label={t('coax.excitation')}
          value={e.type}
          onChange={(type) =>
            update((s) => ({
              ...s,
              excitation: type === 'sinusoidal'
                ? { type, amplitude_V: s.excitation.amplitude_V, frequency_Hz: 100e6 }
                : { type, amplitude_V: s.excitation.amplitude_V, center_s: 2e-9, width_s: 0.5e-9 },
            }))
          }
          options={[{ value: 'sinusoidal', label: t('coax.sinusoidal') }, { value: 'gaussian', label: t('coax.gaussian') }]}
        />
        <Row label={t('coax.amplitude')}><NumberField label={t('coax.amplitude')} value={e.amplitude_V} unit="V" onChange={(x) => exc({ amplitude_V: x })} /></Row>
        {e.type === 'sinusoidal' ? (
          <Row label={t('coax.frequency')} hint={t('coax.sinHint')}><NumberField label={t('coax.frequency')} value={e.frequency_Hz} factor={1e6} unit="MHz" min={0} onChange={(x) => exc({ frequency_Hz: x })} /></Row>
        ) : (
          <>
            <Row label={t('coax.center')}><NumberField label={t('coax.center')} value={e.center_s} factor={1e-9} unit="ns" onChange={(x) => exc({ center_s: x })} /></Row>
            <Row label={t('coax.width')} hint={t('coax.widthHint')}><NumberField label={t('coax.width')} value={e.width_s} factor={1e-9} unit="ns" min={0} onChange={(x) => exc({ width_s: x })} /></Row>
          </>
        )}
        <p className="text-[10px] leading-snug text-muted">{t(e.type === 'sinusoidal' ? 'coax.sinHint' : 'coax.widthHint')}</p>
      </Section>
      <Section title={t('coax.terminations')}>
        <Row label={t('coax.load')}>
          <Segmented<CoaxTermination> label={t('coax.load')} value={spec.load ?? 'matched'} onChange={(load) => update((s) => ({ ...s, load }))} options={TERMS.map((x) => ({ value: x, label: t(`coax.term.${x}`), title: t(`coax.gamma.${x}`) }))} />
        </Row>
        <Row label={t('coax.source')} hint={t('coax.sourceHint')}>
          <Select<CoaxTermination> label={t('coax.source')} value={spec.source ?? 'matched'} onChange={(source) => update((s) => ({ ...s, source }))} options={TERMS.map((x) => ({ value: x, label: t(`coax.src.${x}`) }))} />
        </Row>
        <p className="text-[10px] leading-snug text-muted">{t(`coax.termNote.${spec.load ?? 'matched'}`)}</p>
      </Section>
    </>
  )
}

function TimeAndPosition({ spec, z }: { spec: CoaxSpec; z: number }) {
  const { t } = useT()
  const v = useViewStore()
  const L = spec.geometry.length_m
  return (
    <Section title={t('coax.timePos')}>
      <Row label={t('time.start')}><NumberField label={t('time.start')} value={v.timeStart} factor={1e-9} unit="ns" onChange={(x) => v.set({ timeStart: x, timeS: Math.max(x, v.timeS) })} /></Row>
      <Row label={t('time.end')}><NumberField label={t('time.end')} value={v.timeEnd} factor={1e-9} unit="ns" onChange={(x) => v.set({ timeEnd: x, timeS: Math.min(x, v.timeS) })} /></Row>
      <Row label={t('time.step')}><NumberField label={t('time.step')} value={v.timeStep} factor={1e-9} unit="ns" min={1e-6} max={1e6} onChange={(x) => x > 0 && v.set({ timeStep: x })} /></Row>
      <Row label={t('coax.z')}>
        <Slider label={t('coax.z')} value={v.coaxZFraction} min={0} max={1} step={0.005} onChange={(x) => v.set({ coaxZFraction: x })} />
        <NumberField label={t('coax.zValue')} value={z} unit="m" min={0} max={L} onChange={(x) => L > 0 && v.set({ coaxZFraction: x / L })} />
      </Row>
      <div className="flex flex-wrap gap-1">
        {([0, 0.5, 1] as const).map((f) => (
          <Button key={f} variant={v.coaxZFraction === f ? 'primary' : 'ghost'} onClick={() => v.set({ coaxZFraction: f })}>
            {t(f === 0 ? 'coax.atSource' : f === 1 ? 'coax.atLoad' : 'coax.atMiddle')}
          </Button>
        ))}
      </div>
    </Section>
  )
}

function Layers() {
  const { t } = useT()
  const v = useViewStore()
  const items: [keyof typeof v, MessageKey, string][] = [
    ['showArrows', 'coax.layer.E', COAX_E_COLOR],
    ['showBArrows', 'coax.layer.H', COAX_H_COLOR],
    ['showFieldLines', 'coax.layer.Elines', COAX_E_COLOR],
    ['showBLines', 'coax.layer.Hlines', COAX_H_COLOR],
    ['coaxShowPoynting', 'coax.layer.S', COAX_S_COLOR],
  ]
  return (
    <Section title={t('coax.layers')}>
      <Segmented<'2d' | '3d'> label={t('coax.view')} value={v.mode} onChange={(mode) => v.set({ mode })} options={[{ value: '2d', label: t('coax.view2d') }, { value: '3d', label: t('coax.view3d') }]} />
      {items.map(([key, label, color]) => (
        <Row key={key} label={t(label)}>
          <span className="h-2 w-2 rounded-full" style={{ background: color }} />
          <Switch label={t(label)} checked={v[key] as boolean} onChange={(x) => v.set({ [key]: x })} />
        </Row>
      ))}
      <p className="text-[10px] leading-snug text-muted">{t('coax.layerNote')}</p>
    </Section>
  )
}

function Parameters({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  const p = d.params
  return (
    <Section title={t('coax.params')}>
      <Value label="L′">{formatSI(p.L_per_m_H, 'H/m', 4)}</Value>
      <Value label="C′">{formatSI(p.C_per_m_F, 'F/m', 4)}</Value>
      <Value label="Z₀">{formatSI(p.Z0_ohm, 'Ω', 4)}</Value>
      <Value label="v_p">{formatSI(p.vp_m_per_s, 'm/s', 4)} ({(p.vp_over_c * 100).toFixed(1)} % c)</Value>
      <Value label="t_delay">{formatSI(p.delay_s, 's', 4)}</Value>
      <Value label="Γ_L / Γ_S">{p.gamma_load.toFixed(0)} / {p.gamma_source.toFixed(0)}</Value>
      <Value label={t('coax.te11')} hint={t('coax.te11Hint')}>{formatSI(p.te11_cutoff_Hz, 'Hz', 3)}</Value>
      {d.warnings.includes('above_te11_cutoff') && <p className="text-xs text-warn">{t('coax.warnTe11')}</p>}
    </Section>
  )
}

function Waves({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  return (
    <Section title={t('coax.atZ', { z: formatSI(d.z_m, 'm', 3), t: formatSI(d.t_s, 's', 3) })}>
      <Value label="V = V⁺ + V⁻">{formatSI(d.V, 'V', 4)}</Value>
      <Value label="V⁺ / V⁻">{formatSI(d.Vf, 'V', 3)} / {formatSI(d.Vb, 'V', 3)}</Value>
      <Value label="I = (V⁺ − V⁻)/Z₀">{formatSI(d.I, 'A', 4)}</Value>
      <Value label="I⁺ / I⁻">{formatSI(d.If, 'A', 3)} / {formatSI(d.Ib, 'A', 3)}</Value>
      <Value label="P = V·I">{formatSI(d.V * d.I, 'W', 4)}</Value>
      <p className="text-[10px] leading-snug text-muted">{t('coax.waveNote')}</p>
    </Section>
  )
}

function Power({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  const pw = d.power
  const ok = pw.rel_error === null || pw.rel_error < 1e-6
  return (
    <Section title={t('coax.power')} aside={<Badge tone={ok ? 'ok' : 'warn'}>{pw.rel_error === null ? t('coax.zeroPower') : `δ = ${pw.rel_error.toExponential(1)}`}</Badge>}>
      <Value label="∬ S·dA">{formatSI(pw.P_poynting_W, 'W', 6)}</Value>
      <Value label="V·I">{formatSI(pw.P_VI_W, 'W', 6)}</Value>
      <Value label={t('coax.direction')}>{pw.P_VI_W > 0 ? t('coax.towardLoad') : pw.P_VI_W < 0 ? t('coax.towardSource') : '—'}</Value>
      <p className="text-[10px] leading-snug text-muted">{t('coax.powerNote', { nr: pw.nodes[0], nphi: pw.nodes[1] })}</p>
    </Section>
  )
}

function CheckRow({ c }: { c: CoaxLawCheck }) {
  const { t } = useT()
  const tone = c.status === 'agree' ? 'ok' : c.status === 'nonsmooth' ? 'warn' : 'muted'
  const name = t(`coax.law.${c.id}` as MessageKey)
  return (
    <div className="rounded border border-border px-2 py-1 text-[11px]">
      <div className="flex items-center justify-between">
        <span>{name}{c.component ? ` (${c.component})` : ''}</span>
        <Badge tone={tone}>{t(`coax.status.${c.status}` as MessageKey)}</Badge>
      </div>
      <div className="font-mono text-[10px] text-muted">
        {t('coax.lhs')}: {formatSI(c.lhs.analytic, c.unit, 4)} · FD {formatSI(c.lhs.numerical, c.unit, 4)}
        <br />
        {t('coax.rhs')}: {formatSI(c.rhs.analytic, c.unit, 4)} · FD {formatSI(c.rhs.numerical, c.unit, 4)}
        <br />
        {t('coax.residual')} {c.residual.toExponential(1)} · {t('coax.fdError')} {c.fd_rel_error.toExponential(1)}
      </div>
    </div>
  )
}

function Calculus({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  const c = d.calculus
  return (
    <Section title={t('coax.calculus')}>
      <p className="text-[10px] leading-snug text-muted">{t('coax.calcPoint', { r: formatSI(c.r_m, 'm', 3), z: formatSI(c.point_m[2], 'm', 3) })}</p>
      <Value label="∇·D (= ρ_free = 0)" hint={t('coax.divHint')}>{formatSI(c.div_D, 'C/m^3', 2)}</Value>
      <Value label="∇·B (= 0)">{formatSI(c.div_B, 'T/m', 2)}</Value>
      <p className="text-[10px] leading-snug text-muted">{t('coax.divScale', { d: formatSI(c.div_scale, 'C/m^3', 2), b: formatSI(c.div_B_scale, 'T/m', 2) })}</p>
      {c.checks.map((k, i) => <CheckRow key={`${k.id}-${k.component}-${i}`} c={k} />)}
      {c.telegrapher.map((k) => <CheckRow key={k.id} c={k} />)}
      <p className="text-[10px] leading-snug text-muted">{t('coax.calcNote')}</p>
    </Section>
  )
}

function Boundary({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  const b = d.boundary
  return (
    <Section title={t('coax.boundary')}>
      <Value label="ρ_s(a)">{formatSI(b.rho_s_inner_C_per_m2, 'C/m^2', 4)}</Value>
      <Value label="ρ_s(b)">{formatSI(b.rho_s_shield_C_per_m2, 'C/m^2', 4)}</Value>
      <Value label="K_z(a)">{formatSI(b.K_z_inner_A_per_m, 'A/m', 4)}</Value>
      <Value label="K_z(b)">{formatSI(b.K_z_shield_A_per_m, 'A/m', 4)}</Value>
      <Value label="Q′ = C′V">{formatSI(b.Q_per_m_C, 'C/m', 4)}</Value>
      <p className="text-[10px] leading-snug text-muted">{t('coax.boundaryNote')}</p>
    </Section>
  )
}

const vec = (v: number[], unit: string) => `(${v.map((x) => formatSI(x, unit, 3)).join(', ')})`

function ProbeView({ d }: { d: CoaxSnapshot }) {
  const { t } = useT()
  const mode = useViewStore((s) => s.mode)
  const p = d.probe
  return (
    <Section title={t('coax.probe')}>
      {!p ? (
        <p className="text-[11px] text-muted">{t(mode === '2d' ? 'coax.probeHint' : 'coax.probe2d')}</p>
      ) : (
        <>
          <Value label="r, φ">{formatSI(p.r_m, 'm', 4)}, {((p.phi_rad * 180) / Math.PI).toFixed(1)}°</Value>
          <Value label={t('coax.region')}><Badge tone={p.region === 'dielectric' ? 'accent' : p.region.endsWith('surface') ? 'warn' : 'muted'}>{t(`coax.region.${p.region}` as MessageKey)}</Badge></Value>
          <Value label="E">{vec(p.E, 'V/m')}</Value>
          <Value label="D">{vec(p.D, 'C/m^2')}</Value>
          <Value label="H">{vec(p.H, 'A/m')}</Value>
          <Value label="B">{vec(p.B, 'T')}</Value>
          <Value label="S = E × H">{vec(p.S, 'W/m^2')}</Value>
          <Value label="w_e / w_m">{formatSI(p.w_e_J_per_m3, 'J/m^3', 3)} / {formatSI(p.w_m_J_per_m3, 'J/m^3', 3)}</Value>
          {p.surface_charge_C_per_m2 !== null && p.surface_charge_C_per_m2 !== undefined && (
            <>
              <Value label="ρ_s">{formatSI(p.surface_charge_C_per_m2, 'C/m^2', 4)}</Value>
              <Value label="K_z">{formatSI(p.surface_current_A_per_m ?? 0, 'A/m', 4)}</Value>
              <p className="text-[10px] leading-snug text-warn">{t('coax.surfaceNote')}</p>
            </>
          )}
          {(p.region === 'inner_conductor' || p.region === 'shield' || p.region === 'outside') && <p className="text-[10px] text-muted">{t('coax.zeroRegion')}</p>}
        </>
      )}
    </Section>
  )
}

function Plots({ coax }: { coax: CoaxData }) {
  const { t } = useT()
  const d = coax.data!
  const tr = coax.trace
  const z0 = d.params.Z0_ohm
  return (
    <Section title={t('coax.plots')}>
      <SeriesPlot t={d.line.z_m} now={d.z_m} title={t('coax.plotLine')} unit="V" lines={[
        { label: 'V(z)', color: '#f87171', values: d.line.V },
        { label: 'Z₀·I(z)', color: '#60a5fa', values: d.line.I.map((i) => i * z0) },
        { label: 'V⁺', color: '#fde68a', values: d.line.Vf },
        { label: 'V⁻', color: '#a5b4fc', values: d.line.Vb },
      ]} />
      <p className="text-[10px] text-muted">{t('coax.plotLineAxis')}</p>
      {tr && (
        <SeriesPlot t={tr.t_s} now={d.t_s} title={t('coax.plotTime', { z: formatSI(tr.z_m, 'm', 3) })} unit="V" lines={[
          { label: 'V(t)', color: '#f87171', values: tr.V },
          { label: 'Z₀·I(t)', color: '#60a5fa', values: tr.I.map((i) => i * z0) },
          { label: 'V(L, t)', color: '#a3e635', values: tr.V_load },
        ]} />
      )}
      {tr && <SeriesPlot t={tr.t_s} now={d.t_s} title={t('coax.plotPower')} unit="W" lines={[{ label: 'P = V·I', color: COAX_S_COLOR, values: tr.P_W }]} />}
    </Section>
  )
}

export function CoaxPanel({ coax }: { coax: CoaxData }) {
  const { t } = useT()
  const spec = coax.spec
  if (!spec) {
    return (
      <Section title={t('coax.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('coax.intro')}</p>
        <Button variant="primary" onClick={openCoax}>
          <Cable size={12} /> {t('coax.open')}
        </Button>
      </Section>
    )
  }
  const d = coax.data
  return (
    <div data-testid="coax-panel">
      <Section title={t('coax.title')} aside={<Button variant="ghost" size="sm" onClick={() => useSceneStore.getState().setCoax(null)}><X size={12} /> {t('coax.close')}</Button>}>
        <p className="text-[11px] leading-snug text-muted">{t('coax.assumptions')}</p>
        <p className="text-[11px] leading-snug text-muted">{t('coax.conventions')}</p>
        {coax.issues.length > 0 && (
          <ul className="flex flex-col gap-0.5" aria-label={t('coax.errors')} data-testid="coax-errors">
            {coax.issues.map((i) => <li key={i.key} className="text-xs text-danger">{t(i.key)}</li>)}
          </ul>
        )}
        {coax.error && <p className="text-xs text-danger">{coax.error.message}</p>}
      </Section>
      <Editor spec={spec} />
      <TimeAndPosition spec={spec} z={coax.z} />
      <Layers />
      {d && (
        <>
          <Parameters d={d} />
          <Waves d={d} />
          <Power d={d} />
          <Plots coax={coax} />
          <ProbeView d={d} />
          <Calculus d={d} />
          <Boundary d={d} />
        </>
      )}
    </div>
  )
}
