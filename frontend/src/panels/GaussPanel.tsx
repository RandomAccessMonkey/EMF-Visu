import { useQuery } from '@tanstack/react-query'
import { Box, Circle, Cylinder, Eye, EyeOff, Square, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import type { GaussSurface, Vec3 } from '@/api/types'
import { Badge, Button, NumberField, Row, Section, Select, Slider, Switch } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatSI } from '@/lib/format'
import { explanationFacts, surfaceResult, type FluxData } from '@/sim/gauss'
import { displayOf, useSceneStore, type SurfaceKind } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { fluxText, QualityBadge } from './FluxResults'

const KINDS: { kind: SurfaceKind; icon: typeof Box }[] = [
  { kind: 'sphere', icon: Circle },
  { kind: 'cube', icon: Square },
  { kind: 'box', icon: Box },
  { kind: 'cylinder', icon: Cylinder },
]
const AXES = ['x', 'y', 'z'] as const
const DEG = Math.PI / 180

function VecRows({ label, value, onChange, unit, factor, step }: { label: string; value: Vec3; onChange: (v: Vec3) => void; unit: string; factor?: number; step: number }) {
  return (
    <>
      {AXES.map((a, i) => (
        <Row key={a} label={`${label} ${a}`}>
          <NumberField label={`${label} ${a}`} value={value[i]!} unit={unit} factor={factor} step={step} onChange={(v) => {
            const next = [...value] as Vec3
            next[i] = v
            onChange(next)
          }} />
        </Row>
      ))}
    </>
  )
}

function Dimensions({ s }: { s: GaussSurface }) {
  const { t } = useT()
  const update = (shape: GaussSurface['shape']) => useSceneStore.getState().updateSurface(s.id, { shape })
  const num = (key: MessageKey, value: number, apply: (v: number) => GaussSurface['shape']) => (
    <Row key={key} label={t(key)}>
      <NumberField label={t(key)} value={value} unit="m" min={1e-3} step={0.05} onChange={(v) => update(apply(v))} />
    </Row>
  )
  const sh = s.shape
  switch (sh.type) {
    case 'sphere':
      return num('dim.radius', sh.radius_m, (v) => ({ ...sh, radius_m: v }))
    case 'cube':
      return num('dim.side', sh.side_m, (v) => ({ ...sh, side_m: v }))
    case 'box':
      return (
        <>
          {AXES.map((a, i) =>
            num(`dim.size_${a}` as MessageKey, sh.size_m[i]!, (v) => {
              const size = [...sh.size_m] as Vec3
              size[i] = v
              return { ...sh, size_m: size }
            }),
          )}
        </>
      )
    case 'cylinder':
      return (
        <>
          {num('dim.radius', sh.radius_m, (v) => ({ ...sh, radius_m: v }))}
          {num('dim.height', sh.height_m, (v) => ({ ...sh, height_m: v }))}
        </>
      )
    case 'mesh':
      return <p className="text-[11px] text-muted">{t('gauss.customMesh')}</p>
  }
}

