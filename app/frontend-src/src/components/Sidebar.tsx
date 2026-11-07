import { useState } from 'react'
import type { CaseListItem } from '../types'
import { BrandMark, Icon, PatientAvatar } from './Icon'

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

  return <aside className="patient-sidebar">
    <div className="sidebar-brand"><BrandMark /><span>Apollo</span></div>
    <label className="sidebar-search"><Icon name="search" />
      <input type="search" aria-label="Search patients" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search patients…" />
    </label>
    <nav aria-label="Patients" className="patient-list">
      {filtered.length === 0 && <p className="px-3 py-5 text-sm">No matching patients.</p>}
      {filtered.map(c => {
        const { name, sub } = parseLabel(c.label)
        const active = c.key === activeKey
        return <button key={c.key} onClick={() => onSelect(c.key)} aria-current={active ? 'true' : undefined} className={`patient-option ${active ? 'is-active' : ''}`}>
          <PatientAvatar name={name} />
          <span className="min-w-0 flex-1"><span className="patient-name">{name}</span><span className="patient-condition">{sub}</span></span>
          {active && <Icon name="chevron" className="patient-selected-icon" />}
        </button>
      })}
    </nav>
  </aside>
}
