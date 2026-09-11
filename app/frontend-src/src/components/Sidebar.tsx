import { useState } from 'react'
import type { CaseListItem } from '../types'

interface Props {
  cases: CaseListItem[]
  activeKey: string | null
  onSelect: (key: string) => void
  kgStatus: string
}

function parseLabel(label: string): { name: string; sub: string } {
  const name = label.split('—')[1]?.trim().split('(')[0].trim() || label
  const sub = label.match(/\(([^)]+)\)/)?.[1] || ''
  return { name, sub }
}

export function Sidebar({ cases, activeKey, onSelect, kgStatus }: Props) {
  const [query, setQuery] = useState('')
  const filtered = cases.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()))

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-rule bg-sheet">
      <div className="border-b border-rule p-4">
        <h1 className="font-serif text-xl tracking-tight text-ink">Apollo</h1>
        <p className="text-xs text-ink/50">Case dossier viewer</p>
      </div>

      <div className="p-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patients…"
          className="w-full rounded-sm border border-rule bg-paper px-3 py-1.5 text-sm text-ink
                     placeholder:text-ink/35 focus:border-accent focus:outline-none"
        />
      </div>

      <nav className="flex-1 overflow-y-auto px-3">
        {filtered.map((c, i) => {
          const { name, sub } = parseLabel(c.label)
          const active = c.key === activeKey
          return (
            <button
              key={c.key}
              onClick={() => onSelect(c.key)}
              className={`flex w-full items-baseline gap-3 border-l-2 py-2.5 pl-3 text-left transition-colors ${
                active ? 'border-accent bg-accent-subtle' : 'border-transparent hover:bg-paper'
              }`}
            >
              <span className="font-mono text-xs text-ink/35">{String(i + 1).padStart(2, '0')}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">{name}</span>
                <span className="block truncate text-xs text-ink/50">{sub}</span>
              </span>
              <span className="shrink-0 font-mono text-[10px] text-ink/35">demo</span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-rule p-3 text-xs text-ink/50">{kgStatus}</div>
    </aside>
  )
}
