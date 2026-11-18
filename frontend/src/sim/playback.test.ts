import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loopTime, MIN_STEP_MS, PlaybackLoop, type PlaybackState, type PlaybackStore } from './playback'

/** A minimal store with the same contract as the view store (set notifies subscribers). */
function makeStore(init: Partial<PlaybackState> = {}) {
  let state: PlaybackState = { timeS: 0, timeStart: 0, timeEnd: 20e-9, timeStep: 0.1e-9, playing: false, playbackSpeed: 1, ...init }
  const listeners = new Set<() => void>()
  const history: number[] = []
  const store: PlaybackStore = {
    getState: () => state,
    set: (p) => {
      state = { ...state, ...p }
      if (p.timeS !== undefined) history.push(p.timeS)
      listeners.forEach((f) => f())
    },
    subscribe: (f) => {
      listeners.add(f)
      return () => listeners.delete(f)
    },
  }
  return { store, history, listeners }
}

const N = 200 // steps in the coax preset range (20 ns / 0.1 ns)

describe('loopTime', () => {
  it('stays on the grid and wraps a whole number of steps exactly', () => {
    expect(loopTime(0, 0, 20e-9, 0.1e-9)).toBe(0)
    expect(loopTime(199, 0, 20e-9, 0.1e-9)).toBeCloseTo(19.9e-9, 20)
    expect(loopTime(200, 0, 20e-9, 0.1e-9)).toBe(0) // end ≡ start of the next cycle
    expect(loopTime(201, 0, 20e-9, 0.1e-9)).toBeCloseTo(0.1e-9, 22)
    // No drift after many cycles: the same phase gives bit-identical times.
    expect(loopTime(37 + 1000 * 200, 0, 20e-9, 0.1e-9)).toBe(loopTime(37, 0, 20e-9, 0.1e-9))
    expect(loopTime(-1, 0, 20e-9, 0.1e-9)).toBeCloseTo(19.9e-9, 20)
  })
  it('carries the overflow when the range is not a whole number of steps', () => {
    // Range 1.0, step 0.3: 0.3, 0.6, 0.9, then 1.2 → 0.2 (overflow 0.2 carried).
    expect(loopTime(4, 0, 1, 0.3)).toBeCloseTo(0.2, 12)
    expect(loopTime(7, 0, 1, 0.3)).toBeCloseTo(0.1, 12)
    for (let m = 0; m < 1000; m++) {
      const t = loopTime(m, 2, 3, 0.3)
      expect(t).toBeGreaterThanOrEqual(2)
      expect(t).toBeLessThan(3)
    }
  })
  it('keeps sub-nanosecond steps', () => {
    expect(loopTime(3, 0, 1e-9, 1e-12)).toBeCloseTo(3e-12, 24)
  })
})

describe('PlaybackLoop', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('plays past the end, wraps to the start and keeps playing for three cycles', () => {
    const { store, history } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    store.set({ playing: true })
    vi.advanceTimersByTime(MIN_STEP_MS * (3 * N + 10))
    const times = history
    expect(store.getState().playing).toBe(true)
    expect(times.length).toBeGreaterThanOrEqual(3 * N)
    // Wraps: the time decreases exactly at the cycle boundaries, back to the start.
    const wraps = times.flatMap((t, i) => (i > 0 && t < times[i - 1]! ? [t] : []))
    expect(wraps.length).toBeGreaterThanOrEqual(3)
    wraps.forEach((t) => expect(t).toBe(0))
    times.forEach((t) => {
      expect(t).toBeGreaterThanOrEqual(0)
      expect(t).toBeLessThan(20e-9)
    })
    expect(loop.active).toBe(true)
    loop.dispose()
  })

  it('pause keeps the time, resume continues from it, stop ends playback only when asked', () => {
    const { store } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    store.set({ playing: true })
    vi.advanceTimersByTime(MIN_STEP_MS * 50)
    store.set({ playing: false }) // Pause
    const paused = store.getState().timeS
    expect(paused).toBeGreaterThan(0)
    vi.advanceTimersByTime(MIN_STEP_MS * 100)
    expect(store.getState().timeS).toBe(paused)
    expect(loop.active).toBe(false)
    store.set({ playing: true }) // Resume
    vi.advanceTimersByTime(MIN_STEP_MS)
    expect(store.getState().timeS).toBeCloseTo(paused + 0.1e-9, 20)
    store.set({ playing: false, timeS: store.getState().timeStart }) // Stop
    vi.advanceTimersByTime(MIN_STEP_MS * 10)
    expect(store.getState()).toMatchObject({ playing: false, timeS: 0 })
    loop.dispose()
  })

  it('keeps exactly one timer under repeated Play', () => {
    const { store } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    for (let i = 0; i < 5; i++) store.set({ playing: true })
    expect(vi.getTimerCount()).toBe(1)
    vi.advanceTimersByTime(MIN_STEP_MS * 10)
    expect(vi.getTimerCount()).toBe(1)
    expect(store.getState().timeS).toBeCloseTo(10 * 0.1e-9, 20)
    loop.dispose()
    expect(vi.getTimerCount()).toBe(0) // released on unmount
  })

  it('waits for a pending result without stopping', () => {
    const { store } = makeStore()
    let waiting = true
    const loop = new PlaybackLoop(store, () => waiting).attach()
    store.set({ playing: true })
    vi.advanceTimersByTime(MIN_STEP_MS * 20)
    expect(store.getState()).toMatchObject({ playing: true, timeS: 0 })
    waiting = false
    vi.advanceTimersByTime(MIN_STEP_MS * 2)
    expect(store.getState().timeS).toBeGreaterThan(0)
    loop.dispose()
  })

  it('stays valid when the range changes during playback', () => {
    const { store } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    store.set({ playing: true })
    vi.advanceTimersByTime(MIN_STEP_MS * 150) // t ≈ 15 ns
    store.set({ timeStart: 2e-9, timeEnd: 8e-9 }) // current time now outside the range
    for (let i = 0; i < 200; i++) {
      vi.advanceTimersByTime(MIN_STEP_MS)
      const t = store.getState().timeS
      expect(t).toBeGreaterThanOrEqual(2e-9)
      expect(t).toBeLessThan(8e-9)
    }
    expect(store.getState().playing).toBe(true)
    loop.dispose()
  })

  it('continues after background-tab throttling (sparse, late timer callbacks)', () => {
    const { store } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    store.set({ playing: true })
    // A throttled tab fires timers late (≥ 1 s apart): simulate long gaps between callbacks.
    for (let i = 0; i < 5; i++) vi.advanceTimersByTime(1000)
    expect(store.getState().playing).toBe(true)
    expect(loop.active).toBe(true)
    expect(store.getState().timeS).toBeGreaterThan(0)
    loop.dispose()
  })

  it('a user time edit during playback continues from the edited time', () => {
    const { store } = makeStore()
    const loop = new PlaybackLoop(store).attach()
    store.set({ playing: true })
    vi.advanceTimersByTime(MIN_STEP_MS * 5)
    store.set({ timeS: 12e-9 })
    vi.advanceTimersByTime(MIN_STEP_MS)
    expect(store.getState().timeS).toBeCloseTo(12.1e-9, 20)
    loop.dispose()
  })
})
