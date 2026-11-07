interface Props {
  technical: boolean
  onChange: (technical: boolean) => void
  label?: string
}

export function DetailToggle({ technical, onChange, label = 'Details' }: Props) {
  return (
    <button
      type="button"
      onClick={() => onChange(!technical)}
      aria-pressed={technical}
      className="secondary-button inline-flex items-center gap-2"
    >
      {technical ? 'Hide details' : label}
    </button>
  )
}
