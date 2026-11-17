// Parameter editors for the Phase 3B sources: finite solenoid, finite-turn and ideal toroid,
// uniformly magnetized cylinder. Geometry-derived numbers (turn spacing, turns per metre) are
// computed here; every field value shown (ideal comparisons, magnetic moment) comes from the
// engine's source table in the magnetic result header.
import type { CurrentSourceInfo, SceneObject } from '@/api/types'
import { Button, NumberField, Row, Section, Select, Slider } from '@/components/ui/controls'
import { useT } from '@/i18n'
import { formatPlain, formatSI } from '@/lib/format'
import { MU0_INPUT_CONVERSION } from '@/lib/units'
import { toroidWithModel, useSceneStore, type MagnetSource, type ToroidSource } from '@/state/sceneStore'

type Coil = Extract<SceneObject['primitive'], { type: 'coil' }>
type Torus = Extract<SceneObject['primitive'], { type: 'torus' }>
type Cylinder = Extract<SceneObject['primitive'], { type: 'cylinder' }>

const note = (text: string, warn = false) => <p className={warn ? 'text-[11px] leading-snug text-warn/90' : 'text-[11px] leading-snug text-muted'}>{text}</p>

/** Turn positions are derived: N turns spread evenly over the winding length L (first to last
 *  turn), spacing L/(N−1); a single turn sits at the centre and L is not used. */
export function CoilDimensions({ o, p, info }: { o: SceneObject; p: Coil; info?: CurrentSourceInfo }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  const set = (patch: Partial<Coil>) => update(o.id, { primitive: { ...p, ...patch } })
  const single = p.turns === 1
  const spacing = single ? null : p.length_m / (p.turns - 1)
  const ideal = info?.ideal_long_solenoid
  return (
    <>
      <Row label={`${t('coil.turns')} N`}>
        <NumberField
          label={t('coil.turns')}
          value={p.turns}
          min={1}
          max={2000}
          step={1}
          onChange={(v) => {
            const turns = Math.round(v)
            // More than one turn needs a winding length; restore a sensible one if it was 0.
            set({ turns, ...(turns > 1 && !(p.length_m > 0) ? { length_m: 5 * p.radius_m } : {}) })
          }}
        />
      </Row>
      <Row label={`${t('coil.radius')} a`}>
        <NumberField label={t('coil.radius')} value={p.radius_m} unit="m" min={1e-6} step={0.01} onChange={(v) => set({ radius_m: v })} />
      </Row>
      <Row label={`${t('coil.length')} L`} hint={t('coil.lengthHint')}>
        <NumberField label={t('coil.length')} value={p.length_m} unit="m" min={single ? 0 : 1e-6} step={0.01} disabled={single} onChange={(v) => set({ length_m: v })} />
      </Row>
      {single ? (
        note(t('coil.singleTurn'))
      ) : (
        <>
          <Row label={`${t('coil.spacing')} Δz`} hint={t('coil.spacingHint')}>
            <span className="font-mono text-xs">{formatSI(spacing!, 'm')}</span>
          </Row>
          <Row label={`${t('coil.density')} n = N/L`}>
            <span className="font-mono text-xs">{formatPlain(p.turns / p.length_m, 'm⁻¹')}</span>
          </Row>
        </>
      )}
      {ideal && !single && (
        <div className="rounded-md border border-border/70 p-1.5">
          <p className="text-[11px] font-semibold text-muted">{t('coil.idealTitle')}</p>
          <p className="font-mono text-[11px]">B ≈ μ₀nI = {formatSI(ideal.B_T, 'T')}</p>
          <p className="font-mono text-[11px]">H ≈ nI = {formatSI(ideal.H_A_per_m, 'A/m')}</p>
          {note(t('coil.idealNote'))}
        </div>
      )}
      {note(t('coil.modelNote'))}
    </>
  )
}

/** Both radii are stored: the winding radius belongs to the finite-turn model, the core radius
 *  to the ideal one; switching the model never overwrites the other radius. */
export function TorusDimensions({ o, p }: { o: SceneObject; p: Torus }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  const set = (patch: Partial<Torus>) => update(o.id, { primitive: { ...p, ...patch } })
  const ideal = o.source?.type === 'toroid_ideal'
  const minor = ideal ? p.core_radius_m : p.winding_radius_m
  const invalid = !(p.major_radius_m > minor)
  // Arc length between neighbouring turns at the inner edge of the winding (geometry).
  const innerGap = (2 * Math.PI * (p.major_radius_m - p.winding_radius_m)) / p.turns
  return (
    <>
      <Row label={`${t('torus.turns')} N`}>
        <NumberField label={t('torus.turns')} value={p.turns} min={1} max={5000} step={1} onChange={(v) => set({ turns: Math.round(v) })} />
      </Row>
      <Row label={`${t('torus.major')} R`} hint={t('torus.majorHint')}>
        <NumberField label={t('torus.major')} value={p.major_radius_m} unit="m" min={1e-6} step={0.01} onChange={(v) => set({ major_radius_m: v })} />
      </Row>
      <Row label={`${t('torus.winding')} b`} hint={t('torus.windingHint')}>
        <NumberField label={t('torus.winding')} value={p.winding_radius_m} unit="m" min={1e-6} step={0.005} onChange={(v) => set({ winding_radius_m: v })} />
      </Row>
      <Row label={`${t('torus.core')} b꜀`} hint={t('torus.coreHint')}>
        <NumberField label={t('torus.core')} value={p.core_radius_m} unit="m" min={1e-6} step={0.005} onChange={(v) => set({ core_radius_m: v })} />
      </Row>
      {!ideal && (
        <Row label={t('torus.innerGap')} hint={t('torus.innerGapHint')}>
          <span className="font-mono text-xs">{formatSI(innerGap, 'm')}</span>
        </Row>
      )}
      {invalid && note(t('torus.invalid'), true)}
      {!ideal && !invalid && innerGap < 0.01 * p.winding_radius_m && note(t('torus.closeTurns'), true)}
      {note(t(ideal ? 'torus.usedIdeal' : 'torus.usedFinite'))}
    </>
  )
}

