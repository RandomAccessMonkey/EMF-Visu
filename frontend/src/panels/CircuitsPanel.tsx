// Passive conducting circuits and eddy-current disks (Phase 4C). Every current, EMF, force,
// power and energy shown comes from the engine's circuit solution (one solve over the playback
// grid); this panel only edits the inputs and formats the results of the current sample.
import { Circle, Disc, MoveHorizontal, Pentagon, Square, Trash2, Zap } from 'lucide-react'
import type { CircuitResult, EddyDisk, Electrical, FluxSurface, Mechanics, PassiveCircuit, Vec3 } from '@/api/types'
import { Badge, Button, NumberField, Row, Section, Select } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatSI } from '@/lib/format'
import type { CircuitsData } from '@/sim/useCircuits'
import { useSceneStore, type FluxKind } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { PathEditor, VecRows, type PathOps } from './AmperePanel'
import { MotionEditor, RodEditor } from './MotionEditor'

const DEG = Math.PI / 180
type Tone = 'ok' | 'warn' | 'muted' | 'danger' | 'accent'
const STATUS_TONE: Record<CircuitResult['status'], Tone> = {
  solved: 'ok',
  stopped: 'warn',
  invalid: 'danger',
  singular: 'warn',
  unsupported: 'muted',
  nonphysical: 'danger',
  failed: 'danger',
}
const KINDS: { kind: FluxKind; icon: typeof Circle }[] = [
  { kind: 'circle', icon: Circle },
  { kind: 'rectangle', icon: Square },
  { kind: 'polygon', icon: Pentagon },
  { kind: 'sliding_rod', icon: MoveHorizontal },
]
const MATERIALS = ['copper', 'aluminium', 'silver', 'custom'] as const

const store = () => useSceneStore.getState()
const vec = (v: number[] | null | undefined, unit: string) => (v ? `(${v.map((x) => formatSI(x, '', 3)).join(', ')}) ${unit}` : '—')

function ElectricalEditor({ c }: { c: PassiveCircuit }) {
  const { t } = useT()
  const e = c.electrical ?? ({} as Electrical)
  const set = (patch: Partial<Electrical>) => store().updateCircuit(c.id, { electrical: { ...e, ...patch } })
  const si = e.self_inductance ?? { mode: 'thin_loop' }
  const rod = c.path.shape.type === 'sliding_rod'
  return (
    <Section title={t('circ.electrical')}>
      <Row label={t('circ.material')} hint={t('circ.materialHint')}>
        <Select<(typeof MATERIALS)[number]>
          label={t('circ.material')}
          value={(e.material ?? 'copper') as (typeof MATERIALS)[number]}
          onChange={(m) => set(m === 'custom' ? { material: m, conductivity_S_per_m: 5.8e7, resistivity_ohm_m: null } : { material: m, conductivity_S_per_m: null, resistivity_ohm_m: null })}
          options={MATERIALS.map((m) => ({ value: m, label: t(`circ.mat.${m}` as MessageKey) }))}
        />
      </Row>
      {e.material === 'custom' && (
        <Row label="σ">
          <NumberField label={t('circ.conductivity')} value={e.conductivity_S_per_m ?? 5.8e7} unit="S/m" min={1e-12} step={1e6} onChange={(v) => v > 0 && set({ conductivity_S_per_m: v, resistivity_ohm_m: null })} />
        </Row>
      )}
      <Row label="r_w" hint={t('circ.wireHint')}>
        <NumberField label={t('circ.wireRadius')} value={e.wire_radius_m ?? 0.001} unit="m" min={1e-9} step={0.0001} onChange={(v) => v > 0 && set({ wire_radius_m: v, cross_section_m2: null })} />
      </Row>
      <Row label="R" hint={t(rod ? 'circ.resistanceRodHint' : 'circ.resistanceHint')}>
        <Select<'computed' | 'given'>
          label={t('circ.resistanceMode')}
          value={e.resistance_ohm != null ? 'given' : 'computed'}
          onChange={(m) => set({ resistance_ohm: m === 'given' ? 0.002 : null })}
          options={[
            { value: 'computed', label: t('circ.resComputed') },
            { value: 'given', label: t('circ.resGiven') },
          ]}
        />
        {e.resistance_ohm != null && <NumberField label={t('circ.resistance')} value={e.resistance_ohm} unit="Ω" min={1e-12} step={0.001} onChange={(v) => v > 0 && set({ resistance_ohm: v })} />}
      </Row>
      <Row label="ℒ" hint={t('circ.inductanceHint')}>
        <Select<'thin_loop' | 'user'>
          label={t('circ.inductanceMode')}
          value={si.mode ?? 'thin_loop'}
          onChange={(m) => set({ self_inductance: m === 'user' ? { mode: 'user', value_H: si.value_H ?? 1e-6 } : { mode: 'thin_loop' } })}
          options={[
            { value: 'thin_loop', label: t('circ.indThin') },
            { value: 'user', label: t('circ.indUser') },
          ]}
        />
        {si.mode === 'user' && <NumberField label={t('circ.inductance')} value={si.value_H ?? 1e-6} unit="H" min={1e-15} step={1e-7} onChange={(v) => v > 0 && set({ self_inductance: { mode: 'user', value_H: v } })} />}
      </Row>
      <Row label="I(0)">
        <NumberField label={t('circ.initialCurrent')} value={c.initial_current_A ?? 0} unit="A" step={0.1} onChange={(v) => store().updateCircuit(c.id, { initial_current_A: v })} />
      </Row>
    </Section>
  )
}

