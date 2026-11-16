import { useQuery } from '@tanstack/react-query'
import { Box, Circle, Copy, Cylinder, Eye, EyeOff, Minus, Plus, Square, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import type { PrimitiveType, SceneObject } from '@/api/types'
import { Badge, Button, Section } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { cn, formatSI } from '@/lib/format'
import { useSceneStore, type NewObjectKind } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const GEOMETRY: { kind: Exclude<PrimitiveType, 'point'>; icon: typeof Box }[] = [
  { kind: 'sphere', icon: Circle },
  { kind: 'box', icon: Box },
  { kind: 'cylinder', icon: Cylinder },
  { kind: 'ring', icon: Circle },
  { kind: 'plane', icon: Square },
  { kind: 'line', icon: Minus },
]

function Presets() {
  const { t, loc } = useT()
  const presets = useQuery({ queryKey: ['presets'], queryFn: api.presets, staleTime: Infinity })
  const presetId = useSceneStore((s) => s.presetId)
  const load = useSceneStore((s) => s.load)
  const beginner = useViewStore((s) => s.level === 'beginner')
  if (presets.isError) return <p className="text-xs text-danger">{t('error.api')}</p>
  const active = presets.data?.find((p) => p.id === presetId)
  return (
    <>
      <ul className="flex flex-col gap-0.5">
        {presets.data?.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              disabled={!p.available}
              title={p.available ? loc(p.description) : t('preset.unavailable', { phase: p.planned_phase ?? '—' })}
              onClick={() => {
                if (!p.scene) return
                load(p.scene, { presetId: p.id })
                useViewStore.getState().set({ probePoint: null })
              }}
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
          </li>
        ))}
      </ul>
      {active && beginner && (
        <div className="rounded-md border border-accent/25 bg-accent/5 p-2 text-xs leading-relaxed text-text/90">
          <p>{loc(active.description)}</p>
          <p className="mt-1 text-muted">
            <span className="font-semibold text-accent-2">{t('preset.expected')}: </span>
            {loc(active.expected_behavior)}
          </p>
        </div>
      )}
    </>
  )
}

function ObjectRow({ o }: { o: SceneObject }) {
  const { t } = useT()
  const selected = useSceneStore((s) => s.selectedId === o.id)
  const { select, update, remove, duplicate } = useSceneStore.getState()
  const q = o.source?.charge_C
  const label = o.name || o.id
  return (
    <li
      className={cn(
        'group flex items-center gap-1 rounded px-1.5 py-1',
        selected ? 'bg-accent/15' : 'hover:bg-panel-2',
        !o.enabled && 'opacity-50',
      )}
    >
      <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => select(o.id)} aria-pressed={selected}>
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: q === undefined || q === null ? '#7c8db0' : q > 0 ? '#ff7a59' : q < 0 ? '#4aa8ff' : '#9aa7bd' }}
        />
        <span className="truncate">{label}</span>
        <span className="ml-auto shrink-0 font-mono text-[10px] text-muted">
          {q !== undefined && q !== null ? formatSI(q, 'C') : t(`primitive.${o.primitive.type}` as MessageKey)}
        </span>
      </button>
      <Button variant="ghost" size="icon" aria-label={t(o.enabled ? 'objects.disable' : 'objects.enable', { name: label })} title={t(o.enabled ? 'objects.disable' : 'objects.enable', { name: label })} onClick={() => update(o.id, { enabled: !o.enabled })}>
        {o.enabled ? <Eye size={13} /> : <EyeOff size={13} />}
      </Button>
      <Button variant="ghost" size="icon" aria-label={t('objects.duplicate', { name: label })} title={t('objects.duplicate', { name: label })} onClick={() => duplicate(o.id, `${label} ′`)}>
        <Copy size={13} />
      </Button>
      <Button variant="danger" size="icon" aria-label={t('objects.delete', { name: label })} title={t('objects.delete', { name: label })} onClick={() => remove(o.id)}>
        <Trash2 size={13} />
      </Button>
    </li>
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
            {objects.map((o) => (
              <ObjectRow key={o.id} o={o} />
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
