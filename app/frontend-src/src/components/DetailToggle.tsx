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
      className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 py-1.5
                 text-xs font-medium text-gray-600 shadow-sm transition hover:bg-gray-50"
    >
      <span
        className={`h-2 w-2 rounded-full ${technical ? 'bg-indigo-500' : 'bg-gray-300'}`}
        aria-hidden
      />
      {technical ? 'Hide technical detail' : label}
    </button>
  )
}
