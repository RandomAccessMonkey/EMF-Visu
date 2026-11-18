// Looping playback of the simulation time (shared by every time-dependent model).
//
// Once Play is pressed the time advances indefinitely over [start, end): reaching the end wraps
// to the start with the overflow carried, t = start + ((m·Δt) mod (end − start)), where m is an
// integer step counter. Every time is computed afresh from m (never accumulated), so the loop is
// free of drift. When the range is a whole number N of steps, t = start + (m mod N)·Δt exactly,
// i.e. playback stays on the deterministic grid t = start + k·Δt (the end point itself is the
// next cycle's start). A step is only taken once the previous step's result has arrived; the
// timer keeps running while a tab is in the background (browsers only throttle it).

export interface PlaybackState {
  timeS: number
  timeStart: number
  timeEnd: number
  timeStep: number
  playing: boolean
  playbackSpeed: number
}

export interface PlaybackStore {
  getState(): PlaybackState
  set(patch: Partial<PlaybackState>): void
  subscribe(listener: () => void): () => void
}

export interface Timers {
  set(fn: () => void, ms: number): unknown
  clear(handle: unknown): void
}

const DEFAULT_TIMERS: Timers = {
  set: (fn, ms) => setTimeout(fn, ms),
  clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
}

/** Minimum wall-clock interval between steps, and the poll interval while a result is pending. */
export const MIN_STEP_MS = 30

/** Time of step m in the looped range [start, end). */
export function loopTime(m: number, start: number, end: number, step: number): number {
  const period = end - start
  if (!(period > 0) || !(step > 0) || !Number.isFinite(m)) return start
  const n = period / step
  const whole = Math.round(n)
  if (whole >= 1 && Math.abs(n - whole) <= 1e-9 * Math.max(1, n)) {
    return start + (((m % whole) + whole) % whole) * step
  }
  const x = m * step
  return start + (((x % period) + period) % period)
}

/** Step counter of a time (the nearest grid index; times between grid points round). */
export function stepOf(t: number, start: number, step: number): number {
  return step > 0 ? Math.round((t - start) / step) : 0
}

export function stepDelayMs(step: number, speed: number): number {
  return Math.max(MIN_STEP_MS, (step / (speed > 0 ? speed : 1)) * 1000)
}

/** One playback loop per time bar: at most one pending timer at any moment. */
export class PlaybackLoop {
  private timer: unknown = null
  private m = 0
  private lastSet: number | null = null
  private rangeKey = ''
  private unsubscribe: (() => void) | null = null

  constructor(
    private readonly store: PlaybackStore,
    private readonly isWaiting: () => boolean = () => false,
    private readonly timers: Timers = DEFAULT_TIMERS,
  ) {}

  /** Start listening to the store (playing true starts the loop, false stops it). */
  attach(): this {
    this.unsubscribe = this.store.subscribe(() => this.sync())
    this.sync()
    return this
  }

  /** Release the timer and the store subscription (on unmount). */
  dispose(): void {
    this.cancel()
    this.unsubscribe?.()
    this.unsubscribe = null
  }

  /** Whether a step is scheduled (exactly one while playing). */
  get active(): boolean {
    return this.timer !== null
  }

  private cancel(): void {
    if (this.timer !== null) this.timers.clear(this.timer)
    this.timer = null
  }

  private sync(): void {
    const s = this.store.getState()
    if (s.playing && this.timer === null) {
      this.align(s)
      this.schedule(stepDelayMs(s.timeStep, s.playbackSpeed))
    } else if (!s.playing && this.timer !== null) {
      this.cancel()
    }
  }

  /** Re-derive the step counter from the current time (after an edit or a range change). */
  private align(s: PlaybackState): void {
    this.m = stepOf(s.timeS, s.timeStart, s.timeStep)
    this.lastSet = s.timeS
    this.rangeKey = `${s.timeStart}|${s.timeEnd}|${s.timeStep}`
  }

  private schedule(ms: number): void {
    this.timer = this.timers.set(() => this.tick(), ms)
  }

  private tick(): void {
    this.timer = null
    const s = this.store.getState()
    if (!s.playing) return
    if (this.isWaiting()) {
      this.schedule(MIN_STEP_MS)
      return
    }
    if (s.timeS !== this.lastSet || `${s.timeStart}|${s.timeEnd}|${s.timeStep}` !== this.rangeKey) this.align(s)
    this.m += 1
    const t = loopTime(this.m, s.timeStart, s.timeEnd, s.timeStep)
    this.lastSet = t
    // Schedule first: the store update notifies sync(), which must see the pending step.
    this.schedule(stepDelayMs(s.timeStep, s.playbackSpeed))
    this.store.set({ timeS: t })
  }
}
