import { useState } from 'react'
import type { CaseListItem } from '../types'

interface Props {
  cases: CaseListItem[]
  activeKey: string | null
  onSelect: (key: string) => void
  kgStatus: string
}

function parseLabel(label: string): { initials: string; name: string; sub: string } {
  const name = label.split('—')[1]?.trim().split('(')[0].trim() || label
  const initials = name.split(' ').filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  const sub = label.match(/\(([^)]+)\)/)?.[1] || ''
  return { initials, name, sub }
}

export function Sidebar({ cases, activeKey, onSelect, kgStatus }: Props) {
  const [query, setQuery] = useState('')
  const filtered = cases.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()))

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 p-4">
        <h1 className="text-lg font-semibold text-gray-900">Apollo</h1>
        <p className="text-xs text-gray-500">Clinical assistant demo</p>
      </div>

      <div className="p-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patients…"
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-800
                     placeholder:text-gray-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
      </div>

      <nav className="flex-1 overflow-y-auto px-2">
        {filtered.map((c) => {
          const { initials, name, sub } = parseLabel(c.label)
          const active = c.key === activeKey
          return (
            <button
              key={c.key}
              onClick={() => onSelect(c.key)}
              className={`mb-1 flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition ${
                active ? 'bg-indigo-50 ring-1 ring-indigo-200' : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-gray-900">{name}</div>
                <div className="truncate text-xs text-gray-500">{sub}</div>
              </div>
              <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                Demo
              </span>
            </button>
          )
        })}
      </nav>

      <div className="border-t border-gray-200 p-3 text-xs text-gray-500">{kgStatus}</div>
    </aside>
  )
}
