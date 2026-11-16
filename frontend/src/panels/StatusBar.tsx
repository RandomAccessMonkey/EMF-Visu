import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/controls'
import { useT } from '@/i18n'
import type { Simulation } from '@/sim/useSimulation'

export function StatusBar({ sim }: { sim: Simulation }) {
  const { t, loc } = useT()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 10_000, retry: false })
  const solvers = useQuery({ queryKey: ['solvers'], queryFn: api.solvers, refetchInterval: 10_000, retry: false })
  const h = health.data
  return (
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border bg-panel px-3 py-1 text-[11px] text-muted">
      <span className="flex items-center gap-1.5">
        {t('status.api')}
        <Badge tone={health.isError ? 'danger' : h ? 'ok' : 'muted'}>{health.isError ? t('status.offline') : h ? t('status.online') : '…'}</Badge>
      </span>
      {h && (
        <>
          <span className="flex items-center gap-1.5" title={h.database.detail ?? ''}>
            {t('status.database')}
            <Badge tone={h.database.ok ? 'ok' : 'warn'}>{t(h.database.ok ? 'status.online' : 'status.offline')}</Badge>
          </span>
          <span className="flex items-center gap-1.5" title={h.redis.detail ?? ''}>
            {t('status.queue')}
            <Badge tone={h.redis.ok ? 'ok' : 'warn'}>{t(h.redis.ok ? 'status.online' : 'status.offline')}</Badge>
          </span>
        </>
      )}
      <span className="flex flex-wrap items-center gap-1.5">
        {t('status.solvers')}
        {solvers.data?.map((s) => (
          <span key={s.descriptor.id} title={`${loc(s.descriptor.name)}${s.descriptor.unavailable_reason ? ` — ${loc(s.descriptor.unavailable_reason)}` : ''}`}>
            <Badge tone={s.descriptor.available ? 'ok' : 'muted'}>
              {s.descriptor.kind.toUpperCase()}: {t(s.descriptor.available ? 'status.available' : 'status.unavailable')}
              {s.descriptor.available && ` · ${t(s.queue_worker_online ? 'status.workerOn' : 'status.workerOff')}`}
            </Badge>
          </span>
        ))}
      </span>
      <span className="ml-auto" aria-live="polite">
        {sim.error ? t('status.error') : sim.isFetching || sim.isStale ? t('status.computing') : sim.result ? t('status.upToDate') : ''}
      </span>
    </footer>
  )
}
