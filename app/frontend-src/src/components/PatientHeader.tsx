import type { PatientData } from '../types'

export function PatientHeader({ patient }: { patient: PatientData }) {
  const p = patient.patient || {}
  return (
    <header className="flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-rule bg-sheet px-4 py-5 sm:px-6">
      <h1 className="font-serif text-2xl font-semibold text-ink">{p.name || 'Patient record'}</h1>
      {p.age !== undefined && <span className="text-sm text-muted">Age {p.age}</span>}
    </header>
  )
}
