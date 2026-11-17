// Faraday's law, Lenz's law and mutual induction for stationary measurement surfaces (Phase 4A).
// Every number shown comes from the engine; this panel only formats and explains it. Undefined
// or unsupported values are shown as such, never as zero.
import { useMemo } from 'react'
import { Circle, Eye, EyeOff, MoveHorizontal, Pentagon, Square, Trash2 } from 'lucide-react'
import type { AmperePath, SurfaceResult } from '@/api/types'
import { Badge, Button, Row, Section, Select } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatPlain, formatSI } from '@/lib/format'
import { useInductionHistory, type InductionData } from '@/sim/useInduction'
import { pathDisplayOf, useSceneStore, type FluxKind } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { PathEditor, type PathOps } from './AmperePanel'
import { MotionEditor, RodEditor, Waveforms } from './MotionEditor'

const KINDS: { kind: FluxKind; icon: typeof Circle }[] = [
  { kind: 'circle', icon: Circle },
  { kind: 'rectangle', icon: Square },
  { kind: 'polygon', icon: Pentagon },
  { kind: 'sliding_rod', icon: MoveHorizontal },
]

const vec = (v: number[] | null | undefined, unit: string) => (v ? `(${v.map((x) => formatSI(x, '', 3)).join(', ')}) ${unit}` : '—')

type Tone = 'ok' | 'warn' | 'muted' | 'danger' | 'accent'
export const FARADAY_TONE: Record<SurfaceResult['status'], Tone> = {
  verified: 'ok',
  line_not_converged: 'warn',
  surface_not_converged: 'warn',
  invalid: 'danger',
  singular: 'warn',
  unsupported: 'muted',
  failed: 'danger',
  derivative_not_converged: 'warn',
  motion_undefined: 'warn',
}

const FLUX_OPS: PathOps = {
  update: (id, patch) => useSceneStore.getState().updateFlux(id, patch),
  setDisplay: (id, patch) => useSceneStore.getState().setFluxDisplay(id, patch),
}

const volts = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatSI(v, 'V', 5))

function Lenz({ r }: { r: SurfaceResult }) {
  const { t } = useT()
  if (!r.lenz) return null
  const { flux_trend, circulation } = r.lenz
  return (
    <div className="rounded-md border border-accent-2/40 bg-accent-2/5 p-2 text-[11px] leading-snug" data-testid="lenz-explanation">
      <p className="font-semibold text-accent-2">{t('faraday.lenzTitle')}</p>
      <p>{t(`faraday.trend.${flux_trend}` as MessageKey)}</p>
      <p>{t(`faraday.circulation.${circulation}` as MessageKey)}</p>
      <p className="mt-1 text-muted">{t('faraday.lenzNote')}</p>
    </div>
  )
}

