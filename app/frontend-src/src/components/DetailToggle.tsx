interface Props {
  technical: boolean
  onChange: (technical: boolean) => void
  label?: string
}

export function DetailToggle({ technical, onChange, label = 'Show technical detail' }: Props) {
  return (
    <button
      type="button"
      onClick={() => onChange(!technical)}
      className="inline-flex items-center gap-2 border border-rule bg-sheet px-3 py-1.5
                 font-mono text-xs text-ink/60 transition-colors hover:border-accent hover:text-accent"
    >
      <span className={`h-1.5 w-1.5 ${technical ? 'bg-accent' : 'bg-rule'}`} aria-hidden />
      {technical ? 'Hide technical detail' : label}
    </button>
  )
}
