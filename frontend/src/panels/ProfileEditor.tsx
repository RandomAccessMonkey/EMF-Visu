// Time-dependent current profile of a current source (Phase 4A). The profile is input data; its
// values I(t) and dI/dt are always evaluated by the engine (the plot via /profile/sample, the
// current values from the magnetic result at the simulation time).
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import type { CurrentProfile, SceneObject, TimeSourceInfo } from '@/api/types'
import { Button, NumberField, Row, Select } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { formatPlain, formatSI } from '@/lib/format'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

type Kind = 'none' | 'sinusoidal' | 'ramp' | 'piecewise_linear'
type Sine = Extract<CurrentProfile, { type: 'sinusoidal' }>
type Ramp = Extract<CurrentProfile, { type: 'ramp' }>
type Piecewise = Extract<CurrentProfile, { type: 'piecewise_linear' }>

/** A starting profile of the chosen kind built from the source's present current. */
function defaultProfile(kind: Exclude<Kind, 'none'>, current: number): CurrentProfile {
  const peak = Math.abs(current) || 1
  if (kind === 'sinusoidal') return { type: 'sinusoidal', dc_A: 0, peak_A: peak, frequency_Hz: 1, phase_rad: 0 }
  if (kind === 'ramp') return { type: 'ramp', start_A: 0, slope_A_per_s: peak, t_start_s: 0, t_end_s: 1 }
  return { type: 'piecewise_linear', keyframes: [{ t_s: 0, current_A: 0 }, { t_s: 0.5, current_A: peak }, { t_s: 1, current_A: 0 }] }
}

const W = 260
const H = 70

function Waveform({ profile }: { profile: CurrentProfile }) {
  const { t } = useT()
  const start = useViewStore((s) => s.timeStart)
  const end = useViewStore((s) => s.timeEnd)
  const now = useViewStore((s) => s.timeS)
  const q = useQuery({
    queryKey: ['profile', profile, start, end],
    queryFn: ({ signal }) => api.profileSample(profile, start, end, signal),
    enabled: end > start,
    staleTime: Infinity,
    retry: false,
  })
  if (!q.data) return null
  const { t_s, current_A } = q.data
  const lo = Math.min(0, ...current_A)
  const hi = Math.max(0, ...current_A)
  const x = (v: number) => 4 + ((v - start) / (end - start)) * (W - 8)
  const y = (v: number) => 4 + (hi === lo ? 0.5 : (hi - v) / (hi - lo)) * (H - 8)
  const d = t_s.map((ti, i) => `${i ? 'L' : 'M'}${x(ti).toFixed(1)},${y(current_A[i]!).toFixed(1)}`).join('')
  return (
    <svg width={W} height={H} role="img" aria-label={t('profile.waveform')} className="text-muted">
      <line x1={4} x2={W - 4} y1={y(0)} y2={y(0)} stroke="currentColor" strokeWidth={0.5} />
      <path d={d} fill="none" stroke="#c084fc" strokeWidth={1.5} />
      {now >= start && now <= end && <line x1={x(now)} x2={x(now)} y1={2} y2={H - 2} stroke="#22d3ee" strokeWidth={1} />}
      {q.data.corners_s.map((c) => (
        <circle key={c} cx={x(c)} cy={H - 4} r={2} fill="#f59e0b" />
      ))}
    </svg>
  )
}

