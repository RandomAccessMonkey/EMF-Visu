// Ampère's law: closed planar paths, the numerical circulation of H along each (from the
// engine) and, independently, the signed free current through the spanning surface. Every
// number shown comes from the engine's response; the panel only formats and explains it.
import { Circle, Eye, EyeOff, Pentagon, Plus, Square, Trash2 } from 'lucide-react'
import { useMemo } from 'react'
import type { AmperePath, PathResult, Vec3 } from '@/api/types'
import { Badge, Button, NumberField, Row, Section, Select, Switch } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatPlain, formatSI } from '@/lib/format'
import type { AmpereData } from '@/sim/useAmpere'
import { pathDisplayOf, useSceneStore, type PathKind } from '@/state/sceneStore'

const KINDS: { kind: PathKind; icon: typeof Circle }[] = [
  { kind: 'circle', icon: Circle },
  { kind: 'rectangle', icon: Square },
  { kind: 'polygon', icon: Pentagon },
]
const AXES = ['x', 'y', 'z'] as const
const DEG = Math.PI / 180
const RTOLS = ['1e-3', '1e-4', '1e-6', '1e-8'] as const

type Tone = 'ok' | 'warn' | 'muted' | 'danger' | 'accent'
export const STATUS_TONE: Record<PathResult['status'], Tone> = {
  verified: 'ok',
  not_converged: 'warn',
  ambiguous: 'warn',
  intersects_source: 'warn',
  unsupported: 'muted',
  failed: 'danger',
  invalid: 'danger',
}

function VecRows({ label, value, onChange, unit, factor, step }: { label: string; value: Vec3; onChange: (v: Vec3) => void; unit: string; factor?: number; step: number }) {
  return (
    <>
      {AXES.map((a, i) => (
        <Row key={a} label={`${label} ${a}`}>
          <NumberField
            label={`${label} ${a}`}
            value={value[i]!}
            unit={unit}
            factor={factor}
            step={step}
            onChange={(v) => {
              const next = [...value] as Vec3
              next[i] = v
              onChange(next)
            }}
          />
        </Row>
      ))}
    </>
  )
}

function ShapeEditor({ p }: { p: AmperePath }) {
  const { t } = useT()
  const set = (shape: AmperePath['shape']) => useSceneStore.getState().updatePath(p.id, { shape })
  const sh = p.shape
  const num = (key: MessageKey, value: number, apply: (v: number) => AmperePath['shape']) => (
    <Row key={key} label={t(key)}>
      <NumberField label={t(key)} value={value} unit="m" min={1e-6} step={0.01} onChange={(v) => set(apply(v))} />
    </Row>
  )
  if (sh.type === 'circle') return num('dim.radius', sh.radius_m, (v) => ({ ...sh, radius_m: v }))
  if (sh.type === 'rectangle')
    return (
      <>
        {num('dim.width', sh.width_m, (v) => ({ ...sh, width_m: v }))}
        {num('dim.height', sh.height_m, (v) => ({ ...sh, height_m: v }))}
      </>
    )
  const verts = sh.vertices_m
  const setVert = (i: number, axis: 0 | 1, v: number) => {
    const next = verts.map((x) => [...x] as Vec3)
    next[i]![axis] = v
    set({ ...sh, vertices_m: next })
  }
  return (
    <>
      <p className="text-[11px] leading-snug text-muted">{t('ampere.polygonHint')}</p>
      {verts.map((v, i) => (
        <Row key={i} label={`P${i + 1} (x, y)`}>
          <NumberField label={`P${i + 1} x`} value={v[0]} step={0.01} onChange={(x) => setVert(i, 0, x)} />
          <NumberField label={`P${i + 1} y`} value={v[1]} unit="m" step={0.01} onChange={(y) => setVert(i, 1, y)} />
          <Button variant="ghost" size="icon" aria-label={t('ampere.removeVertex', { n: i + 1 })} disabled={verts.length <= 3} onClick={() => set({ ...sh, vertices_m: verts.filter((_, k) => k !== i) })}>
            <Trash2 size={12} />
          </Button>
        </Row>
      ))}
      <Button
        disabled={verts.length >= 64}
        onClick={() => {
          // New vertex halfway along the closing edge (last → first).
          const a = verts[verts.length - 1]!
          const b = verts[0]!
          set({ ...sh, vertices_m: [...verts, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, a[2]]] })
        }}
      >
        <Plus size={12} /> {t('ampere.addVertex')}
      </Button>
    </>
  )
}