/** Phase 4B: the moving conductor's state and the generalized Faraday comparison. */
function MovingRows({ r }: { r: SurfaceResult }) {
  const { t, loc } = useT()
  const m = r.motion
  const d = r.derivative
  return (
    <div className="flex flex-col gap-1" data-testid="moving-result">
      <table className="w-full font-mono text-[11px]" aria-label={t('motion.resultTable')}>
        <tbody>
          <tr><td className="pr-2 text-muted">{t('motion.emfTr')}</td><td>{r.emf_V == null ? t('faraday.notEvaluated') : volts(r.emf_V)}</td></tr>
          <tr><td className="pr-2 text-muted">{t('motion.emfMot')}</td><td>{r.emf_motional_V == null ? '—' : `${volts(r.emf_motional_V)} ± ${formatSI(r.emf_motional_error_V ?? 0, 'V', 2)}`}</td></tr>
          <tr><td className="pr-2 text-muted">{t('motion.emfTotal')}</td><td data-testid="emf-total">{r.emf_total_V == null ? t('motion.incomplete') : volts(r.emf_total_V)}</td></tr>
          {d && (
            <tr>
              <td className="pr-2 text-muted">{t('motion.derivative')}</td>
              <td>{t(`motion.method.${d.method}` as MessageKey)}, Δt = {formatSI(d.step_s ?? 0, 's', 2)}, {t(d.converged ? 'motion.converged' : 'motion.notConverged')} ({formatSI(d.error_V ?? 0, 'V', 2)})</td>
            </tr>
          )}
          {m && <tr><td className="pr-2 text-muted">c(t)</td><td>{vec(m.center_m, 'm')}</td></tr>}
          {m && <tr><td className="pr-2 text-muted">V</td><td>{m.velocity_m_per_s ? vec(m.velocity_m_per_s, 'm/s') : t('motion.undefinedVelocity')}</td></tr>}
          {m && m.kind === 'rigid' && <tr><td className="pr-2 text-muted">ω</td><td>{m.angular_velocity_rad_per_s ? vec(m.angular_velocity_rad_per_s, 'rad/s') : '—'}</td></tr>}
          {m && m.kind === 'sliding_rod' && (
            <tr><td className="pr-2 text-muted">x, v</td><td>{formatPlain(m.rod_position_m ?? 0, 'm', 5)}, {m.rod_velocity_m_per_s == null ? '—' : formatSI(m.rod_velocity_m_per_s, 'm/s', 4)}</td></tr>
          )}
          {m && !m.unique && (
            <tr><td className="pr-2 text-muted">V₋ / V₊</td><td>{vec(m.velocity_left_m_per_s, '')} / {vec(m.velocity_right_m_per_s, 'm/s')}</td></tr>
          )}
          {(r.turns ?? 1) > 1 && <tr><td className="pr-2 text-muted">N</td><td>{t('motion.turnsNote', { n: r.turns ?? 1 })}</td></tr>}
        </tbody>
      </table>
      {r.reference && (
        <div className="rounded-md border border-border/70 p-1.5 text-[11px]" data-testid="uniform-reference">
          <p className="font-mono">{t('motion.reference')}: EMF ≈ {volts(r.reference.emf_V)}{r.reference.flux_Wb != null && `, Φ ≈ ${formatSI(r.reference.flux_Wb, 'Wb', 4)}`}</p>
          <p className="text-muted">{loc(r.reference.note)}</p>
        </div>
      )}
    </div>
  )
}

