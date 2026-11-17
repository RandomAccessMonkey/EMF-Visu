// Motion of Faraday measurement conductors (Phase 4B): rigid motion profiles of a surface, the
// sliding-rod circuit, the N-turn coil option and the waveform history. The profiles are input
// data; poses, velocities, fluxes and EMFs are evaluated by the engine only.
import type { FluxSurface, MotionProfile, Rotation, SlidingRodShape, Translation, Vec3 } from '@/api/types'
import { Button, NumberField, Row, Section, Select, Switch } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatSI } from '@/lib/format'
import type { HistoryPoint } from '@/sim/useInduction'
import { useSceneStore } from '@/state/sceneStore'
import { VecRows } from './AmperePanel'

const DEG = Math.PI / 180
type TKind = Translation['type']
type RKind = Rotation['type']

const update = (id: string, patch: Partial<FluxSurface>) => useSceneStore.getState().updateFlux(id, patch)

function defaultTranslation(kind: TKind): Translation {
  if (kind === 'constant_velocity') return { type: 'constant_velocity', velocity_m_per_s: [0.1, 0, 0], t0_s: 0 }
  if (kind === 'constant_acceleration') return { type: 'constant_acceleration', velocity_m_per_s: [0, 0, 0], acceleration_m_per_s2: [0.1, 0, 0], t0_s: 0 }
  if (kind === 'sinusoidal') return { type: 'sinusoidal', amplitude_m: 0.02, axis: [1, 0, 0], frequency_Hz: 1, phase_rad: 0 }
  return { type: 'stationary' }
}

function defaultRotation(kind: RKind): Rotation {
  return kind === 'constant_angular_velocity' ? { type: 'constant_angular_velocity', axis: [1, 0, 0], omega_rad_per_s: 2 * Math.PI, t0_s: 0 } : { type: 'none' }
}

type Windowed = { t_start_s?: number | null; t_end_s?: number | null }

/** Optional active window [t_start, t_end] of a motion profile (held outside it). */
function WindowRows({ w, onChange }: { w: Windowed; onChange: (patch: Windowed) => void }) {
  const { t } = useT()
  const opt = (key: 't_start_s' | 't_end_s', label: string, fallback: number) => {
    const v = w[key]
    return (
      <Row key={key} label={label}>
        <Switch label={`${label} ${t('motion.limit')}`} checked={v !== undefined && v !== null} onChange={(on) => onChange({ [key]: on ? fallback : undefined })} />
        {v !== undefined && v !== null && <NumberField label={label} value={v} unit="s" step={0.1} onChange={(x) => onChange({ [key]: x })} />}
      </Row>
    )
  }
  return (
    <>
      {opt('t_start_s', t('motion.tStart'), 0)}
      {opt('t_end_s', t('motion.tEnd'), 1)}
    </>
  )
}

function TranslationRows({ tr, onChange, alongX = false }: { tr: Translation; onChange: (tr: Translation) => void; alongX?: boolean }) {
  const { t } = useT()
  const vec = (label: string, value: Vec3, unit: string, apply: (v: Vec3) => Translation) =>
    alongX ? (
      <Row key={label} label={`${label} x`}>
        <NumberField label={`${label} x`} value={value[0]} unit={unit} step={0.1} onChange={(x) => onChange(apply([x, 0, 0]))} />
      </Row>
    ) : (
      <VecRows key={label} label={label} value={value} unit={unit} step={0.1} onChange={(v) => onChange(apply(v))} />
    )
  return (
    <>
      <Row label={t('motion.translation')}>
        <Select<TKind>
          label={t('motion.translation')}
          value={tr.type}
          onChange={(k) => {
            const d = defaultTranslation(k)
            onChange(alongX && d.type === 'sinusoidal' ? { ...d, axis: [1, 0, 0] } : d)
          }}
          options={(['stationary', 'constant_velocity', 'constant_acceleration', 'sinusoidal'] as TKind[]).map((k) => ({ value: k, label: t(`motion.kind.${k}` as MessageKey) }))}
        />
      </Row>
      {tr.type === 'constant_velocity' && (
        <>
          {vec('V₀', tr.velocity_m_per_s as Vec3, 'm/s', (v) => ({ ...tr, velocity_m_per_s: v }))}
          <Row label="t₀"><NumberField label="t0" value={tr.t0_s ?? 0} unit="s" step={0.1} onChange={(x) => onChange({ ...tr, t0_s: x })} /></Row>
          <WindowRows w={tr} onChange={(p) => onChange({ ...tr, ...p } as Translation)} />
        </>
      )}
      {tr.type === 'constant_acceleration' && (
        <>
          {vec('V₀', tr.velocity_m_per_s as Vec3, 'm/s', (v) => ({ ...tr, velocity_m_per_s: v }))}
          {vec('a', tr.acceleration_m_per_s2 as Vec3, 'm/s²', (v) => ({ ...tr, acceleration_m_per_s2: v }))}
          <Row label="t₀"><NumberField label="t0" value={tr.t0_s ?? 0} unit="s" step={0.1} onChange={(x) => onChange({ ...tr, t0_s: x })} /></Row>
          <WindowRows w={tr} onChange={(p) => onChange({ ...tr, ...p } as Translation)} />
        </>
      )}
      {tr.type === 'sinusoidal' && (
        <>
          <Row label={t('motion.amplitude')}><NumberField label={t('motion.amplitude')} value={tr.amplitude_m ?? 0} unit="m" min={0} step={0.01} onChange={(x) => onChange({ ...tr, amplitude_m: x })} /></Row>
          {!alongX && <VecRows label={t('motion.axis')} value={(tr.axis ?? [1, 0, 0]) as Vec3} unit="" step={1} onChange={(v) => onChange({ ...tr, axis: v })} />}
          <Row label="f"><NumberField label={t('motion.frequency')} value={tr.frequency_Hz ?? 1} unit="Hz" min={1e-9} step={0.1} onChange={(x) => onChange({ ...tr, frequency_Hz: x })} /></Row>
          <Row label="φ"><NumberField label={t('motion.phase')} value={tr.phase_rad ?? 0} unit="rad" step={0.1} onChange={(x) => onChange({ ...tr, phase_rad: x })} /></Row>
          <WindowRows w={tr} onChange={(p) => onChange({ ...tr, ...p } as Translation)} />
        </>
      )}
    </>
  )
}

