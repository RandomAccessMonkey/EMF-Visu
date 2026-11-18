// Simulation-time controls (Phase 4A). The physics is evaluated at t = t_start + k·Δt exactly
// (k an integer, never an accumulated sum), so playback is deterministic; wall-clock time only
// paces the steps, and a step waits until the previous step's result has arrived.
import { Pause, Play, SkipBack, SkipForward, Square } from 'lucide-react'
import { useEffect } from 'react'
import { Button, NumberField, Select } from '@/components/ui/controls'
import { useT, type MessageKey } from '@/i18n'
import { useViewStore } from '@/state/viewStore'

const SPEEDS = ['0.25', '0.5', '1', '2', '4'] as const

/** Index of the time-grid point at or before t (tolerant to rounding). */
export function stepIndex(t: number, start: number, step: number): number {
  return Math.floor((t - start) / step + 1e-9)
}

/** Time of grid point k, clamped to the range. */
export function gridTime(k: number, start: number, end: number, step: number): number {
  return Math.min(end, Math.max(start, start + k * step))
}

/** Display unit of the time fields (values stay in seconds); minStep is the smallest Δt in s. */
export interface TimeUnit {
  factor: number
  unit: string
  minStep: number
}
const SECONDS: TimeUnit = { factor: 1, unit: 's', minStep: 1e-9 }

export function TimeBar({ waiting, heading = 'time.mqs', timeUnit = SECONDS }: { waiting: boolean; heading?: MessageKey; timeUnit?: TimeUnit }) {
  const { t } = useT()
  const v = useViewStore()
  const { timeS, timeStart, timeEnd, timeStep, playing, playbackSpeed } = v
  const k = stepIndex(timeS, timeStart, timeStep)
  const lastK = stepIndex(timeEnd, timeStart, timeStep)
  const go = (kk: number) => v.set({ timeS: gridTime(kk, timeStart, timeEnd, timeStep) })

  useEffect(() => {
    if (!playing || waiting) return
    if (k >= lastK) {
      v.set({ playing: false })
      return
    }
    const delay = Math.max(30, (timeStep / playbackSpeed) * 1000)
    const id = setTimeout(() => useViewStore.getState().set({ timeS: gridTime(k + 1, timeStart, timeEnd, timeStep) }), delay)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, waiting, k, lastK, timeStep, playbackSpeed, timeStart, timeEnd])

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-1.5 text-xs" role="group" aria-label={t('time.controls')} data-testid="time-bar">
      <span className="font-semibold text-accent-2">{t(heading)}</span>
      <Button variant="ghost" size="icon" aria-label={t('time.stepBack')} onClick={() => go(Math.max(0, k - 1))} disabled={playing || k <= 0}>
        <SkipBack size={13} />
      </Button>
      <Button variant="primary" size="icon" aria-label={t(playing ? 'time.pause' : 'time.play')} onClick={() => v.set({ playing: !playing, ...(k >= lastK && !playing ? { timeS: timeStart } : {}) })}>
        {playing ? <Pause size={13} /> : <Play size={13} />}
      </Button>
      <Button variant="ghost" size="icon" aria-label={t('time.stop')} onClick={() => v.set({ playing: false, timeS: timeStart })}>
        <Square size={12} />
      </Button>
      <Button variant="ghost" size="icon" aria-label={t('time.stepForward')} onClick={() => go(Math.min(lastK, k + 1))} disabled={playing || k >= lastK}>
        <SkipForward size={13} />
      </Button>
      <input
        type="range"
        aria-label={t('time.slider')}
        min={0}
        max={lastK}
        step={1}
        value={Math.min(Math.max(k, 0), lastK)}
        onChange={(e) => go(Number(e.target.value))}
        className="h-1 min-w-24 flex-1 accent-[#22d3ee]"
      />
      <span className="flex items-center gap-1">
        t = <NumberField label={t('time.time')} value={timeS} unit={timeUnit.unit} factor={timeUnit.factor} step={timeStep / timeUnit.factor} min={timeStart / timeUnit.factor} max={timeEnd / timeUnit.factor} onChange={(x) => v.set({ timeS: x, playing: false })} />
      </span>
      <span className="flex items-center gap-1 text-muted">
        {t('time.range')}
        <NumberField label={t('time.start')} value={timeStart} factor={timeUnit.factor} step={timeStep / timeUnit.factor} max={(timeEnd - timeStep) / timeUnit.factor} onChange={(x) => v.set({ timeStart: x, timeS: Math.max(x, timeS) })} />
        –
        <NumberField label={t('time.end')} value={timeEnd} unit={timeUnit.unit} factor={timeUnit.factor} step={timeStep / timeUnit.factor} min={(timeStart + timeStep) / timeUnit.factor} onChange={(x) => v.set({ timeEnd: x, timeS: Math.min(x, timeS) })} />
        Δt
        <NumberField label={t('time.step')} value={timeStep} unit={timeUnit.unit} factor={timeUnit.factor} min={timeUnit.minStep / timeUnit.factor} step={timeStep / timeUnit.factor} onChange={(x) => x > 0 && v.set({ timeStep: x })} />
      </span>
      <Select<(typeof SPEEDS)[number]>
        label={t('time.speed')}
        value={(SPEEDS.find((s) => Number(s) === playbackSpeed) ?? '1') as (typeof SPEEDS)[number]}
        onChange={(s) => v.set({ playbackSpeed: Number(s) })}
        options={SPEEDS.map((s) => ({ value: s, label: `${s}×` }))}
      />
      {playing && <span className="text-[11px] text-muted">{t('time.linesPaused')}</span>}
    </div>
  )
}
