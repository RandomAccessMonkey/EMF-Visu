import type { Role, SceneObject, Vec3 } from '@/api/types'
import { NumberField, Row, Section, Select, Slider } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { useSceneStore } from '@/state/sceneStore'
import { useViewStore } from '@/state/viewStore'

const AXES = ['x', 'y', 'z'] as const
const DEG = Math.PI / 180
const UNSUPPORTED_ROLES: Role[] = ['conductor', 'dielectric', 'magnetic_material', 'current_source']

function VecRows(props: { value: Vec3; onChange: (v: Vec3) => void; unit: string; factor?: number; prefix: string; step?: number; nonZero?: boolean }) {
  return (
    <>
      {AXES.map((axis, i) => (
        <Row key={axis} label={`${props.prefix} ${axis}`}>
          <NumberField
            label={`${props.prefix} ${axis}`}
            value={props.value[i]!}
            unit={props.unit}
            factor={props.factor}
            step={props.step}
            onChange={(v) => {
              if (props.nonZero && v === 0) return
              const next = [...props.value] as Vec3
              next[i] = v
              props.onChange(next)
            }}
          />
        </Row>
      ))}
    </>
  )
}

function Dimensions({ o }: { o: SceneObject }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  const p = o.primitive
  const num = (label: MessageKey, value: number, apply: (v: number) => SceneObject['primitive']) => (
    <Row key={label} label={t(label)}>
      <NumberField label={t(label)} value={value} unit="m" min={1e-6} step={0.05} onChange={(v) => update(o.id, { primitive: apply(v) })} />
    </Row>
  )
  switch (p.type) {
    case 'point':
      return null
    case 'sphere':
    case 'ring':
      return num('dim.radius', p.radius_m, (v) => ({ ...p, radius_m: v }))
    case 'cylinder':
      return (
        <>
          {num('dim.radius', p.radius_m, (v) => ({ ...p, radius_m: v }))}
          {num('dim.height', p.height_m, (v) => ({ ...p, height_m: v }))}
        </>
      )
    case 'plane':
      return (
        <>
          {num('dim.width', p.width_m, (v) => ({ ...p, width_m: v }))}
          {num('dim.height', p.height_m, (v) => ({ ...p, height_m: v }))}
        </>
      )
    case 'line':
      return num('dim.length', p.length_m, (v) => ({ ...p, length_m: v }))
    case 'box':
      return (
        <>
          {AXES.map((axis, i) =>
            num(`dim.size_${axis}` as MessageKey, p.size_m[i]!, (v) => {
              const size = [...p.size_m] as Vec3
              size[i] = v
              return { ...p, size_m: size }
            }),
          )}
        </>
      )
  }
}

function ObjectParameters({ o }: { o: SceneObject }) {
  const { t } = useT()
  const { update, setTransform } = useSceneStore.getState()
  const advanced = useViewStore((s) => s.level === 'advanced')
  const source = o.source
  return (
    <>
      <Section title={t('params.object')}>
        <Row label={t('params.name')}>
          <input
            aria-label={t('params.name')}
            value={o.name}
            onChange={(e) => update(o.id, { name: e.target.value })}
            className="h-7 w-36 rounded-md border border-border bg-bg px-1.5 text-xs"
          />
        </Row>
        <Row label={t('params.role')} hint={t('params.roleHint')}>
          {source ? (
            <span className="text-xs">{t('role.charge_source')}</span>
          ) : (
            <Select<Role>
              label={t('params.role')}
              value={o.role}
              onChange={(role) => update(o.id, { role })}
              options={[
                { value: 'geometry_only', label: t('role.geometry_only') },
                ...UNSUPPORTED_ROLES.map((r) => ({
                  value: r,
                  label: `${t(`role.${r}` as MessageKey)} — ${t('role.unsupported')}`,
                  disabled: true,
                })),
              ]}
            />
          )}
        </Row>
        {!source && <p className="text-[11px] leading-snug text-warn/90">{t('params.inertNote')}</p>}
      </Section>
      {source && (
        <Section title={t('params.electrical')}>
          <Row label={`${t('params.charge')} q`} hint={t('params.chargeHint')}>
            <Slider label={t('params.charge')} value={source.charge_C / 1e-9} min={-10} max={10} step={0.1} onChange={(v) => update(o.id, { source: { ...source, charge_C: v * 1e-9 } })} />
            <NumberField label={t('params.charge')} value={source.charge_C} factor={1e-9} unit="nC" step={0.1} onChange={(v) => update(o.id, { source: { ...source, charge_C: v } })} />
          </Row>
          <p className="text-[11px] leading-snug text-muted">{t('params.chargeHint')}</p>
        </Section>
      )}
      <Section title={t('params.transform')}>
        <VecRows prefix={t('params.position')} unit="m" step={0.1} value={o.transform.position_m} onChange={(v) => setTransform(o.id, { position_m: v })} />
        {(advanced || !source) && (
          <>
            <VecRows prefix={t('params.rotation')} unit="°" factor={DEG} step={5} value={o.transform.rotation_euler_xyz_rad} onChange={(v) => setTransform(o.id, { rotation_euler_xyz_rad: v })} />
            <VecRows prefix={t('params.scale')} unit="×" step={0.1} nonZero value={o.transform.scale} onChange={(v) => setTransform(o.id, { scale: v })} />
          </>
        )}
        {advanced && <p className="text-[11px] text-muted">{t('params.rotationNote')}</p>}
      </Section>
      {o.primitive.type !== 'point' && (
        <Section title={t('params.dimensions')}>
          <Dimensions o={o} />
        </Section>
      )}
    </>
  )
}

function DomainParameters() {
  const { t } = useT()
  const domain = useSceneStore((s) => s.scene.domain)
  const setDomain = useSceneStore((s) => s.setDomain)
  return (
    <Section title={t('params.domain')}>
      <p className="text-[11px] leading-snug text-muted">{t('params.domainHint')}</p>
      {AXES.map((axis, i) => (
        <Row key={axis} label={`${axis} min / max`}>
          <NumberField
            label={`${axis} min`}
            value={domain.min_m[i]!}
            step={0.5}
            max={domain.max_m[i]! - 0.01}
            onChange={(v) => {
              const min = [...domain.min_m] as Vec3
              min[i] = v
              setDomain({ ...domain, min_m: min })
            }}
          />
          <NumberField
            label={`${axis} max`}
            value={domain.max_m[i]!}
            unit="m"
            step={0.5}
            min={domain.min_m[i]! + 0.01}
            onChange={(v) => {
              const max = [...domain.max_m] as Vec3
              max[i] = v
              setDomain({ ...domain, max_m: max })
            }}
          />
        </Row>
      ))}
      <Row label={t('params.medium')}>
        <span className="text-xs">{t('params.vacuum')}</span>
      </Row>
      <Row label={t('params.reference')}>
        <span className="text-xs">φ(∞) = 0 V</span>
      </Row>
    </Section>
  )
}

export function ParametersPanel() {
  const { t } = useT()
  const selected = useSceneStore((s) => s.scene.objects.find((o) => o.id === s.selectedId))
  return (
    <div>
      {selected ? <ObjectParameters o={selected} /> : <p className="border-b border-border px-3 py-3 text-xs text-muted">{t('params.nothingSelected')}</p>}
      <DomainParameters />
    </div>
  )
}
