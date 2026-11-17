import type { ReactNode } from 'react'
import type { SurfaceFlux } from '@/api/types'
import { Badge, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { formatNumber, formatPlain, formatSI, formatVector, prettyUnit } from '@/lib/format'
import { surfaceResult, type FluxData } from '@/sim/gauss'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

type ValueClass = SurfaceFlux['value_classes'][string]
const CLASS_TONE: Record<ValueClass, 'ok' | 'accent' | 'warn' | 'muted' | 'danger'> = {
  exact_analytical: 'ok',
  exact_for_represented_mesh: 'accent',
  numerical_approximation: 'warn',
  numerical_diagnostic: 'muted',
  undefined: 'danger',
}

export function ClassBadge({ c }: { c: ValueClass | undefined }) {
  const { t } = useT()
  if (!c) return null
  return <Badge tone={CLASS_TONE[c]}>{t(`vclass.${c}` as MessageKey)}</Badge>
}

function Row({ label, value, cls, hint }: { label: ReactNode; value: ReactNode; cls?: ValueClass; hint?: string }) {
  return (
    <tr className="border-t border-border/60 align-top" title={hint}>
      <td className="py-1 pr-2 text-muted">{label}</td>
      <td className="py-1 text-right font-mono">{value}</td>
      <td className="py-1 pl-2 text-right">
        <ClassBadge c={cls} />
      </td>
    </tr>
  )
}

/** A flux value, marked "≈ 0" when it is smaller than its own floating-point uncertainty (the
 *  raw value is still shown; it is never replaced by zero). */
export function fluxText(value: number | null | undefined, unc: number | null | undefined, unit: string, t: (k: MessageKey) => string): string {
  if (value == null) return t('flux.undefined')
  if (unc != null && value !== 0 && Math.abs(value) <= unc) return `${formatNumber(value, 3)} ${unit} ${t('flux.roundOffZero')}`
  return formatSI(value, unit, 6)
}

export function QualityBadge({ flux }: { flux: FluxData }) {
  const { t } = useT()
  return flux.header.quality === 'final' ? <Badge tone="ok">{t('flux.final')}</Badge> : <Badge tone="warn">{t('flux.preview')}</Badge>
}

/** Results for the selected Gaussian surface (or the first one). */
export function FluxResults({ flux }: { flux: FluxData | undefined }) {
  const { t, loc } = useT()
  const surfaces = useSceneStore((s) => s.surfaces)
  const selectedSurfaceId = useSceneStore((s) => s.selectedSurfaceId)
  const selectedCharge = useSceneStore((s) => s.selectedId)
  const objects = useSceneStore((s) => s.scene.objects)
  const patch = useViewStore((s) => s.selectedPatch)
  const cell = useViewStore((s) => s.selectedCell)
  const advanced = useViewStore((s) => s.level === 'advanced')
  if (surfaces.length === 0) return null
  const id = selectedSurfaceId ?? surfaces[0]!.id
  const s = surfaceResult(flux, id)
  const surface = surfaces.find((x) => x.id === id)
  const names = Object.fromEntries(objects.map((o) => [o.id, o.name || o.id]))
  if (!flux || !s || !surface) return <Section title={t('flux.title')}><p className="text-xs text-muted">{t('common.loading')}</p></Section>
  const vc = s.value_classes
  const m = s.mesh
  const sign = s.orientation_sign
  const arrays = (name: string) => flux.result.arrays[`surf${s.index}.${name}`]?.data
  return (
    <Section title={t('flux.title')} aside={<QualityBadge flux={flux} />}>
      <p className="text-xs">
        <span className="font-semibold">{surface.name || surface.id}</span>{' '}
        <span className="text-muted">· {t(`shape.${surface.shape.type}` as MessageKey)} · {t(s.orientation === 'outward' ? 'flux.outward' : 'flux.inward')}</span>
      </p>
      {flux.header.quality === 'preview' && <p className="text-[11px] text-warn">{t('flux.previewNote')}</p>}
      {s.status === 'invalid' && (
        <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-2 text-xs">
          <p className="font-semibold text-danger">{t('flux.invalid')}</p>
          <ul className="list-disc pl-4">
            {s.errors.map((e, i) => (
              <li key={i}>{loc(e)}</li>
            ))}
          </ul>
        </div>
      )}
      {s.status === 'boundary_ambiguous' && (
        <p role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-2 text-xs text-danger">
          {t('flux.ambiguous')}
        </p>
      )}
      {s.enclosed && (
        <table className="w-full text-[11px]" aria-label={t('flux.table')}>
          <tbody>
            <Row label="Φ_E = ∮ E·dA" value={fluxText(s.flux_E_V_m, s.flux_E_uncertainty_V_m, 'V·m', t)} cls={vc['flux']} hint={t('flux.surfaceHint')} />
            <Row label="Φ_D = ∮ D·dA" value={fluxText(s.flux_D_C, s.flux_D_uncertainty_C, 'C', t)} cls={vc['flux']} />
            <Row label={t('flux.qenc')} value={formatSI(s.enclosed.total_C, 'C', 4)} cls={vc['enclosed_charge']} />
            <Row label={t('flux.qpos')} value={`${s.enclosed.positive_count} · ${formatSI(s.enclosed.positive_C, 'C')}`} />
            <Row label={t('flux.qneg')} value={`${s.enclosed.negative_count} · ${formatSI(s.enclosed.negative_C, 'C')}`} />
            <Row label={t('flux.external')} value={s.enclosed.external_count} />
            <Row label={t('flux.boundary')} value={s.enclosed.boundary_count} />
            <Row label={t('flux.volumeE')} value={s.volume_integral_E_V_m == null ? t('flux.undefined') : formatSI(s.volume_integral_E_V_m, 'V·m', 6)} cls={vc['volume_integral']} hint={t('flux.volumeHint')} />
            <Row label={t('flux.volumeD')} value={s.volume_integral_D_C == null ? t('flux.undefined') : formatSI(s.volume_integral_D_C, 'C', 6)} cls={vc['volume_integral']} />
            <Row label={t('flux.difference', { s: sign > 0 ? '' : '−' })} value={s.difference_E_V_m == null ? t('flux.undefined') : `${formatNumber(s.difference_E_V_m, 3)} V·m`} />
            <Row label={t('flux.uncertainty')} value={s.flux_E_uncertainty_V_m == null ? '—' : `± ${formatNumber(s.flux_E_uncertainty_V_m, 2)} V·m`} cls={vc['uncertainty']} />
            <Row label={t('flux.orientation')} value={t(s.orientation === 'outward' ? 'flux.outward' : 'flux.inward')} />
          </tbody>
        </table>
      )}
      {s.enclosed && <p className="text-[11px] leading-snug text-muted">{t(sign > 0 ? 'flux.compareNote' : 'flux.compareNoteInward')}</p>}
      {m && (
        <div className="rounded-md border border-border bg-panel-2/50 p-2 text-[11px]">
          <div className="mb-1 flex items-center gap-1.5">
            <span className="font-semibold">{t('flux.mesh')}</span>
            <ClassBadge c={vc['mesh_geometry']} />
          </div>
          <p className="leading-snug">{t(m.representation === 'exact' ? 'flux.meshExact' : m.representation === 'custom' ? 'flux.meshCustom' : 'flux.meshApprox', { shape: t(`shape.${surface.shape.type}` as MessageKey) })}</p>
          <table className="mt-1 w-full font-mono">
            <tbody>
              <tr><td className="text-muted">{t('flux.resolution')}</td><td className="text-right">{m.resolution_id} · {m.triangles} △</td></tr>
              {m.max_deviation_m != null && m.representation !== 'exact' && (
                <tr><td className="text-muted">{t('flux.deviation')}</td><td className="text-right">{formatSI(m.max_deviation_m, 'm')}</td></tr>
              )}
              {m.ideal_area_m2 != null && m.representation !== 'exact' && (
                <tr><td className="text-muted">{t('flux.areaVsIdeal')}</td><td className="text-right">{formatPlain(m.area_m2, 'm²', 5)} / {formatPlain(m.ideal_area_m2, 'm²', 5)}</td></tr>
              )}
              <tr><td className="text-muted">{t('flux.tolerance')}</td><td className="text-right">{formatNumber(m.tolerance_m, 2)} m</td></tr>
              <tr><td className="text-muted">{t('flux.nearDistance')}</td><td className="text-right">{formatSI(m.near_boundary_m, 'm')}</td></tr>
            </tbody>
          </table>
          {m.representation === 'inscribed_polyhedron' && <p className="mt-1 leading-snug text-muted">{t('flux.geometryVsIntegration')}</p>}
          {s.ideal_shape_disagreement_ids.length > 0 && (
            <p className="mt-1 text-warn">{t('flux.idealDisagree', { names: s.ideal_shape_disagreement_ids.map((x) => names[x] ?? x).join(', ') })}</p>
          )}
        </div>
      )}
      {s.charges.length > 0 && (
        <div>
          <h4 className="mb-1 mt-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{t('flux.charges')}</h4>
          <table className="w-full text-[11px]" aria-label={t('flux.charges')}>
            <thead>
              <tr className="text-left text-muted">
                <th className="font-normal">{t('probe.source')}</th>
                <th className="font-normal">{t('flux.state')}</th>
                <th className="text-right font-normal">{t('flux.distance')}</th>
                <th className="text-right font-normal">Φ_E,i</th>
              </tr>
            </thead>
            <tbody>
              {s.charges.map((c) => (
                <tr key={c.object_id} className={`border-t border-border/60 ${c.object_id === selectedCharge ? 'bg-accent/10' : ''}`}>
                  <td className="max-w-20 truncate">{names[c.object_id] ?? c.object_id} <span className="text-muted">({formatSI(c.charge_C, 'C')})</span></td>
                  <td>
                    <Badge tone={c.state === 'inside' ? 'ok' : c.state === 'boundary' ? 'danger' : 'muted'}>{t(`state.${c.state}` as MessageKey)}</Badge>
                    {c.near_boundary && c.state !== 'boundary' && <span className="ml-1 text-warn">{t('state.near')}</span>}
                  </td>
                  <td className="text-right font-mono">{formatSI(c.signed_distance_m, 'm')}</td>
                  <td className="text-right font-mono">{c.flux_E_V_m == null ? '—' : formatSI(c.flux_E_V_m, 'V·m', 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] leading-snug text-muted">{t('flux.chargesNote')}</p>
        </div>
      )}
      {patch !== null && m && patch < m.triangles && (
        <PatchInspector flux={flux} s={s} patch={patch} names={names} arrays={arrays} />
      )}
      {s.subdivision && <SubdivisionResults s={s} cell={cell} names={names} />}
      {advanced && (
        <ul className="list-disc space-y-0.5 pl-4 text-[11px] leading-snug text-muted">
          <li>{loc(flux.header.surface_method)}</li>
          <li>{loc(flux.header.volume_method)}</li>
          <li>{loc(flux.header.local_sampling)}</li>
        </ul>
      )}
    </Section>
  )
}

function PatchInspector({ flux, s, patch, names, arrays }: { flux: FluxData; s: SurfaceFlux; patch: number; names: Record<string, string>; arrays: (n: string) => Float32Array | undefined }) {
  const { t } = useT()
  const v3 = (name: string) => {
    const a = arrays(name)
    return a ? [a[3 * patch]!, a[3 * patch + 1]!, a[3 * patch + 2]!] : [NaN, NaN, NaN]
  }
  const v1 = (name: string) => arrays(name)?.[patch] ?? NaN
  const en = v1('En')
  const emag = v1('Emag')
  const perCharge = arrays('charge_flux_E')
  const T = s.mesh!.triangles
  const approxZero = emag === 0 || Math.abs(en) <= flux.header.approx_zero_relative_threshold * emag
  return (
    <div className="rounded-md border border-white/30 bg-panel-2/60 p-2 text-[11px]" data-testid="patch-inspector">
      <p className="mb-1 font-semibold">{t('patch.title', { n: patch })}</p>
      <table className="w-full font-mono">
        <tbody>
          <tr><td className="font-sans text-muted">{t('patch.area')}</td><td className="text-right">{formatSI(v1('area'), 'm²', 4)}</td></tr>
          <tr><td className="font-sans text-muted">{t('patch.normal')}</td><td className="text-right">{formatVector(v3('normals'), 3)}</td></tr>
          <tr><td className="font-sans text-muted">|E| {t('patch.atCentroid')}</td><td className="text-right">{formatSI(emag, 'V/m', 4)}</td></tr>
          <tr>
            <td className="font-sans text-muted">E·n {t('patch.atCentroid')}</td>
            <td className="text-right">
              {formatSI(en, 'V/m', 4)} {approxZero && <span className="font-sans text-muted">({t('patch.approxZero')})</span>}
            </td>
          </tr>
          <tr><td className="font-sans text-muted">D·n {t('patch.atCentroid')}</td><td className="text-right">{formatSI(v1('Dn'), prettyUnit('C/m^2'), 4)}</td></tr>
          <tr><td className="font-sans text-muted">Φ_E,T ({t('patch.integrated')})</td><td className="text-right">{formatSI(v1('flux_E'), 'V·m', 5)}</td></tr>
        </tbody>
      </table>
      {perCharge && (
        <table className="mt-1 w-full font-mono" aria-label={t('patch.perCharge')}>
          <tbody>
            {s.charges.map((c, i) => (
              <tr key={c.object_id}>
                <td className="font-sans text-muted">{t('patch.from', { name: names[c.object_id] ?? c.object_id })}</td>
                <td className="text-right">{formatSI(perCharge[i * T + patch]!, 'V·m', 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-1 leading-snug text-muted">{t('patch.note')}</p>
    </div>
  )
}

function SubdivisionResults({ s, cell, names }: { s: SurfaceFlux; cell: number | null; names: Record<string, string> }) {
  const { t } = useT()
  const d = s.subdivision!
  const c = cell !== null && cell < d.cells.length ? d.cells[cell] : undefined
  return (
    <div className="rounded-md border border-accent-2/40 bg-accent-2/5 p-2 text-[11px]" data-testid="subdivision-results">
      <div className="mb-1 flex items-center gap-1.5">
        <span className="font-semibold">{t('cells.title', { n: d.n.join('×') })}</span>
        <Badge tone={d.status === 'ok' ? 'ok' : 'danger'}>{t(d.status === 'ok' ? 'cells.ok' : 'cells.ambiguous')}</Badge>
      </div>
      <table className="w-full font-mono">
        <tbody>
          <tr><td className="font-sans text-muted">{t('cells.shared')}</td><td className="text-right">{d.shared_faces}</td></tr>
          <tr><td className="font-sans text-muted">{t('cells.maxSharedSum')}</td><td className="text-right">{formatNumber(d.shared_face_max_abs_sum_E_V_m, 3)} V·m</td></tr>
          <tr><td className="font-sans text-muted">Σ Φ_cell</td><td className="text-right">{formatSI(d.sum_cell_flux_E_V_m, 'V·m', 6)}</td></tr>
          <tr><td className="font-sans text-muted">Φ_outer</td><td className="text-right">{d.outer_flux_E_V_m == null ? t('flux.undefined') : formatSI(d.outer_flux_E_V_m, 'V·m', 6)}</td></tr>
          <tr><td className="font-sans text-muted">{t('cells.fluxDiff')}</td><td className="text-right">{d.cell_flux_difference_E_V_m == null ? '—' : `${formatNumber(d.cell_flux_difference_E_V_m, 3)} V·m`}</td></tr>
          <tr><td className="font-sans text-muted">Σ ∫_cell ∇·E dV</td><td className="text-right">{d.sum_cell_volume_integral_E_V_m == null ? t('cells.ambiguousShort') : formatSI(d.sum_cell_volume_integral_E_V_m, 'V·m', 6)}</td></tr>
          <tr><td className="font-sans text-muted">∫_V ∇·E dV</td><td className="text-right">{d.parent_volume_integral_E_V_m == null ? t('flux.undefined') : formatSI(d.parent_volume_integral_E_V_m, 'V·m', 6)}</td></tr>
        </tbody>
      </table>
      {d.status === 'ambiguous' && <p className="mt-1 text-danger">{t('cells.ambiguousNote', { names: d.ambiguous_object_ids.map((x) => names[x] ?? x).join(', ') })}</p>}
      {c && (
        <div className="mt-1 border-t border-border/60 pt-1" data-testid="cell-results">
          <p className="font-semibold">{t('cells.cell', { ijk: c.index.join(', ') })}</p>
          <table className="w-full font-mono">
            <tbody>
              <tr><td className="font-sans text-muted">Φ_E</td><td className="text-right">{formatSI(c.flux_E_V_m, 'V·m', 5)}</td></tr>
              <tr><td className="font-sans text-muted">{t('flux.qenc')}</td><td className="text-right">{c.enclosed_C == null ? t('cells.ambiguousShort') : formatSI(c.enclosed_C, 'C')}</td></tr>
              <tr><td className="font-sans text-muted">∫ ∇·E dV</td><td className="text-right">{c.volume_integral_E_V_m == null ? t('cells.ambiguousShort') : formatSI(c.volume_integral_E_V_m, 'V·m', 5)}</td></tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-1 leading-snug text-muted">{t('cells.note')}</p>
    </div>
  )
}