function MechanicsEditor({ c }: { c: PassiveCircuit }) {
  const { t } = useT()
  const m = c.mechanics ?? ({ mode: 'prescribed', mass_kg: 0.02, initial_velocity_m_per_s: 0.5, external_force_N: 0, damping_N_s_per_m: 0 } as Mechanics)
  const set = (patch: Partial<Mechanics>) => store().updateCircuit(c.id, { mechanics: { ...m, ...patch } })
  return (
    <Section title={t('circ.mechanics')}>
      <Row label={t('circ.mechMode')} hint={t('circ.mechHint')}>
        <Select<'prescribed' | 'dynamic'>
          label={t('circ.mechMode')}
          value={m.mode ?? 'prescribed'}
          onChange={(mode) => set({ mode })}
          options={[
            { value: 'prescribed', label: t('circ.prescribed') },
            { value: 'dynamic', label: t('circ.dynamic') },
          ]}
        />
      </Row>
      {m.mode === 'dynamic' && (
        <>
          <Row label="m"><NumberField label={t('circ.mass')} value={m.mass_kg ?? 0.02} unit="kg" min={1e-9} step={0.005} onChange={(v) => v > 0 && set({ mass_kg: v })} /></Row>
          <Row label="v₀"><NumberField label={t('circ.v0')} value={m.initial_velocity_m_per_s ?? 0} unit="m/s" step={0.1} onChange={(v) => set({ initial_velocity_m_per_s: v })} /></Row>
          <Row label="F_ext"><NumberField label={t('circ.fext')} value={m.external_force_N ?? 0} unit="N" step={0.001} onChange={(v) => set({ external_force_N: v })} /></Row>
          <Row label="b"><NumberField label={t('circ.damping')} value={m.damping_N_s_per_m ?? 0} unit="N·s/m" min={0} step={0.001} onChange={(v) => set({ damping_N_s_per_m: v })} /></Row>
        </>
      )}
    </Section>
  )
}

function CircuitEditor({ c }: { c: PassiveCircuit }) {
  const { t } = useT()
  const up = (patch: Partial<FluxSurface>) => store().updateCircuit(c.id, { path: { ...c.path, ...patch } })
  const ops: PathOps = { update: (_id, patch) => up(patch as Partial<FluxSurface>), setDisplay: () => undefined }
  return (
    <div data-testid="circuit-editor">
      <Row label={t('params.name')}>
        <input aria-label={t('circ.name')} value={c.name ?? ''} onChange={(e) => store().updateCircuit(c.id, { name: e.target.value })} className="h-7 w-36 rounded-md border border-border bg-bg px-1.5 text-xs" />
      </Row>
      {c.path.shape.type === 'sliding_rod' ? (
        <RodEditor f={c.path} onUpdate={up} title={t('circ.geometry')} />
      ) : (
        <>
          <PathEditor key={c.id} p={c.path as never} ops={ops} title={t('circ.geometry')} crossings={false} />
          <MotionEditor f={c.path} onUpdate={up} />
        </>
      )}
      <ElectricalEditor c={c} />
      {c.path.shape.type === 'sliding_rod' && <MechanicsEditor c={c} />}
    </div>
  )
}

