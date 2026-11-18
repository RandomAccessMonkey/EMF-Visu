// Legend of the coaxial TEM view: what each colour and glyph encodes, the arrow-length rule, and
// the instantaneous V, I and P at the inspected cross-section (engine values).
import { useT } from '@/i18n'
import { formatSI } from '@/lib/format'
import { COAX_E_COLOR, COAX_H_COLOR, COAX_S_COLOR } from '@/render/CoaxLayer'
import type { CoaxData } from '@/sim/coax'
import { useViewStore } from '@/state/viewStore'

const Chip = ({ color }: { color: string }) => <span className="mr-1 inline-block h-2 w-3 rounded-sm align-middle" style={{ background: color }} />

export function CoaxLegend({ coax }: { coax: CoaxData }) {
  const { t } = useT()
  const mode = useViewStore((s) => s.mode)
  const d = coax.data
  if (!coax.spec || coax.issues.length > 0) return null
  return (
    <div className="pointer-events-none absolute left-2 top-2 max-w-[24rem] rounded-lg bg-panel/85 px-3 py-2 text-[10px] leading-snug text-muted shadow-lg" data-testid="coax-legend">
      {d && (
        <div className="mb-1 font-mono text-[11px] text-text">
          t = {formatSI(d.t_s, 's', 4)} · z = {formatSI(d.z_m, 'm', 3)} · V = {formatSI(d.V, 'V', 3)} · I = {formatSI(d.I, 'A', 3)} · {t('coax.pInstShort')} = {formatSI(d.V * d.I, 'W', 3)}
        </div>
      )}
      <div><Chip color={COAX_E_COLOR} />{t('coax.legend.E')}</div>
      <div><Chip color={COAX_H_COLOR} />{t('coax.legend.H')}</div>
      <div><Chip color={COAX_S_COLOR} />{t(mode === '2d' ? 'coax.legend.S2d' : 'coax.legend.S3d')}</div>
      {mode === '3d' && (
        <div>
          <span className="mr-1 inline-block h-2 w-8 rounded-sm align-middle" style={{ background: 'linear-gradient(90deg,#60a5fa,#243047,#f87171)' }} />
          {t('coax.legend.V')}
        </div>
      )}
      <div>{t('coax.legend.length')}</div>
      <div>{t('coax.legend.scales')}</div>
      <div>{t('coax.legend.region')}</div>
    </div>
  )
}
