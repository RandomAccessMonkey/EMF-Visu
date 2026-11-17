// Axial field profile of the selected solenoid or magnet: B·â sampled by the engine at points
// on the symmetry axis, with the winding (or magnet) extent marked and, for a solenoid, the
// ideal long-solenoid value μ₀nI from the engine's source table as a dashed reference line.
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type { SimulationResult } from '@/api/container'
import { api } from '@/api/client'
import type { CurrentSourceInfo, SolveRequest, Vec3 } from '@/api/types'
import { Section } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { formatSI } from '@/lib/format'
import { fieldScene, physicsKey } from '@/sim/request'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const N = 161
const W = 280
const H = 140
const PAD = { l: 44, r: 8, t: 8, b: 22 }

export function axisSamples(info: CurrentSourceInfo): { s: number[]; points: Vec3[]; half: number } {
  const half = (info.length_m ?? 0) / 2
  const a = info.radius_m ?? 0
  const span = half + Math.max(2 * a, 0.5 * half)
  const s = Array.from({ length: N }, (_, i) => -span + (2 * span * i) / (N - 1))
  const c = info.point_m
  const d = info.direction
  return { s, half, points: s.map((x) => [c[0]! + x * d[0]!, c[1]! + x * d[1]!, c[2]! + x * d[2]!] as Vec3) }
}

export function AxisProfile({ info }: { info: CurrentSourceInfo }) {
  const { t } = useT()
  const scene = useSceneStore((s) => s.scene)
  const dragging = useViewStore((s) => s.dragging)
  const { s, points, half } = useMemo(() => axisSamples(info), [info])
  const request: SolveRequest = useMemo(
    () => ({ samplings: [{ kind: 'points', id: 'axis', points_m: points }], quantities: ['B'], quality: 'normal', source_contributions: [] }),
    [points],
  )
  const sub = useMemo(() => fieldScene(scene, 'magnetic'), [scene])
  const query = useQuery({
    queryKey: ['axis-profile', physicsKey(scene, request)],
    queryFn: ({ signal }): Promise<SimulationResult> => api.simulate(sub, request, signal),
    enabled: !dragging,
    staleTime: Infinity,
    retry: false,
  })
  const values = useMemo(() => {
    const b = query.data?.arrays['axis.B']?.data
    if (!b) return null
    const d = info.direction
    return s.map((_, i) => b[3 * i]! * d[0]! + b[3 * i + 1]! * d[1]! + b[3 * i + 2]! * d[2]!)
  }, [query.data, s, info.direction])
  const ideal = info.ideal_long_solenoid?.B_T ?? null
  if (query.isError) return null
  const finite = values?.filter((v) => Number.isFinite(v)) ?? []
  const lo = Math.min(0, ...finite, ideal ?? 0)
  const hi = Math.max(0, ...finite, ideal ?? 0)
  const x = (v: number) => PAD.l + ((v - s[0]!) / (s[N - 1]! - s[0]!)) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (hi === lo ? 0.5 : (hi - v) / (hi - lo)) * (H - PAD.t - PAD.b)
  const path = values
    ? values.map((v, i) => (Number.isFinite(v) ? `${i === 0 || !Number.isFinite(values[i - 1]!) ? 'M' : 'L'}${x(s[i]!).toFixed(1)},${y(v).toFixed(1)}` : '')).join('')
    : ''
  const magnet = info.kind === 'permanent_magnet'
  return (
    <Section title={t('profile.title')}>
      <svg width={W} height={H} role="img" aria-label={t('profile.aria')} className="text-muted">
        <rect x={x(-half)} y={PAD.t} width={Math.max(1, x(half) - x(-half))} height={H - PAD.t - PAD.b} fill="currentColor" opacity={0.08} />
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} stroke="currentColor" strokeWidth={0.5} />
        {ideal !== null && (
          <line x1={x(-half)} x2={x(half)} y1={y(ideal)} y2={y(ideal)} stroke="var(--color-warn, #f59e0b)" strokeDasharray="4 3" strokeWidth={1} />
        )}
        {path && <path d={path} fill="none" stroke={magnet ? '#f87171' : '#c084fc'} strokeWidth={1.5} />}
        <text x={PAD.l - 4} y={y(hi) + 4} textAnchor="end" fontSize={9} fill="currentColor">{formatSI(hi, 'T', 2)}</text>
        <text x={PAD.l - 4} y={y(lo)} textAnchor="end" fontSize={9} fill="currentColor">{formatSI(lo, 'T', 2)}</text>
        <text x={x(0)} y={H - 6} textAnchor="middle" fontSize={9} fill="currentColor">{t('profile.axisLabel')}</text>
        <text x={x(-half)} y={H - 6} textAnchor="middle" fontSize={9} fill="currentColor">−L/2</text>
        <text x={x(half)} y={H - 6} textAnchor="middle" fontSize={9} fill="currentColor">L/2</text>
      </svg>
      <p className="text-[11px] leading-snug text-muted">{t(magnet ? 'profile.magnetNote' : 'profile.solenoidNote')}</p>
    </Section>
  )
}
