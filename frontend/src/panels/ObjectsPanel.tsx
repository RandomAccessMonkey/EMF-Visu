import { useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, Box, Circle, CircleDot, Copy, Cylinder, Eye, EyeOff, Donut, Magnet, Minus, Plus, Square, Trash2, Waves, Zap } from 'lucide-react'
import { api } from '@/api/client'
import type { Preset, PrimitiveType, SceneObject, TestCharge, Vec3 } from '@/api/types'
import { Badge, Button, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatSI } from '@/lib/format'
import { chargeOf, currentOf, dipoleInfo, magnetizationOf, useSceneStore, type NewObjectKind } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'
import { MAGNET_COLOR, MAGNETIC_SOURCE_COLOR } from '@/render/magneticColors'

const GEOMETRY: { kind: Exclude<PrimitiveType, 'point' | 'group' | 'coil' | 'torus'>; icon: typeof Box }[] = [
  { kind: 'sphere', icon: Circle },
  { kind: 'box', icon: Box },
  { kind: 'cylinder', icon: Cylinder },
  { kind: 'ring', icon: Circle },
  { kind: 'plane', icon: Square },
  { kind: 'line', icon: Minus },
]

/** Load a preset (or one of its variants) and apply its view hint (display only). */
function loadPreset(p: Preset, scene: NonNullable<Preset['scene']>) {
  useSceneStore.getState().load(scene, { presetId: p.id, presetScene: scene })
  // A preset's Ampère paths (Phase 3B) replace the current ones; presets without paths keep them.
  if (p.ampere_paths.length > 0) useSceneStore.getState().setPaths(p.ampere_paths)
  // Phase 4A: a preset's measurement surfaces replace the current ones, and its time range sets
  // the playback (identical initial parameters reproduce identical results).
  // Phase 4B/4C experiment presets (a test charge or passive circuits) define the complete
  // setup: their measurement surfaces replace the current ones even when they have none.
  const experiment = !!p.test_charge || p.circuits.length > 0 || p.eddy_disks.length > 0
  if (p.flux_surfaces.length > 0 || experiment) useSceneStore.getState().setFluxSurfaces(p.flux_surfaces)
  // Phase 4B/4C: the test charge, passive circuits and eddy disks belong to the preset's
  // physical setup: they are replaced (and cleared when the preset has none), so a heavy
  // trajectory or circuit solve of one preset never runs against another preset's sources.
  useSceneStore.getState().setTestCharge((p.test_charge as TestCharge | null | undefined) ?? null)
  useSceneStore.getState().setCircuits(p.circuits)
  useSceneStore.getState().setDisks(p.eddy_disks)
  const hint = p.view_hint
  const time = p.time
  useViewStore.getState().set({
    playing: false,
    ...(time ? { timeStart: time.start_s, timeEnd: time.end_s, timeStep: time.step_s, timeS: time.initial_s } : {}),
    probePoint: (hint?.probe_m as Vec3 | null | undefined) ?? null,
    ...(hint?.mode ? { mode: hint.mode } : {}),
    ...(hint?.plane ? { plane: hint.plane, offset: 0 } : {}),
  })
}

function Variants({ p }: { p: Preset }) {
  const { t, loc } = useT()
  const scene = useSceneStore((s) => s.presetScene)
  if (p.variants.length === 0) return null
  return (
    <div className="mt-1.5 flex flex-wrap gap-1" role="group" aria-label={t('preset.variants')}>
      {p.variants.map((v) => (
        <Button key={v.id} variant={JSON.stringify(scene) === JSON.stringify(v.scene) ? 'primary' : 'ghost'} title={loc(v.description)} onClick={() => loadPreset(p, v.scene)}>
          {loc(v.name)}
        </Button>
      ))}
    </div>
  )
}

