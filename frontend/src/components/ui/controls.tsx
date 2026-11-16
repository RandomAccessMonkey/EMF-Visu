// Small shadcn/ui-style primitives (Tailwind + Radix), kept local so they can be restyled freely.
import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as SliderPrimitive from '@radix-ui/react-slider'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { cva, type VariantProps } from 'class-variance-authority'
import { X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/format'

const buttonStyles = cva(
  'inline-flex items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed select-none',
  {
    variants: {
      variant: {
        default: 'bg-panel-2 border border-border text-text hover:border-accent/60 hover:bg-[#18233a]',
        primary: 'bg-accent/15 border border-accent/50 text-accent hover:bg-accent/25',
        ghost: 'text-muted hover:text-text hover:bg-panel-2',
        danger: 'text-danger hover:bg-danger/10',
        active: 'bg-accent/20 border border-accent/60 text-accent',
      },
      size: { sm: 'h-7 px-2', md: 'h-8 px-3', icon: 'h-7 w-7' },
    },
    defaultVariants: { variant: 'default', size: 'sm' },
  },
)

export function Button({
  className,
  variant,
  size,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonStyles>) {
  return <button type="button" className={cn(buttonStyles({ variant, size }), className)} {...props} />
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="border-b border-border px-3 py-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</h3>
        {aside}
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  )
}

export function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex items-center justify-between gap-2" title={hint}>
      <span className="shrink-0 text-xs text-muted">{label}</span>
      <span className="flex min-w-0 items-center gap-2">{children}</span>
    </label>
  )
}

interface NumberFieldProps {
  value: number
  onChange: (v: number) => void
  unit?: string
  factor?: number // displayed = value / factor (e.g. 1e-9 to edit coulombs as nC)
  step?: number
  min?: number
  max?: number
  label?: string
  className?: string
}

/** Numeric input that edits an SI value, optionally displayed in a scaled unit. Invalid or
 *  out-of-range text is never committed to the model. */
export function NumberField({ value, onChange, unit, factor = 1, step, min, max, label, className }: NumberFieldProps) {
  const shown = (v: number) => String(Number((v / factor).toPrecision(8)))
  const [text, setText] = useState(shown(value))
  const focused = useRef(false)
  useEffect(() => {
    if (!focused.current) setText(shown(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, factor])
  const parsed = Number(text)
  const valid =
    text.trim() !== '' && Number.isFinite(parsed) && (min === undefined || parsed >= min) && (max === undefined || parsed <= max)
  return (
    <span className={cn('flex items-center gap-1', className)}>
      <input
        type="number"
        aria-label={label}
        aria-invalid={!valid}
        value={text}
        step={step ?? 'any'}
        min={min}
        max={max}
        onFocus={() => (focused.current = true)}
        onBlur={() => {
          focused.current = false
          setText(shown(value))
        }}
        onChange={(e) => {
          setText(e.target.value)
          const n = Number(e.target.value)
          const ok =
            e.target.value.trim() !== '' && Number.isFinite(n) && (min === undefined || n >= min) && (max === undefined || n <= max)
          if (ok) onChange(n * factor)
        }}
        className={cn(
          'h-7 w-20 rounded-md border bg-bg px-1.5 text-right font-mono text-xs text-text',
          valid ? 'border-border' : 'border-danger',
        )}
      />
      {unit && <span className="w-7 text-[11px] text-muted">{unit}</span>}
    </span>
  )
}

export function Slider(props: { value: number; min: number; max: number; step: number; onChange: (v: number) => void; label: string }) {
  return (
    <SliderPrimitive.Root
      className="relative flex h-5 w-28 touch-none items-center"
      value={[props.value]}
      min={props.min}
      max={props.max}
      step={props.step}
      onValueChange={([v]) => v !== undefined && props.onChange(v)}
    >
      <SliderPrimitive.Track className="relative h-1 grow rounded-full bg-border">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={props.label}
        className="block h-3.5 w-3.5 rounded-full border border-accent bg-bg shadow-[0_0_8px_rgba(56,189,248,0.6)]"
      />
    </SliderPrimitive.Root>
  )
}

export function Switch(props: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <SwitchPrimitive.Root
      aria-label={props.label}
      checked={props.checked}
      disabled={props.disabled}
      onCheckedChange={props.onChange}
      className="relative h-4 w-8 rounded-full bg-border transition-colors data-[state=checked]:bg-accent/70 disabled:opacity-40"
    >
      <SwitchPrimitive.Thumb className="block h-3 w-3 translate-x-0.5 rounded-full bg-text transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  )
}

export function Select<T extends string>(props: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string; disabled?: boolean }[]
  label: string
}) {
  const id = useId()
  return (
    <select
      id={id}
      aria-label={props.label}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value as T)}
      className="h-7 max-w-44 rounded-md border border-border bg-bg px-1.5 text-xs text-text"
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Segmented<T extends string>(props: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: ReactNode; title?: string }[]
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={props.label} className="inline-flex rounded-md border border-border bg-bg p-0.5">
      {props.options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={props.value === o.value}
          title={o.title}
          onClick={() => props.onChange(o.value)}
          className={cn(
            'flex h-6 items-center gap-1 rounded px-2 text-xs transition-colors',
            props.value === o.value ? 'bg-accent/20 text-accent' : 'text-muted hover:text-text',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Dialog(props: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode; closeLabel: string }) {
  return (
    <DialogPrimitive.Root open={props.open} onOpenChange={props.onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[min(640px,92vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-panel p-5 shadow-[0_0_60px_rgba(56,189,248,0.12)]"
        >
          <div className="mb-3 flex items-start justify-between gap-4">
            <DialogPrimitive.Title className="text-base font-semibold text-text">{props.title}</DialogPrimitive.Title>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="icon" aria-label={props.closeLabel}>
                <X size={15} />
              </Button>
            </DialogPrimitive.Close>
          </div>
          {props.children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function Badge({ tone, children }: { tone: 'ok' | 'warn' | 'muted' | 'danger' | 'accent'; children: ReactNode }) {
  const tones = {
    ok: 'border-ok/40 text-ok bg-ok/10',
    warn: 'border-warn/40 text-warn bg-warn/10',
    muted: 'border-border text-muted bg-panel-2',
    danger: 'border-danger/40 text-danger bg-danger/10',
    accent: 'border-accent/40 text-accent bg-accent/10',
  }
  return <span className={cn('inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none', tones[tone])}>{children}</span>
}