export function SurfaceResultView({ r, stale }: { r: SurfaceResult; stale: boolean }) {
  const { t, loc } = useT()
  const objects = useSceneStore((s) => s.scene.objects)
  const names = useMemo(() => Object.fromEntries(objects.map((o) => [o.id, o.name || o.id])), [objects])
  return (
    <div className={cn('flex flex-col gap-1.5 text-xs', stale && 'opacity-60')} data-testid="faraday-result" aria-live="polite">
      <div className="flex items-center gap-2">
        <Badge tone={FARADAY_TONE[r.status]}>{t(`faraday.status.${r.status}` as MessageKey)}</Badge>
        <span className="font-mono text-[11px] text-muted">t = {formatPlain(r.time_s, 's', 6)}</span>
        {stale && <span className="text-[11px] text-muted">{t('ampere.stale')}</span>}
      </div>
      {r.invalid_reasons.map((x, i) => (
        <p key={i} className="text-[11px] text-danger">{loc(x)}</p>
      ))}
      {r.status_reason && <p className="text-[11px] leading-snug text-warn/90">{loc(r.status_reason)}</p>}
      {!r.derivative_unique && <p className="text-[11px] leading-snug text-warn/90">{t('faraday.corner')}</p>}
      {r.valid && (
        <table className="w-full font-mono text-[11px]" aria-label={t('faraday.table')}>
          <tbody>
            <tr><td className="pr-2 text-muted">Φ_B</td><td>{r.flux_Wb == null ? '—' : `${formatSI(r.flux_Wb, 'Wb', 6)} ± ${formatSI(r.flux_error_Wb ?? 0, 'Wb', 2)}`}</td></tr>
            <tr><td className="pr-2 text-muted">dΦ_B/dt</td><td>{volts(r.dflux_dt_V)}</td></tr>
            <tr><td className="pr-2 text-muted">∮E_ind·dl</td><td>{r.emf_V == null ? t('faraday.notEvaluated') : `${volts(r.emf_V)} ± ${formatSI(r.emf_error_V ?? 0, 'V', 2)}`}</td></tr>
            <tr><td className="pr-2 text-muted">−dΦ_B/dt</td><td>{r.dflux_dt_V == null ? '—' : volts(-r.dflux_dt_V)}</td></tr>
            {r.difference_V != null && (
              <tr><td className="pr-2 text-muted">{t('ampere.difference')}</td><td>{formatSI(r.difference_V, 'V', 2)} ({t('ampere.tolerance')} {formatSI(r.tolerance_V ?? 0, 'V', 2)})</td></tr>
            )}
            {r.relative_error != null && (
              <tr><td className="pr-2 text-muted">{t('faraday.relative')}</td><td>{r.relative_error.toExponential(2)}</td></tr>
            )}
            <tr><td className="pr-2 text-muted">{t('faraday.area')}</td><td>{formatPlain(r.area_m2, 'm²', 5)}</td></tr>
            <tr><td className="pr-2 text-muted">n̂</td><td>({(r.normal ?? []).map((x) => x.toFixed(3)).join(', ')})</td></tr>
            {r.surface_cells != null && (
              <tr><td className="pr-2 text-muted">{t('faraday.quadrature')}</td><td>{t('faraday.quadratureValue', { cells: r.surface_cells, sub: r.line_subintervals ?? 0 })}</td></tr>
            )}
          </tbody>
        </table>
      )}
      {r.moving && <MovingRows r={r} />}
      {r.warnings.map((w, i) => (
        <p key={`w${i}`} className="text-[11px] text-warn/90">{loc(w)}</p>
      ))}
      {r.no_change && r.status === 'verified' && <p className="text-[11px] leading-snug text-muted">{t('faraday.noChange')}</p>}
      <Lenz r={r} />
      {r.sources.length > 0 && (
        <table className="w-full text-[11px]" aria-label={t('faraday.sources')}>
          <thead>
            <tr className="text-left text-muted">
              <th className="font-normal">{t('probe.source')}</th>
              <th className="text-right font-normal">I(t)</th>
              <th className="text-right font-normal">dI/dt</th>
              <th className="text-right font-normal">EMF</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {r.sources.map((s) => (
              <tr key={s.object_id} className="border-t border-border/60">
                <td className="max-w-24 truncate font-sans">{names[s.object_id] ?? s.object_id}</td>
                <td className="text-right">{formatSI(s.current_A, 'A', 4)}</td>
                <td className="text-right">{formatSI(s.dI_dt_A_per_s, 'A/s', 4)}</td>
                <td className="text-right">{s.emf_V == null ? '—' : volts(s.emf_V)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {r.mutual.length > 0 && (
        <div data-testid="mutual">
          <h4 className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('faraday.mutualTitle')}</h4>
          {r.mutual.map((m) => (
            <div key={m.object_id} className="border-t border-border/60 py-1 font-mono text-[11px]">
              <p className="font-sans">{names[m.object_id] ?? m.object_id}</p>
              {m.M12_H != null && <p>M₁₂ = {formatSI(m.M12_H, 'H', 6)}</p>}
              {m.M21_H != null && <p>M₂₁ = {formatSI(m.M21_H, 'H', 6)}</p>}
              {m.reciprocity_relative != null && (
                <p className={m.reciprocity_ok ? 'text-ok' : 'text-danger'}>
                  {t(m.reciprocity_ok ? 'faraday.reciprocityOk' : 'faraday.reciprocityFail', { rel: m.reciprocity_relative.toExponential(1) })}
                </p>
              )}
              {m.reason && <p className="font-sans text-muted">{loc(m.reason)}</p>}
            </div>
          ))}
          <p className="text-[11px] leading-snug text-muted">{t('faraday.mutualNote')}</p>
        </div>
      )}
    </div>
  )
}

function ConventionRow() {
  const { t } = useT()
  const c = useViewStore((s) => s.velocityConvention)
  return (
    <Row label={t('motion.convention')} hint={t('motion.conventionHint')}>
      <Select<'undefined' | 'left' | 'right'>
        label={t('motion.convention')}
        value={c}
        onChange={(v) => useViewStore.getState().set({ velocityConvention: v })}
        options={(['undefined', 'left', 'right'] as const).map((v) => ({ value: v, label: t(`motion.conv.${v}` as MessageKey) }))}
      />
    </Row>
  )
}

function History({ id }: { id: string }) {
  const { t } = useT()
  const points = useInductionHistory((s) => s.bySurface[id])
  const now = useViewStore((s) => s.timeS)
  return (
    <div className="mt-1">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{t('motion.waveforms')}</h4>
      <Waveforms points={points ?? []} now={now} />
    </div>
  )
}

export function FaradayPanel({ induction, stale, error }: { induction: InductionData | undefined; stale: boolean; error: Error | null }) {
  const { t, loc } = useT()
  const surfaces = useSceneStore((s) => s.fluxSurfaces)
  const selectedId = useSceneStore((s) => s.selectedFluxId)
  const selected = surfaces.find((p) => p.id === selectedId)
  const results = new Map((induction?.surfaces ?? []).map((r) => [r.surface_id, r]))
  const add = (kind: FluxKind) => useSceneStore.getState().addFlux(kind, `${t(kind === 'sliding_rod' ? 'rod.name' : (`ampere.kind.${kind}` as MessageKey))} ${surfaces.length + 1}`)
  const selectedResult = selected ? results.get(selected.id) : undefined
  return (
    <div>
      <Section title={t('faraday.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('faraday.intro')}</p>
        <div className="flex flex-wrap gap-1">
          {KINDS.map(({ kind, icon: Icon }) => (
            <Button key={kind} variant="primary" onClick={() => add(kind)}>
              <Icon size={12} /> {t(kind === 'sliding_rod' ? 'rod.add' : (`ampere.kind.${kind}` as MessageKey))}
            </Button>
          ))}
        </div>
        {surfaces.length === 0 ? (
          <p className="text-xs text-muted">{t('faraday.none')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t('faraday.list')}>
            {surfaces.map((p) => {
              const r = results.get(p.id)
              const d = pathDisplayOf(p)
              return (
                <li key={p.id} className={cn('flex items-center gap-1 rounded px-1.5 py-1', p.id === selectedId ? 'bg-accent/15' : 'hover:bg-panel-2')}>
                  <button type="button" aria-pressed={p.id === selectedId} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => useSceneStore.getState().selectFlux(p.id)}>
                    <span className="truncate">{p.name || p.id}</span>
                    <span className="ml-auto shrink-0">{r ? <Badge tone={FARADAY_TONE[r.status]}>{t(`faraday.status.${r.status}` as MessageKey)}</Badge> : '…'}</span>
                  </button>
                  <Button variant="ghost" size="icon" aria-label={t('ampere.toggleVisible', { name: p.name || p.id })} onClick={() => useSceneStore.getState().setFluxDisplay(p.id, { visible: !d.visible })}>
                    {d.visible ? <Eye size={13} /> : <EyeOff size={13} />}
                  </Button>
                  <Button variant="danger" size="icon" aria-label={t('ampere.delete', { name: p.name || p.id })} onClick={() => useSceneStore.getState().removeFlux(p.id)}>
                    <Trash2 size={13} />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
        {error && <p className="text-xs text-danger">{error.message}</p>}
        {surfaces.some((f) => !!f.motion || f.shape.type === 'sliding_rod') && <ConventionRow />}
        {selectedResult && <SurfaceResultView r={selectedResult} stale={stale} />}
        {selected && selectedResult?.moving && <History id={selected.id} />}
        {induction && surfaces.length > 0 && <p className="text-[11px] leading-snug text-muted">{loc(induction.method)}</p>}
      </Section>
      {selected && selected.shape.type === 'sliding_rod' && <RodEditor key={selected.id} f={selected} />}
      {selected && selected.shape.type !== 'sliding_rod' && (
        <>
          <PathEditor key={selected.id} p={selected as AmperePath} ops={FLUX_OPS} title={t('faraday.edit', { name: selected.name || selected.id })} crossings={false} />
          <MotionEditor f={selected} />
        </>
      )}
      <Section title={t('faraday.aboutTitle')}>
        <p className="text-[11px] leading-snug text-muted">{t('faraday.about')}</p>
      </Section>
    </div>
  )
}