function DiskEditor({ d }: { d: EddyDisk }) {
  const { t } = useT()
  const set = (patch: Partial<EddyDisk>) => store().updateDisk(d.id, patch)
  return (
    <Section title={t('circ.diskTitle', { name: d.name || d.id })}>
      <p className="text-[11px] leading-snug text-warn/90">{t('circ.diskApprox')}</p>
      <div className="flex flex-col gap-1.5" data-testid="disk-editor">
        <Row label="R"><NumberField label={t('circ.outerRadius')} value={d.outer_radius_m ?? 0.1} unit="m" min={1e-6} step={0.01} onChange={(v) => v > (d.inner_radius_m ?? 0) && set({ outer_radius_m: v })} /></Row>
        <Row label="R_in"><NumberField label={t('circ.innerRadius')} value={d.inner_radius_m ?? 0} unit="m" min={0} step={0.01} onChange={(v) => v >= 0 && v < (d.outer_radius_m ?? 0.1) && set({ inner_radius_m: v })} /></Row>
        <Row label="t"><NumberField label={t('circ.thickness')} value={d.thickness_m ?? 0.005} unit="m" min={1e-9} step={0.001} onChange={(v) => v > 0 && set({ thickness_m: v })} /></Row>
        <Row label="N_r" hint={t('circ.bandsHint')}><NumberField label={t('circ.bands')} value={d.bands ?? 20} min={2} max={200} step={1} onChange={(v) => Number.isInteger(v) && set({ bands: v })} /></Row>
        <Row label={t('circ.material')}>
          <Select<(typeof MATERIALS)[number]>
            label={t('circ.material')}
            value={(d.material ?? 'copper') as (typeof MATERIALS)[number]}
            onChange={(m) => set(m === 'custom' ? { material: m, conductivity_S_per_m: 5.8e7 } : { material: m, conductivity_S_per_m: null })}
            options={MATERIALS.map((m) => ({ value: m, label: t(`circ.mat.${m}` as MessageKey) }))}
          />
        </Row>
        {d.material === 'custom' && (
          <Row label="σ"><NumberField label={t('circ.conductivity')} value={d.conductivity_S_per_m ?? 5.8e7} unit="S/m" min={1e-12} step={1e6} onChange={(v) => v > 0 && set({ conductivity_S_per_m: v })} /></Row>
        )}
        <VecRows label={t('params.position')} value={d.center_m as Vec3} unit="m" step={0.01} onChange={(v) => set({ center_m: v })} />
        <VecRows label={t('params.rotation')} value={d.rotation_euler_xyz_rad as Vec3} unit="°" factor={DEG} step={15} onChange={(v) => set({ rotation_euler_xyz_rad: v })} />
      </div>
    </Section>
  )
}

// ------------------------------------------------------------------------------- results

interface Line {
  label: string
  color: string
  values: (number | null)[]
}

const W = 270
const H = 80