function PathEditor({ p }: { p: AmperePath }) {
  const { t } = useT()
  const { updatePath, setPathDisplay } = useSceneStore.getState()
  const d = pathDisplayOf(p)
  return (
    <Section title={t('ampere.edit', { name: p.name || p.id })}>
      <Row label={t('params.name')}>
        <input aria-label={t('params.name')} value={p.name} onChange={(e) => updatePath(p.id, { name: e.target.value })} className="h-7 w-36 rounded-md border border-border bg-bg px-1.5 text-xs" />
      </Row>
      <ShapeEditor p={p} />
      <VecRows label={t('params.position')} value={p.center_m} unit="m" step={0.01} onChange={(v) => updatePath(p.id, { center_m: v })} />
      <VecRows label={t('params.rotation')} value={p.rotation_euler_xyz_rad} unit="°" factor={DEG} step={15} onChange={(v) => updatePath(p.id, { rotation_euler_xyz_rad: v })} />
      <Row label={t('ampere.orientation')} hint={t('ampere.orientationHint')}>
        <Button aria-label={t(p.reversed ? 'ampere.reversed' : 'ampere.forward')} onClick={() => updatePath(p.id, { reversed: !p.reversed })}>
          {t(p.reversed ? 'ampere.reversed' : 'ampere.forward')}
        </Button>
      </Row>
      <Row label={t('ampere.rtol')} hint={t('ampere.rtolHint')}>
        <Select<(typeof RTOLS)[number]>
          label={t('ampere.rtol')}
          value={(RTOLS.find((r) => Number(r) === p.rtol) ?? '1e-4') as (typeof RTOLS)[number]}
          onChange={(v) => updatePath(p.id, { rtol: Number(v) })}
          options={RTOLS.map((r) => ({ value: r, label: r }))}
        />
      </Row>
      <Row label={t('ampere.showNormal')}>
        <Switch label={t('ampere.showNormal')} checked={d.show_normal} onChange={(v) => setPathDisplay(p.id, { show_normal: v })} />
      </Row>
      <Row label={t('ampere.showCrossings')}>
        <Switch label={t('ampere.showCrossings')} checked={d.show_crossings} onChange={(v) => setPathDisplay(p.id, { show_crossings: v })} />
      </Row>
      <Row label={t('ampere.showSurface')}>
        <Switch label={t('ampere.showSurface')} checked={d.show_surface} onChange={(v) => setPathDisplay(p.id, { show_surface: v })} />
      </Row>
    </Section>
  )
}

const amps = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatSI(v, 'A', 5))

