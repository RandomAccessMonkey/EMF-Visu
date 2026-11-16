// Decoder for the EMF1 binary result container (see docs/architecture.md and emf_core/wire.py).
import type { ArrayEntry, ResultHeader } from './types'

export interface FieldArray {
  entry: ArrayEntry
  data: Float32Array // zero-copy view into the response buffer
}

export interface SimulationResult {
  header: ResultHeader
  arrays: Record<string, FieldArray>
  byteLength: number
}

const MAGIC = 'EMF1'
const pad8 = (n: number) => (8 - (n % 8)) % 8

export function decodeContainer(buffer: ArrayBuffer): SimulationResult {
  const bytes = new Uint8Array(buffer)
  const magic = String.fromCharCode(...bytes.subarray(0, 4))
  if (magic !== MAGIC) throw new Error('Not an EMF1 result container')
  const headerLength = new DataView(buffer).getUint32(4, true)
  const header = JSON.parse(
    new TextDecoder('utf-8').decode(bytes.subarray(8, 8 + headerLength)),
  ) as ResultHeader
  const payloadStart = 8 + headerLength + pad8(8 + headerLength)
  const arrays: Record<string, FieldArray> = {}
  for (const entry of header.arrays) {
    if (entry.dtype !== '<f4') throw new Error(`Unsupported dtype ${entry.dtype}`)
    const count = entry.shape.reduce((a, b) => a * b, 1)
    if (count * 4 !== entry.byte_length) throw new Error(`Corrupt array table for ${entry.name}`)
    // Offsets are multiples of 8 and the payload start is 8-aligned, so this view never copies.
    arrays[entry.name] = {
      entry,
      data: new Float32Array(buffer, payloadStart + entry.offset, count),
    }
  }
  return { header, arrays, byteLength: buffer.byteLength }
}