/** Time series of the solution (computed grid samples only). */
export function SeriesPlot({ t: times, lines, now, title, unit }: { t: number[]; lines: Line[]; now: number; title: string; unit: string }) {
  if (times.length < 2) return null
  const t0 = times[0]!
  const t1 = times[times.length - 1]!
  const vals = lines.flatMap((l) => l.values.filter((v): v is number => v !== null && Number.isFinite(v)))
  const hi = Math.max(1e-300, ...vals.map(Math.abs))
  const x = (v: number) => 4 + ((v - t0) / (t1 - t0 || 1)) * (W - 8)
  const y = (v: number) => H / 2 - (v / hi) * (H / 2 - 4)
  return (
    <figure className="mt-1">
      <figcaption className="text-[10px] text-muted">
        {title} (±{formatSI(hi, unit, 2)})
      </figcaption>
      <svg width={W} height={H} role="img" aria-label={title} className="text-muted">
        <line x1={4} x2={W - 4} y1={H / 2} y2={H / 2} stroke="currentColor" strokeWidth={0.5} />
        {lines.map((l) => {
          let first = true
          const d = l.values
            .map((v, i) => {
              if (v === null || !Number.isFinite(v)) {
                first = true
                return ''
              }
              const seg = `${first ? 'M' : 'L'}${x(times[i]!).toFixed(1)},${y(v).toFixed(1)}`
              first = false
              return seg
            })
            .join('')
          return <path key={l.label} d={d} fill="none" stroke={l.color} strokeWidth={1.3} />
        })}
        {now >= t0 && now <= t1 && <line x1={x(now)} x2={x(now)} y1={2} y2={H - 2} stroke="#22d3ee" strokeWidth={1} />}
      </svg>
      <div className="flex flex-wrap gap-x-2 text-[10px]">
        {lines.map((l) => (
          <span key={l.label} style={{ color: l.color }}>
            {l.label}
          </span>
        ))}
      </div>
    </figure>
  )
}

const COLORS = ['#f472b6', '#38bdf8', '#facc15', '#a3e635', '#fb923c', '#c084fc', '#22d3ee', '#f87171']