export function ToroidModel({ o, source }: { o: SceneObject; source: ToroidSource }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  return (
    <>
      <Row label={t('torus.model')} hint={t('torus.modelHint')}>
        <Select<ToroidSource['type']>
          label={t('torus.model')}
          value={source.type}
          onChange={(m) => update(o.id, { source: toroidWithModel(o, m).source })}
          options={[
            { value: 'toroid_finite', label: t('torus.finite') },
            { value: 'toroid_ideal', label: t('torus.ideal') },
          ]}
        />
      </Row>
      {source.type === 'toroid_ideal' && (
        <>
          <Row label={`${t('torus.mur')} μᵣ`} hint={t('torus.murHint')}>
            <NumberField label={t('torus.mur')} value={source.relative_permeability} min={1e-6} step={1} onChange={(v) => update(o.id, { source: { ...source, relative_permeability: v } })} />
          </Row>
          {note(t('torus.idealNote'))}
        </>
      )}
      {source.type === 'toroid_finite' && note(t('torus.finiteNote'))}
    </>
  )
}

/** Uniform magnetization along the cylinder axis (local +z). M is the stored parameter; the
 *  equivalent B_r = μ₀M is offered as an input in tesla (a parameterization, not a B–H curve). */
export function MagnetParameters({ o, source, info }: { o: SceneObject; source: MagnetSource; info?: CurrentSourceInfo }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  const canReset = useSceneStore((s) => !!s.presetScene?.objects.some((x) => x.id === o.id))
  const resetToPreset = useSceneStore((s) => s.resetToPreset)
  const setM = (magnetization_A_per_m: number) => update(o.id, { source: { ...source, magnetization_A_per_m } })
  const M = source.magnetization_A_per_m
  const moment = info?.moment_A_m2
  return (
    <Section title={t('magnet.title')}>
      <Row label={`${t('magnet.M')} M`} hint={t('magnet.MHint')}>
        <Slider label={t('magnet.M')} value={Math.max(-1.5e6, Math.min(1.5e6, M)) / 1e5} min={-15} max={15} step={0.1} onChange={(v) => setM(v * 1e5)} />
        <NumberField label={t('magnet.M')} value={M} factor={1e3} unit="kA/m" step={10} onChange={setM} />
      </Row>
      <Row label={`${t('magnet.Br')} Bᵣ = μ₀M`} hint={t('magnet.BrHint')}>
        <NumberField label={t('magnet.Br')} value={M * MU0_INPUT_CONVERSION} unit="T" step={0.05} onChange={(v) => setM(v / MU0_INPUT_CONVERSION)} />
      </Row>
      <Row label={t('params.direction')}>
        <span className="font-mono text-xs">{M > 0 ? '+z' : M < 0 ? '−z' : '0'}</span>
        <Button aria-label={t('magnet.reverse')} onClick={() => setM(-M)} title={t('magnet.reverseHint')}>
          {t('magnet.reverse')}
        </Button>
      </Row>
      {moment && (
        <Row label={`${t('magnet.moment')} m = Mπa²L`}>
          <span className="font-mono text-xs">{formatSI(Math.hypot(...moment), 'A·m²')}</span>
        </Row>
      )}
      {note(t('magnet.note'))}
      {canReset && (
        <Button onClick={() => resetToPreset(o.id)} title={t('params.resetHint')}>
          {t('params.reset')}
        </Button>
      )}
    </Section>
  )
}

export function MagnetDimensions({ o, p }: { o: SceneObject; p: Cylinder }) {
  const { t } = useT()
  const update = useSceneStore((s) => s.update)
  return (
    <>
      <Row label={`${t('dim.radius')} a`}>
        <NumberField label={t('dim.radius')} value={p.radius_m} unit="m" min={1e-6} step={0.005} onChange={(v) => update(o.id, { primitive: { ...p, radius_m: v } })} />
      </Row>
      <Row label={`${t('magnet.length')} L`}>
        <NumberField label={t('magnet.length')} value={p.height_m} unit="m" min={1e-6} step={0.005} onChange={(v) => update(o.id, { primitive: { ...p, height_m: v } })} />
      </Row>
    </>
  )
}
