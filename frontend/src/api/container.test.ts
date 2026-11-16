import { describe, expect, it } from 'vitest'
import { decodeContainer } from './container'

function build(header: object, payload: Float32Array, misalign = 0): ArrayBuffer {
  const head = new TextEncoder().encode(JSON.stringify(header))
  const pad = (8 - ((8 + head.length) % 8)) % 8
  const out = new Uint8Array(8 + head.length + pad + misalign + payload.byteLength)
  out.set(new TextEncoder().encode('EMF1'), 0)
  new DataView(out.buffer).setUint32(4, head.length, true)
  out.set(head, 8)
  out.set(new Uint8Array(payload.buffer), 8 + head.length + pad + misalign)
  return out.buffer
}

const entry = (name: string, shape: number[], offset: number) => ({
  name, sampling_id: 's', quantity: 'E', symbol: 'E', unit: 'V/m', components: 3,
  stats: { min: 0, max: 1, non_finite_count: 0 }, dtype: '<f4', shape, offset,
  byte_length: shape.reduce((a, b) => a * b, 1) * 4,
})

describe('decodeContainer', () => {
  it('decodes arrays as zero-copy views with the right values', () => {
    const data = new Float32Array([1, 2, 3, 4, 5, 6, 0, 0, 7.5, NaN])
    const buf = build({ status: 'ok', arrays: [entry('s.E', [2, 3], 0), entry('s.phi', [2], 32)] }, data)
    const r = decodeContainer(buf)
    expect(Array.from(r.arrays['s.E']!.data)).toEqual([1, 2, 3, 4, 5, 6])
    expect(r.arrays['s.phi']!.data[0]).toBe(7.5)
    expect(Number.isNaN(r.arrays['s.phi']!.data[1]!)).toBe(true)
    expect(r.arrays['s.E']!.data.buffer).toBe(buf)
    expect(r.header.status).toBe('ok')
  })
  it('rejects foreign data and inconsistent array tables', () => {
    expect(() => decodeContainer(new Uint8Array(16).buffer)).toThrow(/EMF1/)
    const bad = { ...entry('s.E', [2, 3], 0), byte_length: 20 }
    expect(() => decodeContainer(build({ arrays: [bad] }, new Float32Array(6)))).toThrow(/Corrupt/)
  })
})