function Presets() {
  const { t, loc } = useT()
  const presets = useQuery({ queryKey: ['presets'], queryFn: api.presets, staleTime: Infinity })
  const presetId = useSceneStore((s) => s.presetId)
  const beginner = useViewStore((s) => s.level === 'beginner')
  const presetScene = useSceneStore((s) => s.presetScene)
  if (presets.isError) return <p className="text-xs text-danger">{t('error.api')}</p>
  const active = presets.data?.find((p) => p.id === presetId)
  const variant = active?.variants.find((v) => JSON.stringify(v.scene) === JSON.stringify(presetScene))
  return (
    <>
      <ul className="flex flex-col gap-0.5">
        {presets.data?.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              disabled={!p.available}
              title={p.available ? loc(p.description) : t('preset.unavailable', { phase: p.planned_phase ?? '—' })}
              onClick={() => p.scene && loadPreset(p, p.scene)}
              className={cn(
                'flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs',
                p.available ? 'hover:bg-panel-2' : 'cursor-not-allowed text-muted/60',
                p.id === presetId && 'bg-accent/15 text-accent',
              )}
            >
              <span className="truncate">
                <span className="mr-1.5 font-mono text-[10px] text-muted">{String(p.number).padStart(2, '0')}</span>
                {loc(p.name)}
              </span>
              {!p.available && <Badge tone="muted">{t('preset.phase', { phase: p.planned_phase ?? '—' })}</Badge>}
            </button>
            {p.id === presetId && <Variants p={p} />}
          </li>
        ))}
      </ul>
      {active && beginner && (
        <div className="rounded-md border border-accent/25 bg-accent/5 p-2 text-xs leading-relaxed text-text/90">
          <p>{loc(variant?.description ?? active.description)}</p>
          <p className="mt-1 text-muted">
            <span className="font-semibold text-accent-2">{t('preset.expected')}: </span>
            {loc(variant?.expected_behavior ?? active.expected_behavior)}
          </p>
        </div>
      )}
    </>
  )
}

const SHORT: Record<NonNullable<SceneObject['source']>['type'], MessageKey> = {
  point_charge: 'objects.charge',
  infinite_wire: 'objects.wireShort',
  circular_loop: 'objects.loopShort',
  solenoid: 'objects.solenoidShort',
  toroid_finite: 'objects.toroidShort',
  toroid_ideal: 'objects.toroidIdealShort',
  permanent_magnet: 'objects.magnet',
}

/** Marks of a time-dependent current (Phase 4A) in the object list. */
const PROFILE_MARK = { sinusoidal: '∿', ramp: '⟋', piecewise_linear: '⟋⟍' } as const

function ObjectRow({ o, depth }: { o: SceneObject; depth: number }) {
  const { t } = useT()
  const selected = useSceneStore((s) => s.selectedId === o.id)
  const scene = useSceneStore((s) => s.scene)
  const children = scene.objects.filter((c) => c.parent_id === o.id)
  // Derived from the scene on every render: selectors must not return fresh objects.
  const dipole = o.primitive.type === 'group' ? dipoleInfo(scene, o.id) : null
  const { select, update, remove, duplicate } = useSceneStore.getState()
  const q = chargeOf(o)
  const current = currentOf(o)
  const magnetization = magnetizationOf(o)
  const profile = o.source && 'profile' in o.source && o.source.profile && o.source.profile.type !== 'constant' ? o.source.profile.type : null
  const turns = o.primitive.type === 'coil' || o.primitive.type === 'torus' ? o.primitive.turns : 1
  const label = o.name || o.id
  const isGroup = o.primitive.type === 'group'
  const summary = isGroup
    ? dipole?.balanced
      ? `±${formatSI(dipole.charge_C, 'C')} · d = ${formatSI(dipole.separation_m, 'm')}`
      : t('primitive.group')
    : q !== undefined
      ? formatSI(q, 'C')
      : current !== undefined
        ? `${turns > 1 ? `${turns}×` : ''}${profile ? `${PROFILE_MARK[profile]} I(t)` : formatSI(current, 'A')} · ${t(SHORT[o.source!.type])}`
        : magnetization !== undefined
          ? `M = ${formatSI(magnetization, 'A/m')}`
          : t(`primitive.${o.primitive.type}` as MessageKey)
  return (
    <>
      <li
        className={cn(
          'group flex items-center gap-1 rounded px-1.5 py-1',
          selected ? 'bg-accent/15' : 'hover:bg-panel-2',
          !o.enabled && 'opacity-50',
        )}
        style={{ marginLeft: depth * 14 }}
      >
        <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => select(o.id)} aria-pressed={selected}>
          {isGroup ? (
            <ArrowLeftRight size={11} className="shrink-0 text-accent-2" />
          ) : current !== undefined ? (
            <Zap size={11} className="shrink-0" style={{ color: MAGNETIC_SOURCE_COLOR }} />
          ) : magnetization !== undefined ? (
            <Magnet size={11} className="shrink-0" style={{ color: MAGNET_COLOR }} />
          ) : (
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: q === undefined ? '#7c8db0' : q > 0 ? '#ff7a59' : q < 0 ? '#4aa8ff' : '#9aa7bd' }}
            />
          )}
          <span className="truncate">{label}</span>
          <span className="ml-auto shrink-0 font-mono text-[10px] text-muted">{summary}</span>
        </button>
        <Button variant="ghost" size="icon" aria-label={t(o.enabled ? 'objects.disable' : 'objects.enable', { name: label })} title={t(o.enabled ? 'objects.disable' : 'objects.enable', { name: label })} onClick={() => update(o.id, { enabled: !o.enabled })}>
          {o.enabled ? <Eye size={13} /> : <EyeOff size={13} />}
        </Button>
        {!isGroup && depth === 0 && (
          <Button variant="ghost" size="icon" aria-label={t('objects.duplicate', { name: label })} title={t('objects.duplicate', { name: label })} onClick={() => duplicate(o.id, `${label} ′`)}>
            <Copy size={13} />
          </Button>
        )}
        <Button variant="danger" size="icon" aria-label={t('objects.delete', { name: label })} title={t('objects.delete', { name: label })} onClick={() => remove(o.id)}>
          <Trash2 size={13} />
        </Button>
      </li>
      {children.map((c) => (
        <ObjectRow key={c.id} o={c} depth={depth + 1} />
      ))}
    </>
  )
}