/** Rigid motion of a circle / rectangle / polygon measurement surface. */
export function MotionEditor({ f }: { f: FluxSurface }) {
  const { t } = useT()
  const m: MotionProfile | null | undefined = f.motion
  const setMotion = (motion: MotionProfile | null) => update(f.id, { motion })
  const rot: Rotation = m?.rotation ?? { type: 'none' }
  return (
    <Section title={t('motion.title')}>
      <p className="text-[11px] leading-snug text-muted">{t('motion.intro')}</p>
      <Row label={t('motion.moving')}>
        <Switch label={t('motion.moving')} checked={!!m} onChange={(on) => setMotion(on ? { translation: { type: 'stationary' }, rotation: defaultRotation('constant_angular_velocity') } : null)} />
      </Row>
      {m && (
        <div className="flex flex-col gap-1.5" data-testid="motion-editor">
          <TranslationRows tr={m.translation ?? { type: 'stationary' }} onChange={(tr) => setMotion({ ...m, translation: tr })} />
          <Row label={t('motion.rotation')}>
            <Select<RKind>
              label={t('motion.rotation')}
              value={rot.type}
              onChange={(k) => setMotion({ ...m, rotation: defaultRotation(k) })}
              options={(['none', 'constant_angular_velocity'] as RKind[]).map((k) => ({ value: k, label: t(`motion.kind.${k}` as MessageKey) }))}
            />
          </Row>
          {rot.type === 'constant_angular_velocity' && (
            <>
              <VecRows label={t('motion.axis')} value={(rot.axis ?? [0, 0, 1]) as Vec3} unit="" step={1} onChange={(v) => setMotion({ ...m, rotation: { ...rot, axis: v } })} />
              <Row label="ω" hint={t('motion.omegaHint')}>
                <NumberField label={t('motion.omega')} value={rot.omega_rad_per_s ?? 0} unit="rad/s" step={0.5} onChange={(x) => setMotion({ ...m, rotation: { ...rot, omega_rad_per_s: x } })} />
              </Row>
              <Row label="t₀"><NumberField label="rotation t0" value={rot.t0_s ?? 0} unit="s" step={0.1} onChange={(x) => setMotion({ ...m, rotation: { ...rot, t0_s: x } })} /></Row>
              <WindowRows w={rot} onChange={(p) => setMotion({ ...m, rotation: { ...rot, ...p } })} />
            </>
          )}
        </div>
      )}
      <TurnsRow f={f} />
    </Section>
  )
}

function TurnsRow({ f }: { f: FluxSurface }) {
  const { t } = useT()
  return (
    <Row label={t('motion.turns')} hint={t('motion.turnsHint')}>
      <NumberField label={t('motion.turns')} value={f.turns ?? 1} min={1} max={100000} step={1} onChange={(n) => Number.isInteger(n) && update(f.id, { turns: n })} />
    </Row>
  )
}

