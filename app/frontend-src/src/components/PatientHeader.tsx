import type { PatientData } from '../types'
import { PatientAvatar } from './Icon'

export function PatientHeader({ patient }: { patient: PatientData }) {
  const p = patient.patient || {}
  return <header className="patient-header">
    <PatientAvatar name={p.name || 'Patient record'} className="header-avatar" />
    <div className="flex min-w-0 flex-wrap items-baseline gap-x-5 gap-y-1">
      <h1 className="patient-heading">{p.name || 'Patient record'}</h1>
      {p.age !== undefined && <span className="patient-age">Age {p.age}</span>}
    </div>
  </header>
}