export function ObjectsPanel() {
  const { t } = useT()
  const objects = useSceneStore((s) => s.scene.objects)
  const add = (kind: NewObjectKind, key: MessageKey) =>
    useSceneStore.getState().add(kind, `${t(key)} ${useSceneStore.getState().scene.objects.length + 1}`)
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <Section title={t('objects.title')}>
        <div className="flex gap-1.5">
          <Button variant="primary" className="flex-1" onClick={() => add('positive_charge', 'objects.charge')}>
            <Plus size={13} /> {t('objects.addPositive')}
          </Button>
          <Button variant="primary" className="flex-1" onClick={() => add('negative_charge', 'objects.charge')}>
            <Minus size={13} /> {t('objects.addNegative')}
          </Button>
        </div>
        <div className="flex gap-1.5">
          <Button className="flex-1" onClick={() => add('wire', 'objects.wire')} title={t('objects.addWireHint')}>
            <Zap size={13} /> {t('objects.addWire')}
          </Button>
          <Button className="flex-1" onClick={() => add('loop', 'objects.loop')} title={t('objects.addLoopHint')}>
            <CircleDot size={13} /> {t('objects.addLoop')}
          </Button>
        </div>
        <div className="flex gap-1.5">
          <Button className="flex-1" onClick={() => add('solenoid', 'objects.solenoid')} title={t('objects.addSolenoidHint')}>
            <Waves size={13} /> {t('objects.solenoid')}
          </Button>
          <Button className="flex-1" onClick={() => add('toroid', 'objects.toroid')} title={t('objects.addToroidHint')}>
            <Donut size={13} /> {t('objects.toroid')}
          </Button>
          <Button className="flex-1" onClick={() => add('magnet', 'objects.magnet')} title={t('objects.addMagnetHint')}>
            <Magnet size={13} /> {t('objects.magnet')}
          </Button>
        </div>
        <Button onClick={() => useSceneStore.getState().addDipole(`${t('objects.dipole')} ${objects.filter((o) => o.primitive.type === 'group').length + 1}`)} title={t('objects.addDipoleHint')}>
          <ArrowLeftRight size={13} /> {t('objects.addDipole')}
        </Button>
        <div>
          <p className="mb-1 text-[11px] text-muted" title={t('objects.inertHint')}>
            {t('objects.addGeometry')}
          </p>
          <div className="flex flex-wrap gap-1">
            {GEOMETRY.map(({ kind, icon: Icon }) => (
              <Button key={kind} onClick={() => add(kind, `primitive.${kind}` as MessageKey)} title={t('objects.inertHint')}>
                <Icon size={12} /> {t(`primitive.${kind}` as MessageKey)}
              </Button>
            ))}
          </div>
        </div>
        {objects.length === 0 ? (
          <p className="text-xs text-muted">{t('objects.empty')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {objects.filter((o) => !o.parent_id).map((o) => (
              <ObjectRow key={o.id} o={o} depth={0} />
            ))}
          </ul>
        )}
      </Section>
      <Section title={t('presets.title')}>
        <Presets />
      </Section>
    </div>
  )
}