function Results({ data }: { data: CircuitsData }) {
  const { t, loc } = useT()
  const now = useViewStore((s) => s.timeS)
  const r = data.data
  if (!r) return null
  const s = r.series
  const k = data.k
  const circuits = r.elements.map((e, i) => ({ e, i })).filter(({ e }) => e.kind === 'circuit')
  const bands = r.elements.map((e, i) => ({ e, i })).filter(({ e }) => e.kind === 'band')
  return (
    <div className={cn('flex flex-col gap-1.5 text-xs', data.isStale && 'opacity-60')} data-testid="circuit-result" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[r.status]}>{t(`circ.status.${r.status}` as MessageKey)}</Badge>
        {s && k >= 0 && <span className="font-mono text-[11px] text-muted">t = {formatSI(s.t_s[k]!, 's', 6)}</span>}
        {data.isFetching && <span className="text-[11px] text-muted">{t('circ.solving')}</span>}
      </div>
      {r.status_reason && <p className="text-[11px] leading-snug text-warn/90">{loc(r.status_reason)}</p>}
      {r.problems.map((p, i) => (
        <p key={i} className="text-[11px] text-danger">{loc(p)}</p>
      ))}
      {r.warnings.map((w, i) => (
        <p key={`w${i}`} className="text-[11px] leading-snug text-muted">{loc(w)}</p>
      ))}
      {s && k >= 0 &&
        circuits.map(({ e, i }) => {
          const f = s.force_N[i]?.[k]
          const pm = s.mechanical_power_W[i]?.[k]
          const v = s.rod_velocity_m_per_s?.[k]
          const braking = f && v != null ? f[0]! * v < 0 : null
          return (
            <table key={e.id} className="w-full font-mono text-[11px]" aria-label={e.name} data-testid="circuit-table">
              <tbody>
                <tr><td colSpan={2} className="pt-1 font-sans font-semibold text-accent-2">{e.name}</td></tr>
                <tr><td className="pr-2 text-muted">I</td><td data-testid="circuit-current">{formatSI(s.current_A[i]![k]!, 'A', 5)}</td></tr>
                <tr><td className="pr-2 text-muted">dI/dt</td><td>{formatSI(s.dI_dt_A_per_s[i]![k]!, 'A/s', 4)}</td></tr>
                <tr><td className="pr-2 text-muted">R, ℒ</td><td>{formatSI(e.resistance_ohm, 'Ω', 4)}, {formatSI(e.self_inductance_H, 'H', 4)}{e.self_inductance_approximate ? ' ≈' : ''}</td></tr>
                <tr><td className="pr-2 text-muted">τ = ℒ/R</td><td>{formatSI(e.time_constant_s, 's', 3)}</td></tr>
                <tr><td className="pr-2 text-muted">λ</td><td>{formatSI(s.flux_linkage_Wb[i]![k]!, 'Wb', 5)}</td></tr>
                <tr><td className="pr-2 text-muted">Φ_ext</td><td>{formatSI(s.flux_external_Wb[i]![k]!, 'Wb', 5)}</td></tr>
                <tr><td className="pr-2 text-muted">{t('circ.emfTr')}</td><td>{formatSI(s.emf_transformer_V[i]![k]!, 'V', 4)}</td></tr>
                <tr><td className="pr-2 text-muted">{t('circ.emfMot')}</td><td>{formatSI(s.emf_motional_V[i]![k]!, 'V', 4)}</td></tr>
                <tr><td className="pr-2 text-muted">R I</td><td>{formatSI(s.resistive_drop_V[i]![k]!, 'V', 4)}</td></tr>
                <tr><td className="pr-2 text-muted">P_R = RI²</td><td>{formatSI(s.joule_power_W[i]![k]!, 'W', 4)}</td></tr>
                {f && <tr><td className="pr-2 text-muted">F_em</td><td data-testid="circuit-force">{vec(f, 'N')}</td></tr>}
                {pm != null && <tr><td className="pr-2 text-muted">P_mech = F·u</td><td>{formatSI(pm, 'W', 4)}</td></tr>}
                {s.rod_position_m && (
                  <tr><td className="pr-2 text-muted">x, v</td><td>{formatSI(s.rod_position_m[k]!, 'm', 5)}, {formatSI(v ?? 0, 'm/s', 6)}</td></tr>
                )}
                {braking !== null && (
                  <tr><td className="pr-2 text-muted">{t('circ.forceVsMotion')}</td><td data-testid="braking">{t(braking ? 'circ.opposes' : 'circ.notOpposing')}</td></tr>
                )}
              </tbody>
            </table>
          )
        })}
      {s && k >= 0 && (
        <table className="w-full font-mono text-[11px]" aria-label={t('circ.energy')} data-testid="energy-table">
          <tbody>
            <tr><td colSpan={2} className="pt-1 font-sans font-semibold text-accent-2">{t('circ.energy')}</td></tr>
            <tr><td className="pr-2 text-muted">W_m = ½IᵀLI</td><td>{formatSI(s.magnetic_energy_J[k]!, 'J', 5)}</td></tr>
            <tr><td className="pr-2 text-muted">Q_R</td><td>{formatSI(s.joule_heat_J[k]!, 'J', 5)}</td></tr>
            <tr><td className="pr-2 text-muted">{t('circ.sourceWork')}</td><td>{formatSI(s.source_work_J[k]!, 'J', 5)}</td></tr>
            {s.kinetic_energy_J && <tr><td className="pr-2 text-muted">K</td><td>{formatSI(s.kinetic_energy_J[k]!, 'J', 6)}</td></tr>}
            {s.external_work_J && <tr><td className="pr-2 text-muted">W_ext</td><td>{formatSI(s.external_work_J[k]!, 'J', 4)}</td></tr>}
            <tr><td className="pr-2 text-muted">{t('circ.residual')}</td><td data-testid="energy-residual">{formatSI(s.energy_residual_J[k]!, 'J', 2)}</td></tr>
          </tbody>
        </table>
      )}
      {r.matrix && r.matrix.ids.length <= 8 && (
        <div data-testid="inductance-matrix">
          <h4 className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('circ.matrix')}</h4>
          <table className="font-mono text-[10px]">
            <tbody>
              {r.matrix.values_H.map((row, i) => (
                <tr key={i}>
                  {row.map((v, j) => (
                    <td key={j} className="pr-2">{formatSI(v, 'H', 4)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {r.matrix && (
        <p className="text-[11px] text-muted">
          {t(r.matrix.positive_definite ? 'circ.pdOk' : 'circ.pdFail', { min: formatSI(r.matrix.min_eigenvalue_H, 'H', 3) })}
          {r.matrix.reciprocity_max_relative != null && ` ${t('circ.recip', { rel: r.matrix.reciprocity_max_relative.toExponential(1) })}`}
        </p>
      )}
      {s && circuits.length > 0 && (
        <>
          <SeriesPlot t={s.t_s} now={now} title={t('circ.currentPlot')} unit="A" lines={circuits.map(({ e, i }, n) => ({ label: e.name, color: COLORS[n % COLORS.length]!, values: s.current_A[i]! }))} />
          <SeriesPlot
            t={s.t_s}
            now={now}
            title={t('circ.emfPlot')}
            unit="V"
            lines={circuits.flatMap(({ e, i }, n) => [
              { label: `${e.name} EMF_tr`, color: COLORS[n % COLORS.length]!, values: s.emf_transformer_V[i]! },
              { label: `${e.name} EMF_mot`, color: COLORS[(n + 3) % COLORS.length]!, values: s.emf_motional_V[i]! },
            ])}
          />
          {s.rod_velocity_m_per_s && <SeriesPlot t={s.t_s} now={now} title={t('circ.velocityPlot')} unit="m/s" lines={[{ label: 'v', color: '#e5e7eb', values: s.rod_velocity_m_per_s }]} />}
        </>
      )}
      {s && (
        <SeriesPlot
          t={s.t_s}
          now={now}
          title={t('circ.energyPlot')}
          unit="J"
          lines={[
            { label: 'W_m', color: '#38bdf8', values: s.magnetic_energy_J },
            { label: 'Q_R', color: '#fb923c', values: s.joule_heat_J },
            ...(s.kinetic_energy_J ? [{ label: 'K', color: '#a3e635', values: s.kinetic_energy_J }] : []),
          ]}
        />
      )}
      {s && k >= 0 && bands.length > 0 && <BandResults r={r} k={k} bands={bands} />}
      <p className="text-[11px] leading-snug text-muted">{loc(r.method)}</p>
    </div>
  )
}

function BandResults({ r, k, bands }: { r: CircuitResult; k: number; bands: { e: CircuitResult['elements'][number]; i: number }[] }) {
  const { t } = useT()
  const s = r.series!
  const jj = bands.map(({ i }) => s.current_density_A_per_m2[i]?.[k] ?? 0)
  const rad = bands.map(({ e }) => e.radius_m ?? 0)
  const rMax = Math.max(...rad, 1e-300)
  const jMax = Math.max(1e-300, ...jj.map(Math.abs))
  const x = (v: number) => 4 + (v / rMax) * (W - 8)
  const y = (v: number) => H / 2 - (v / jMax) * (H / 2 - 4)
  return (
    <div data-testid="band-results">
      <h4 className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('circ.bandsTitle')}</h4>
      <p className="text-[10px] text-warn/90">{t('circ.diskApprox')}</p>
      <svg width={W} height={H} role="img" aria-label={t('circ.jPlot')} className="text-muted">
        <line x1={4} x2={W - 4} y1={H / 2} y2={H / 2} stroke="currentColor" strokeWidth={0.5} />
        <path d={jj.map((v, n) => `${n ? 'L' : 'M'}${x(rad[n]!).toFixed(1)},${y(v).toFixed(1)}`).join('')} fill="none" stroke="#f472b6" strokeWidth={1.3} />
        {jj.map((v, n) => (
          <circle key={n} cx={x(rad[n]!)} cy={y(v)} r={1.6} fill="#f472b6" />
        ))}
      </svg>
      <p className="text-[10px] text-muted">{t('circ.jPlot')} (±{formatSI(jMax, 'A/m²', 2)}), r ≤ {formatSI(rMax, 'm', 3)}</p>
      <table className="w-full font-mono text-[10px]">
        <thead>
          <tr className="text-left text-muted">
            <th className="font-normal">#</th>
            <th className="font-normal">r</th>
            <th className="font-normal">I</th>
            <th className="font-normal">R</th>
            <th className="font-normal">J_φ</th>
            <th className="font-normal">P</th>
          </tr>
        </thead>
        <tbody>
          {bands.map(({ e, i }) => (
            <tr key={e.id}>
              <td>{(e.band_index ?? 0) + 1}</td>
              <td>{formatSI(e.radius_m ?? 0, 'm', 3)}</td>
              <td>{formatSI(s.current_A[i]![k]!, 'A', 3)}</td>
              <td>{formatSI(e.resistance_ohm, 'Ω', 3)}</td>
              <td>{formatSI(s.current_density_A_per_m2[i]?.[k] ?? 0, 'A/m²', 3)}</td>
              <td>{formatSI(s.joule_power_W[i]![k]!, 'W', 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CircuitsPanel({ data }: { data: CircuitsData }) {
  const { t } = useT()
  const circuits = useSceneStore((s) => s.circuits)
  const disks = useSceneStore((s) => s.eddyDisks)
  const selectedId = useSceneStore((s) => s.selectedCircuitId)
  const fluxId = useSceneStore((s) => s.selectedFluxId)
  const flux = useSceneStore((s) => s.fluxSurfaces.find((f) => f.id === fluxId))
  const selected = circuits.find((c) => c.id === selectedId)
  const add = (kind: FluxKind) => store().addCircuit(kind, `${t(kind === 'sliding_rod' ? 'rod.name' : (`ampere.kind.${kind}` as MessageKey))} ${circuits.length + 1}`)
  return (
    <div>
      <Section title={t('circ.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('circ.intro')}</p>
        <div className="flex flex-wrap gap-1">
          {KINDS.map(({ kind, icon: Icon }) => (
            <Button key={kind} variant="primary" onClick={() => add(kind)}>
              <Icon size={12} /> {t(kind === 'sliding_rod' ? 'rod.add' : (`ampere.kind.${kind}` as MessageKey))}
            </Button>
          ))}
          <Button variant="primary" onClick={() => store().addDisk(`${t('circ.disk')} ${disks.length + 1}`)}>
            <Disc size={12} /> {t('circ.disk')}
          </Button>
          {flux && (
            <Button onClick={() => store().convertFluxToCircuit(flux.id, `${flux.name || flux.id} (${t('circ.circuit')})`)}>
              <Zap size={12} /> {t('circ.convert', { name: flux.name || flux.id })}
            </Button>
          )}
        </div>
        {circuits.length + disks.length === 0 ? (
          <p className="text-xs text-muted">{t('circ.none')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t('circ.list')}>
            {circuits.map((c) => (
              <li key={c.id} className={cn('flex items-center gap-1 rounded px-1.5 py-1', c.id === selectedId ? 'bg-accent/15' : 'hover:bg-panel-2')}>
                <button type="button" aria-pressed={c.id === selectedId} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => store().selectCircuit(c.id)}>
                  <span className="truncate">{c.name || c.id}</span>
                </button>
                <Button variant="danger" size="icon" aria-label={t('ampere.delete', { name: c.name || c.id })} onClick={() => store().removeCircuit(c.id)}>
                  <Trash2 size={13} />
                </Button>
              </li>
            ))}
            {disks.map((d) => (
              <li key={d.id} className="flex items-center gap-1 rounded px-1.5 py-1">
                <span className="flex-1 truncate text-xs">{d.name || d.id} ({t('circ.bandsCount', { n: d.bands ?? 0 })})</span>
                <Button variant="danger" size="icon" aria-label={t('ampere.delete', { name: d.name || d.id })} onClick={() => store().removeDisk(d.id)}>
                  <Trash2 size={13} />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {data.tooMany && <p className="text-xs text-danger">{t('circ.tooMany', { n: data.samples })}</p>}
        {data.error && <p className="text-xs text-danger">{data.error.message}</p>}
        <Results data={data} />
      </Section>
      {selected && <CircuitEditor key={selected.id} c={selected} />}
      {disks.map((d) => (
        <DiskEditor key={d.id} d={d} />
      ))}
      <Section title={t('circ.aboutTitle')}>
        <p className="text-[11px] leading-snug text-muted">{t('circ.about')}</p>
      </Section>
    </div>
  )
}