function SurfaceEditor({ s }: { s: GaussSurface }) {
  const { t } = useT()
  const { updateSurface, setSurfaceDisplay } = useSceneStore.getState()
  const selectedCell = useViewStore((v) => v.selectedCell)
  const display = displayOf(s)
  const sub = s.subdivision
  const canSubdivide = s.shape.type === 'box' || s.shape.type === 'cube'
  return (
    <>
      <Section title={t('gauss.geometry')}>
        <Row label={t('params.name')}>
          <input aria-label={t('gauss.surfaceName')} value={s.name} onChange={(e) => updateSurface(s.id, { name: e.target.value })} className="h-7 w-36 rounded-md border border-border bg-bg px-1.5 text-xs" />
        </Row>
        <VecRows label={t('gauss.centre')} unit="m" step={0.1} value={s.center_m} onChange={(center_m) => updateSurface(s.id, { center_m })} />
        {s.shape.type !== 'sphere' && (
          <VecRows label={t('params.rotation')} unit="°" factor={DEG} step={5} value={s.rotation_euler_xyz_rad} onChange={(rotation_euler_xyz_rad) => updateSurface(s.id, { rotation_euler_xyz_rad })} />
        )}
        <Dimensions s={s} />
        {s.shape.type === 'cylinder' && <p className="text-[11px] text-muted">{t('gauss.cylinderAxis')}</p>}
      </Section>
      <Section title={t('gauss.orientation')}>
        <Row label={t('flux.orientation')}>
          <span className="text-xs">{t(s.orientation === 'outward' ? 'flux.outward' : 'flux.inward')}</span>
          <Button aria-label={t('gauss.reverse')} onClick={() => updateSurface(s.id, { orientation: s.orientation === 'outward' ? 'inward' : 'outward' })}>{t('gauss.reverse')}</Button>
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('gauss.reverseHint')}</p>
      </Section>
      {canSubdivide && (
        <Section title={t('gauss.subdivision')}>
          <Row label={t('gauss.subdivide')}>
            <Switch label={t('gauss.subdivide')} checked={sub != null} onChange={(on) => {
              updateSurface(s.id, { subdivision: on ? [4, 4, 4] : null })
              useViewStore.getState().set({ selectedCell: on ? 0 : null })
            }} />
          </Row>
          {sub && (
            <>
              {AXES.map((a, i) => (
                <Row key={a} label={t('gauss.cellsAlong', { axis: a })}>
                  <Select label={t('gauss.cellsAlong', { axis: a })} value={String(sub[i])} onChange={(v) => {
                    const next = [...sub] as [number, number, number]
                    next[i] = Number(v)
                    updateSurface(s.id, { subdivision: next })
                    useViewStore.getState().set({ selectedCell: 0 })
                  }} options={[1, 2, 3, 4, 5, 6, 7, 8].map((n) => ({ value: String(n), label: String(n) }))} />
                </Row>
              ))}
              <Row label={t('gauss.cellToInspect')}>
                <Slider label={t('gauss.cellToInspect')} value={selectedCell ?? 0} min={0} max={sub[0] * sub[1] * sub[2] - 1} step={1} onChange={(c) => useViewStore.getState().set({ selectedCell: c })} />
                <span className="w-10 text-right font-mono text-[11px] text-muted">
                  {(() => {
                    const c = selectedCell ?? 0
                    return `${Math.floor(c / (sub[1] * sub[2]))},${Math.floor(c / sub[2]) % sub[1]},${c % sub[2]}`
                  })()}
                </span>
              </Row>
              <p className="text-[11px] leading-snug text-muted">{t('gauss.subdivisionHint')}</p>
            </>
          )}
        </Section>
      )}
      <Section title={t('gauss.display')}>
        <Row label={t('gauss.visible')}>
          <Switch label={t('gauss.visible')} checked={display.visible} onChange={(visible) => setSurfaceDisplay(s.id, { visible })} />
        </Row>
        <Row label={t('gauss.opacity')}>
          <Slider label={t('gauss.opacity')} value={display.opacity} min={0.05} max={0.9} step={0.05} onChange={(opacity) => setSurfaceDisplay(s.id, { opacity })} />
        </Row>
        <Row label={t('gauss.normals')}>
          <Switch label={t('gauss.normals')} checked={display.show_normals} onChange={(show_normals) => setSurfaceDisplay(s.id, { show_normals })} />
        </Row>
        <Row label={t('gauss.colorByFlux')}>
          <Switch label={t('gauss.colorByFlux')} checked={display.color_by_flux} onChange={(color_by_flux) => setSurfaceDisplay(s.id, { color_by_flux })} />
        </Row>
        <p className="text-[11px] leading-snug text-muted">{t('gauss.patchHint')}</p>
      </Section>
    </>
  )
}

/** A guided explanation built from the computed result for the selected surface. */
function Explanation({ flux }: { flux: FluxData | undefined }) {
  const { t } = useT()
  const id = useSceneStore((s) => s.selectedSurfaceId ?? s.surfaces[0]?.id ?? null)
  const objects = useSceneStore((s) => s.scene.objects)
  const s = surfaceResult(flux, id)
  if (!s || s.status === 'invalid') return null
  const f = explanationFacts(s)
  const names = Object.fromEntries(objects.map((o) => [o.id, o.name || o.id]))
  const lines: string[] = []
  if (f.status === 'boundary_ambiguous') lines.push(t('explain.boundary', { n: f.nboundary }))
  else {
    lines.push(t('explain.enclosed', { npos: f.npos, nneg: f.nneg, q: formatSI(f.qenc, 'C') }))
    lines.push(t(f.sign > 0 ? 'explain.flux' : 'explain.fluxInward', { phi: formatSI(f.flux ?? 0, 'V·m'), vol: formatSI(f.volume ?? 0, 'V·m') }))
    if (f.qenc === 0 && f.npos + f.nneg > 0) lines.push(t('explain.cancel'))
    if (f.nexternal > 0) lines.push(t('explain.external', { n: f.nexternal, net: formatSI(f.externalNet, 'V·m') }))
    if (f.nearIds.length > 0) lines.push(t('explain.near', { names: f.nearIds.map((x) => names[x] ?? x).join(', ') }))
    if (f.npos + f.nneg === 0 && f.nexternal === 0) lines.push(t('explain.empty'))
  }
  lines.push(t('explain.local'))
  return (
    <div className="rounded-md border border-accent/30 bg-accent/5 p-2 text-xs leading-relaxed" data-testid="gauss-explanation" aria-live="polite">
      {lines.map((l, i) => (
        <p key={i} className={i > 0 ? 'mt-1' : ''}>{l}</p>
      ))}
    </div>
  )
}

