import type { PatientData } from '../types'

function initials(name = ''): string {
  return name.split(' ').filter(Boolean).map((w) => w[0]?.toUpperCase()).slice(0, 2).join('')
}

export function PatientHeader({ patient }: { patient: PatientData }) {
  const p = patient.patient || {}
  const diagnoses = (patient.summary.diagnoses || []).slice(0, 3).map((d) => d.name).join(' · ')

  return (
    <div className="flex items-center gap-4 border-b border-gray-200 bg-white px-6 py-4">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">
        {initials(p.name)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-base font-semibold text-gray-900">{p.name || 'Unknown patient'}</div>
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-500">
          {p.age !== undefined && <span>Age {p.age}</span>}
          {p.dob && <span>DOB {p.dob}</span>}
          {p.mrn && <span>MRN {p.mrn}</span>}
          {diagnoses && <span className="text-gray-600">{diagnoses}</span>}
        </div>
      </div>
      <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
        Demo patient
      </span>
    </div>
  )
}
