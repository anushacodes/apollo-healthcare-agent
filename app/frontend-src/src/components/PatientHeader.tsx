import type { PatientData } from '../types'

export function PatientHeader({ patient }: { patient: PatientData }) {
  const p = patient.patient || {}
  const diagnoses = (patient.summary.diagnoses || []).slice(0, 3).map((d) => d.name)

  return (
    <div className="border-b border-rule bg-sheet px-6 py-4">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-serif text-xl text-ink">{p.name || 'Unknown patient'}</h2>
        <span className="shrink-0 rounded-sm border border-caution/30 bg-caution-subtle px-2 py-0.5 text-xs text-caution">
          Demo patient
        </span>
      </div>
      <div className="mt-2 flex flex-wrap divide-x divide-rule text-xs text-ink/60">
        {p.age !== undefined && <span className="pr-3">Age {p.age}</span>}
        {p.dob && <span className="px-3">DOB {p.dob}</span>}
        {p.mrn && <span className="px-3 font-mono">MRN {p.mrn}</span>}
        {diagnoses.map((name, i) => (
          <span key={i} className="px-3 text-ink/80">
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}
