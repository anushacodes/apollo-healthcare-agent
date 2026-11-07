import { useState } from 'react'
import type { CaseListItem } from '../types'

interface Props {
  cases: CaseListItem[]
  activeKey: string | null
  onSelect: (key: string) => void
}

function parseLabel(label: string): { name: string; sub: string } {
  const name = label.split('—')[1]?.trim().split('(')[0].trim() || label
  const sub = label.match(/\(([^)]+)\)/)?.[1] || ''
  return { name, sub }
}

export function Sidebar({ cases, activeKey, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const filtered = cases.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()))

  return (
    <aside className="flex max-h-[45dvh] w-full shrink-0 flex-col border-r border-rule bg-sheet lg:h-full lg:max-h-none lg:w-72">
      <div className="border-b border-rule p-4">
        <h1 className="font-serif text-2xl font-semibold tracking-tight text-ink">Apollo</h1>
      </div>

      <div className="p-3">
        <input
          type="text"
          aria-label="Search patients"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patients…"
          className="w-full rounded-sm border border-rule bg-paper px-3 py-1.5 text-base text-ink
                     placeholder:text-muted focus:border-accent focus:outline-none"
        />
      </div>

      <nav aria-label="Patients" className="flex-1 overflow-y-auto px-3">
        {filtered.length === 0 && <p className="p-3 text-sm text-muted">No matching patients.</p>}
        {filtered.map((c) => {
          const { name, sub } = parseLabel(c.label)
          const active = c.key === activeKey
          return (
            <button
              key={c.key}
              onClick={() => onSelect(c.key)}
              aria-current={active ? 'true' : undefined}
              className={`flex w-full items-baseline gap-3 border-l-2 py-4 pl-3 text-left transition-colors ${
                active ? 'border-accent bg-accent-subtle' : 'border-transparent hover:bg-paper'
              }`}
            >
              <span className="min-w-0 flex-1">
                <span className="block text-base font-medium text-ink">{name}</span>
                <span className="block text-sm text-muted">{sub}</span>
              </span>
            </button>
          )
        })}
      </nav>

    </aside>
  )
}