export function GaussPanel({ flux }: { flux: FluxData | undefined }) {
  const { t, loc } = useT()
  const surfaces = useSceneStore((s) => s.surfaces)
  const selectedId = useSceneStore((s) => s.selectedSurfaceId)
  const situations = useQuery({ queryKey: ['gauss-situations'], queryFn: api.gaussSituations, staleTime: Infinity })
  const selected = surfaces.find((s) => s.id === selectedId)
  const add = (kind: SurfaceKind) => useSceneStore.getState().addSurface(kind, `${t(`shape.${kind}` as MessageKey)} ${surfaces.length + 1}`)
  return (
    <div>
      <Section title={t('gauss.title')}>
        <p className="text-[11px] leading-snug text-muted">{t('gauss.intro')}</p>
        <div className="flex flex-wrap gap-1">
          {KINDS.map(({ kind, icon: Icon }) => (
            <Button key={kind} variant="primary" onClick={() => add(kind)}>
              <Icon size={12} /> {t(`shape.${kind}` as MessageKey)}
            </Button>
          ))}
        </div>
        {surfaces.length === 0 ? (
          <p className="text-xs text-muted">{t('gauss.none')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5" aria-label={t('gauss.list')}>
            {surfaces.map((s) => {
              const r = surfaceResult(flux, s.id)
              const d = displayOf(s)
              return (
                <li key={s.id} className={cn('flex items-center gap-1 rounded px-1.5 py-1', s.id === selectedId ? 'bg-accent/15' : 'hover:bg-panel-2')}>
                  <button type="button" aria-pressed={s.id === selectedId} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => useSceneStore.getState().selectSurface(s.id)}>
                    <span className="truncate">{s.name || s.id}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-muted">
                      {r?.status === 'ok' ? `Φ_E = ${fluxText(r.flux_E_V_m, r.flux_E_uncertainty_V_m, 'V·m', t)}` : r?.status === 'boundary_ambiguous' ? t('flux.undefined') : r?.status === 'invalid' ? t('flux.invalidShort') : '…'}
                    </span>
                  </button>
                  <Button variant="ghost" size="icon" aria-label={t('gauss.toggleVisible', { name: s.name || s.id })} onClick={() => useSceneStore.getState().setSurfaceDisplay(s.id, { visible: !d.visible })}>
                    {d.visible ? <Eye size={13} /> : <EyeOff size={13} />}
                  </Button>
                  <Button variant="danger" size="icon" aria-label={t('gauss.delete', { name: s.name || s.id })} onClick={() => useSceneStore.getState().removeSurface(s.id)}>
                    <Trash2 size={13} />
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
        {flux && surfaces.length > 0 && (
          <div className="flex items-center gap-2 text-[11px] text-muted">
            <QualityBadge flux={flux} /> {t(flux.header.quality === 'final' ? 'flux.finalNote' : 'flux.previewNote')}
          </div>
        )}
        <Explanation flux={flux} />
      </Section>
      {selected && <SurfaceEditor key={selected.id} s={selected} />}
      <Section title={t('gauss.situations')}>
        <p className="text-[11px] leading-snug text-muted">{t('gauss.situationsIntro')}</p>
        <ul className="flex flex-col gap-0.5">
          {situations.data?.map((sit) => (
            <li key={sit.id}>
              <button
                type="button"
                title={loc(sit.description)}
                className="flex w-full items-start gap-1.5 rounded px-2 py-1 text-left text-xs hover:bg-panel-2"
                onClick={() => {
                  useSceneStore.getState().load(sit.scene, {})
                  useSceneStore.getState().setSurfaces(sit.surfaces)
                  useViewStore.getState().set({ selectedPatch: null, selectedCell: null, probePoint: null })
                }}
              >
                <span className="font-mono text-[10px] text-muted">{String(sit.number).padStart(2, '0')}</span>
                <span>
                  {loc(sit.name)}
                  <span className="block text-[11px] text-muted">{loc(sit.expectation)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <Badge tone="muted">{t('gauss.twoD')}</Badge>
      </Section>
    </div>
  )
}
