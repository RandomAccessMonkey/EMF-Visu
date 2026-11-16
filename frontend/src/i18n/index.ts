import type { LocalizedText } from '@/api/types'
import { useViewStore, type Lang } from '@/state/viewStore'
import en from './en.json'
import hu from './hu.json'

export type MessageKey = keyof typeof en
const DICTS: Record<Lang, Record<MessageKey, string>> = { en, hu }

export function translate(lang: Lang, key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = DICTS[lang][key] ?? en[key] ?? key
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v))
  return text
}

/** `t` for UI strings, `loc` for localized text delivered by the backend. */
export function useT() {
  const lang = useViewStore((s) => s.lang)
  return {
    lang,
    t: (key: MessageKey, vars?: Record<string, string | number>) => translate(lang, key, vars),
    loc: (text: LocalizedText | null | undefined) => (text ? text[lang] : ''),
  }
}