export function ProfileEditor({ o, profile, info }: { o: SceneObject; profile: CurrentProfile | null | undefined; info?: TimeSourceInfo }) {
  const { t } = useT()
  const timeS = useViewStore((s) => s.timeS)
  const setProfile = (p: CurrentProfile | null) => useSceneStore.getState().setProfile(o.id, p)
  const current = o.source && 'current_A' in o.source ? o.source.current_A : 0
  const kind: Kind = !profile || profile.type === 'constant' ? 'none' : profile.type
  const num = (label: string, value: number, unit: string, apply: (v: number) => CurrentProfile, extra: { min?: number; step?: number } = {}) => (
    <Row key={label} label={label}>
      <NumberField label={label} value={value} unit={unit} step={extra.step ?? 0.1} min={extra.min} onChange={(v) => setProfile(apply(v))} />
    </Row>
  )
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border/70 p-2" data-testid="profile-editor">
      <Row label={t('profile.type')} hint={t('profile.typeHint')}>
        <Select<Kind>
          label={t('profile.type')}
          value={kind}
          onChange={(k) => setProfile(k === 'none' ? null : defaultProfile(k, current))}
          options={[
            { value: 'none', label: t('profile.constant') },
            { value: 'sinusoidal', label: t('profile.sinusoidal') },
            { value: 'ramp', label: t('profile.ramp') },
            { value: 'piecewise_linear', label: t('profile.piecewise') },
          ]}
        />
      </Row>
      {profile?.type === 'sinusoidal' && (() => {
        const p = profile as Sine
        return (
          <>
            {num(`${t('profile.dc')} I_dc`, p.dc_A, 'A', (v) => ({ ...p, dc_A: v }))}
            {num(`${t('profile.peak')} I_peak`, p.peak_A, 'A', (v) => ({ ...p, peak_A: v }), { min: 0 })}
            {num(`${t('profile.frequency')} f`, p.frequency_Hz, 'Hz', (v) => ({ ...p, frequency_Hz: v }), { min: 1e-9 })}
            {num(`${t('profile.phase')} φ`, p.phase_rad, 'rad', (v) => ({ ...p, phase_rad: v }))}
          </>
        )
      })()}
      {profile?.type === 'ramp' && (() => {
        const p = profile as Ramp
        return (
          <>
            {num(`${t('profile.start')} I_start`, p.start_A, 'A', (v) => ({ ...p, start_A: v }))}
            {num(`${t('profile.slope')} s`, p.slope_A_per_s, 'A/s', (v) => ({ ...p, slope_A_per_s: v }))}
            {num(`${t('profile.tStart')} t_start`, p.t_start_s, 's', (v) => ({ ...p, t_start_s: v }))}
            {num(`${t('profile.tEnd')} t_end`, p.t_end_s, 's', (v) => ({ ...p, t_end_s: v }))}
            <p className="text-[11px] leading-snug text-muted">{t('profile.rampNote')}</p>
          </>
        )
      })()}
      {profile?.type === 'piecewise_linear' && (() => {
        const p = profile as Piecewise
        const setKey = (i: number, patch: Partial<Piecewise['keyframes'][number]>) =>
          setProfile({ ...p, keyframes: p.keyframes.map((k, j) => (j === i ? { ...k, ...patch } : k)) })
        return (
          <>
            {p.keyframes.map((k, i) => (
              <Row key={i} label={`k${i + 1} (t, I)`}>
                <NumberField label={`k${i + 1} t`} value={k.t_s} step={0.1} onChange={(v) => setKey(i, { t_s: v })} />
                <NumberField label={`k${i + 1} I`} value={k.current_A} unit="A" step={0.1} onChange={(v) => setKey(i, { current_A: v })} />
                <Button variant="ghost" size="icon" aria-label={t('profile.removeKey', { n: i + 1 })} disabled={p.keyframes.length <= 2} onClick={() => setProfile({ ...p, keyframes: p.keyframes.filter((_, j) => j !== i) })}>
                  <Trash2 size={12} />
                </Button>
              </Row>
            ))}
            <Button
              disabled={p.keyframes.length >= 64}
              onClick={() => {
                const last = p.keyframes[p.keyframes.length - 1]!
                setProfile({ ...p, keyframes: [...p.keyframes, { t_s: last.t_s + 0.5, current_A: last.current_A }] })
              }}
            >
              <Plus size={12} /> {t('profile.addKey')}
            </Button>
            <p className="text-[11px] leading-snug text-muted">{t('profile.piecewiseNote')}</p>
          </>
        )
      })()}
      {profile && profile.type !== 'constant' && <Waveform profile={profile} />}
      {profile && profile.type !== 'constant' && info && (
        <p className="font-mono text-[11px]" data-testid="profile-now">
          t = {formatPlain(timeS, 's', 6)}: I = {formatSI(info.current_A, 'A', 5)}, dI/dt = {formatSI(info.dI_dt_A_per_s, 'A/s', 5)}
          {!info.derivative_unique && ` (${t('profile.corner', { left: formatSI(info.dI_dt_left_A_per_s, 'A/s', 4) })})`}
        </p>
      )}
    </div>
  )
}