/** The sliding-rod circuit: rails, connecting segment and the moving rod. */
export function RodEditor({ f }: { f: FluxSurface }) {
  const { t } = useT()
  const sh = f.shape as SlidingRodShape
  const set = (patch: Partial<SlidingRodShape>) => update(f.id, { shape: { ...sh, ...patch } })
  const num = (label: string, value: number, unit: string, apply: (v: number) => Partial<SlidingRodShape>) => (
    <Row key={label} label={label}>
      <NumberField label={label} value={value} unit={unit} min={1e-6} step={0.01} onChange={(v) => set(apply(v))} />
    </Row>
  )
  return (
    <Section title={t('rod.title', { name: f.name || f.id })}>
      <p className="text-[11px] leading-snug text-muted">{t('rod.intro')}</p>
      <div className="flex flex-col gap-1.5" data-testid="rod-editor">
        <Row label={t('params.name')}>
          <input aria-label={t('params.name')} value={f.name} onChange={(e) => update(f.id, { name: e.target.value })} className="h-7 w-36 rounded-md border border-border bg-bg px-1.5 text-xs" />
        </Row>
        {num(`${t('rod.separation')} L`, sh.rail_separation_m ?? 0.1, 'm', (v) => ({ rail_separation_m: v }))}
        {num(t('rod.railLength'), sh.rail_length_m ?? 0.3, 'm', (v) => ({ rail_length_m: v }))}
        {num(`${t('rod.position')} x₀`, sh.rod_position_m ?? 0.05, 'm', (v) => ({ rod_position_m: v }))}
        <TranslationRows tr={sh.rod_motion ?? { type: 'stationary' }} alongX onChange={(tr) => set({ rod_motion: tr })} />
        <VecRows label={t('params.position')} value={f.center_m as Vec3} unit="m" step={0.01} onChange={(v) => update(f.id, { center_m: v })} />
        <VecRows label={t('params.rotation')} value={f.rotation_euler_xyz_rad as Vec3} unit="°" factor={DEG} step={15} onChange={(v) => update(f.id, { rotation_euler_xyz_rad: v })} />
        <Row label={t('ampere.orientation')} hint={t('ampere.orientationHint')}>
          <Button aria-label={t(f.reversed ? 'ampere.reversed' : 'ampere.forward')} onClick={() => update(f.id, { reversed: !f.reversed })}>
            {t(f.reversed ? 'ampere.reversed' : 'ampere.forward')}
          </Button>
        </Row>
      </div>
    </Section>
  )
}

const W = 270
const H = 90

/** Waveforms of the computed times: flux (left scale) and EMFs (right scale). Only points the
 *  engine computed are drawn (no interpolation beyond straight segments between them). */
export function Waveforms({ points, now }: { points: HistoryPoint[]; now: number }) {
  const { t } = useT()
  const pts = points.filter((p) => p.flux !== null)
  if (pts.length < 2) return <p className="text-[11px] text-muted">{t('motion.historyHint')}</p>
  const t0 = pts[0]!.t
  const t1 = pts[pts.length - 1]!.t
  const span = t1 - t0 || 1
  const x = (v: number) => 4 + ((v - t0) / span) * (W - 8)
  const scaleOf = (vals: (number | null)[]) => Math.max(1e-300, ...vals.map((v) => Math.abs(v ?? 0)))
  const fs = scaleOf(pts.map((p) => p.flux))
  const es = scaleOf(pts.flatMap((p) => [p.emfTotal, p.emfMot, p.refEmf, p.dflux === null ? null : -p.dflux]))
  const y = (v: number, s: number) => H / 2 - (v / s) * (H / 2 - 4)
  const line = (get: (p: HistoryPoint) => number | null, s: number) =>
    pts
      .filter((p) => get(p) !== null)
      .map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(get(p)!, s).toFixed(1)}`)
      .join('')
  const series = [
    { key: 'flux', color: '#38bdf8', d: line((p) => p.flux, fs), dash: undefined },
    { key: 'emf', color: '#f472b6', d: line((p) => p.emfTotal, es), dash: undefined },
    { key: 'minusDphi', color: '#facc15', d: line((p) => (p.dflux === null ? null : -p.dflux), es), dash: '3 3' },
    { key: 'ref', color: '#a3a3a3', d: line((p) => p.refEmf, es), dash: '1 3' },
  ]
  return (
    <div data-testid="waveforms">
      <svg width={W} height={H} role="img" aria-label={t('motion.waveforms')} className="text-muted">
        <line x1={4} x2={W - 4} y1={H / 2} y2={H / 2} stroke="currentColor" strokeWidth={0.5} />
        {series.map((s) => s.d && <path key={s.key} d={s.d} fill="none" stroke={s.color} strokeWidth={1.4} strokeDasharray={s.dash} />)}
        {now >= t0 && now <= t1 && <line x1={x(now)} x2={x(now)} y1={2} y2={H - 2} stroke="#22d3ee" strokeWidth={1} />}
      </svg>
      <div className="flex flex-wrap gap-x-3 text-[10px]">
        <span style={{ color: '#38bdf8' }}>Φ_B (±{formatSI(fs, 'Wb', 2)})</span>
        <span style={{ color: '#f472b6' }}>EMF (±{formatSI(es, 'V', 2)})</span>
        <span style={{ color: '#facc15' }}>−dΦ_B/dt</span>
        <span style={{ color: '#a3a3a3' }}>{t('motion.reference')}</span>
      </div>
      <p className="text-[10px] text-muted">{t('motion.historyNote', { n: pts.length })}</p>
    </div>
  )
}