/** The engine's result for one path, with a short explanation of what it means. */
export function PathResultView({ r, stale }: { r: PathResult; stale: boolean }) {
  const { t, loc } = useT()
  // Select the stable array, derive the map: a selector must not return a fresh object.
  const objects = useSceneStore((s) => s.scene.objects)
  const names = useMemo(() => Object.fromEntries(objects.map((o) => [o.id, o.name || o.id])), [objects])
  const enc = r.enclosure
  // One line per object, sign and state (a 24-turn toroid gives one line, not 24).
  const groups = useMemo(() => {
    const out = new Map<string, { key: string; object_id: string; state: string; sign: number; current_A: number; count: number; total_A: number }>()
    for (const c of enc?.crossings ?? []) {
      const key = `${c.object_id}|${c.state}|${c.sign}|${c.current_A}`
      const g = out.get(key) ?? { key, object_id: c.object_id, state: c.state, sign: c.sign, current_A: c.current_A, count: 0, total_A: 0 }
      g.count += 1
      g.total_A += c.contribution_A
      out.set(key, g)
    }
    return [...out.values()]
  }, [enc])
  return (
    <div className={cn('flex flex-col gap-1 text-xs', stale && 'opacity-60')} data-testid="ampere-result" aria-live="polite">
      <div className="flex items-center gap-2">
        <Badge tone={STATUS_TONE[r.status]}>{t(`ampere.status.${r.status}` as MessageKey)}</Badge>
        {stale && <span className="text-[11px] text-muted">{t('ampere.stale')}</span>}
      </div>
      {r.invalid_reasons.map((x, i) => (
        <p key={i} className="text-[11px] text-danger">{loc(x)}</p>
      ))}
      {r.valid && (
        <table className="w-full font-mono text-[11px]">
          <tbody>
            {r.circulation_H_A !== null && r.circulation_H_A !== undefined && (
              <tr>
                <td className="pr-2 text-muted">∮H·dl</td>
                <td>{amps(r.circulation_H_A)} ± {formatSI(r.circulation_error_A ?? 0, 'A', 2)}</td>
              </tr>
            )}
            <tr>
              <td className="pr-2 text-muted">I_free,enc</td>
              <td>{enc?.available ? amps(enc.value_A) : t(`ampere.enclosure.${enc?.status ?? 'unsupported'}` as MessageKey)}</td>
            </tr>
            {r.difference_A !== null && r.difference_A !== undefined && (
              <tr>
                <td className="pr-2 text-muted">{t('ampere.difference')}</td>
                <td>{formatSI(r.difference_A, 'A', 2)} {r.tolerance_A ? `(${t('ampere.tolerance')} ${formatSI(r.tolerance_A, 'A', 2)})` : ''}</td>
              </tr>
            )}
            {r.circulation_B_T_m !== null && r.circulation_B_T_m !== undefined && (
              <tr>
                <td className="pr-2 text-muted">∮B·dl</td>
                <td>{formatSI(r.circulation_B_T_m, 'T·m', 5)}</td>
              </tr>
            )}
            {r.bound_current_from_B_A !== null && r.bound_current_from_B_A !== undefined && (
              <tr>
                <td className="pr-2 text-muted">{t('ampere.bound')}</td>
                <td>{amps(r.bound_current_from_B_A)}</td>
              </tr>
            )}
            <tr>
              <td className="pr-2 text-muted">{t('ampere.geometry')}</td>
              <td>
                {r.perimeter_m !== null && r.perimeter_m !== undefined ? formatSI(r.perimeter_m, 'm', 4) : '—'} · {r.area_m2 !== null && r.area_m2 !== undefined ? formatPlain(r.area_m2, 'm²', 4) : '—'}
              </td>
            </tr>
            {r.subintervals !== null && r.subintervals !== undefined && (
              <tr>
                <td className="pr-2 text-muted">{t('ampere.quadrature')}</td>
                <td>{t('ampere.quadratureValue', { n: r.subintervals, ev: r.evaluations ?? 0 })}</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {groups.length > 0 && (
        <ul className="text-[11px]" aria-label={t('ampere.crossings')}>
          {groups.map((g) => (
            <li key={g.key} className="font-mono">
              {g.state !== 'inside' ? '⚠' : g.sign > 0 ? '↑' : '↓'} {names[g.object_id] ?? g.object_id}: {g.count > 1 ? `${g.count} × ` : ''}
              {g.sign > 0 ? '+' : g.sign < 0 ? '−' : '±'}
              {formatSI(Math.abs(g.current_A), 'A')} → {amps(g.total_A)}
            </li>
          ))}
        </ul>
      )}
      {enc?.notes.map((n, i) => (
        <p key={i} className="text-[11px] leading-snug text-warn/90">{loc(n)}</p>
      ))}
      {r.near_singular && <p className="text-[11px] leading-snug text-warn/90">{t('ampere.nearSingular', { d: formatSI(r.min_distance_to_filament_m ?? 0, 'm') })}</p>}
      {r.crosses_material && <p className="text-[11px] leading-snug text-muted">{t('ampere.crossesMaterial')}</p>}
      <p className="text-[11px] leading-snug text-muted">{t(`ampere.explain.${r.status}` as MessageKey)}</p>
    </div>
  )
}

export function AmperePanel({ ampere, stale, error }: { ampere: AmpereData | undefined; stale: boolean; error: Error | null }) {
  const { t, loc } = useT()
  const paths = useSceneStore((s) => s.paths)
  const selectedId = useSceneStore((s) => s.selectedPathId)
  const selected = paths.find((p) => p.id === selectedId)
  const results = new Map((ampere?.paths ?? []).map((r) => [r.path_id, r]))
  const add = (kind: PathKind) => useSceneStore.getState().addPath(kind, `${t(`ampere.kind.${kind}` as MessageKey)} ${paths.length + 1}`)
  const selectedResult = selected ? results.get(selected.id) : undefined
  return (
    <div>
      <Section title={t('ampere.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('ampere.intro')}</p>
        <div className="flex flex-wrap gap-1">
          {KINDS.map(({ kind, icon: Icon }) => (
            <Button key={kind} variant="primary" onClick={() => add(kind)}>
              <Icon size={12} /> {t(`ampere.kind.${kind}` as MessageKey)}
            </Button>
          ))}
        </div>
        {paths.length === 0 ? (
          <p className="text-xs text-muted">{t('ampere.none')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t('ampere.list')}>
            {paths.map((p) => {
              const r = results.get(p.id)
              const d = pathDisplayOf(p)
              return (
                <li key={p.id} className={cn('flex items-center gap-1 rounded px-1.5 py-1', p.id === selectedId ? 'bg-accent/15' : 'hover:bg-panel-2')}>
                  <button type="button" aria-pressed={p.id === selectedId} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => useSceneStore.getState().selectPath(p.id)}>
                    <span className="truncate">{p.name || p.id}</span>
                    <span className="ml-auto shrink-0">{r ? <Badge tone={STATUS_TONE[r.status]}>{t(`ampere.status.${r.status}` as MessageKey)}</Badge> : '…'}</span>
                  </button>
                  <Button variant="ghost" size="icon" aria-label={t('ampere.toggleVisible', { name: p.name || p.id })} onClick={() => useSceneStore.getState().setPathDisplay(p.id, { visible: !d.visible })}>
                    {d.visible ? <Eye size={13} /> : <EyeOff size={13} />}
                  </Button>
                  <Button variant="danger" size="icon" aria-label={t('ampere.delete', { name: p.name || p.id })} onClick={() => useSceneStore.getState().removePath(p.id)}>
                    <Trash2 size={13} />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
        {error && <p className="text-xs text-danger">{error.message}</p>}
        {selectedResult && <PathResultView r={selectedResult} stale={stale} />}
        {ampere && paths.length > 0 && <p className="text-[11px] leading-snug text-muted">{loc(ampere.method)}</p>}
      </Section>
      {selected && <PathEditor key={selected.id} p={selected} />}
      <Section title={t('ampere.aboutTitle')}>
        <p className="text-[11px] leading-snug text-muted">{t('ampere.about')}</p>
      </Section>
    </div>
  )
}
