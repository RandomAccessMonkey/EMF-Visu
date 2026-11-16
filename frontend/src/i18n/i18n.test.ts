import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from './en.json'
import hu from './hu.json'

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? sources(join(dir, e.name)) : /\.tsx$/.test(e.name) ? [join(dir, e.name)] : [],
  )
}

describe('localization', () => {
  it('English and Hungarian dictionaries have identical keys and no empty strings', () => {
    expect(Object.keys(hu).sort()).toEqual(Object.keys(en).sort())
    for (const dict of [en, hu]) for (const v of Object.values(dict)) expect(v.trim()).not.toBe('')
  })
  it('placeholders match between languages', () => {
    const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort()
    for (const k of Object.keys(en) as (keyof typeof en)[]) expect(vars(hu[k])).toEqual(vars(en[k]))
  })
  it('components contain no hard-coded user-facing sentences', () => {
    // JSX text nodes must be symbols, numbers or punctuation only; words go through t().
    const offenders: string[] = []
    for (const file of sources(join(__dirname, '..'))) {
      if (file.endsWith('main.tsx')) continue // pre-app WebGL 2 fallback, localized inline
      const text = readFileSync(file, 'utf8')
      for (const m of text.matchAll(/>\s*([A-Za-z][A-Za-z ,.']{12,})\s*</g)) offenders.push(`${file}: ${m[1]}`)
      for (const m of text.matchAll(/(?:title|aria-label|placeholder)="([A-Za-z][^"]{3,})"/g)) offenders.push(`${file}: ${m[1]}`)
    }
    expect(offenders).toEqual([])
  })
})
