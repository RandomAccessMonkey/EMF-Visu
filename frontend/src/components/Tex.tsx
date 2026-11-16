import katex from 'katex'
import 'katex/dist/katex.min.css'
import { useMemo } from 'react'

export function Tex({ latex, block = false }: { latex: string; block?: boolean }) {
  const html = useMemo(
    () => katex.renderToString(latex, { displayMode: block, throwOnError: false, trust: false }),
    [latex, block],
  )
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}
