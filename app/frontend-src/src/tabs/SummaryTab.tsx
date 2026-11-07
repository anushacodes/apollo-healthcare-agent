import { useState, type ReactNode } from 'react'
import { DetailToggle } from '../components/DetailToggle'
import { explainIcdCode, explainLabFlag, isCriticalLabFlag } from '../labels'
import type { PatientData } from '../types'

export function SummaryTab({ patient }: { patient: PatientData }) {
  const [technical, setTechnical] = useState(false)
  const [allConcerns, setAllConcerns] = useState(false)
  const [fullNarrative, setFullNarrative] = useState(false)
  const s = patient.summary
  const cs = s.clinical_summary
  const concerns = cs?.key_concerns?.length ? cs.key_concerns :
    (s.clinical_flags || []).filter((flag) => typeof flag === 'string' || flag.type === 'warn' || flag.type === 'critical').map((flag) => typeof flag === 'string' ? flag : flag.text).filter(Boolean)
  const narrative = cs?.patient_facing_summary || cs?.chief_complaint || s.summary_narrative || 'No summary available yet.'

  return (
    <div className="page-content space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-2xl font-semibold">Overview</h2>
        </div>
        <DetailToggle technical={technical} onChange={setTechnical} label="More details" />
      </div>

      {concerns.length > 0 && (
        <section className="panel border-caution/40 bg-caution-subtle" aria-labelledby="concerns-heading">
          <h3 id="concerns-heading" className="section-title text-caution">Key concerns</h3>
          <ul id="concerns-list" className="max-w-[75ch] list-disc space-y-3 pl-5 leading-relaxed">
            {(allConcerns ? concerns : concerns.slice(0, 3)).map((c, i) => <li key={i}>{c}</li>)}
          </ul>
          {concerns.length > 3 && <button className="mt-4 min-h-11 text-sm font-semibold text-caution underline underline-offset-4" aria-expanded={allConcerns} aria-controls="concerns-list" onClick={() => setAllConcerns(!allConcerns)}>
            {allConcerns ? 'Show fewer concerns' : `Show ${concerns.length - 3} more concerns`}
          </button>}
        </section>
      )}

      <section className="panel">
        <h3 className="section-title">At a glance</h3>
        <p id="overview-narrative" className={`max-w-[68ch] leading-7 ${fullNarrative || narrative.length <= 500 ? '' : 'line-clamp-5'}`}>{narrative}</p>
        {narrative.length > 500 && <button className="mt-3 min-h-11 text-sm font-medium text-accent underline underline-offset-4" aria-expanded={fullNarrative} aria-controls="overview-narrative" onClick={() => setFullNarrative(!fullNarrative)}>
          {fullNarrative ? 'Show shorter overview' : 'Read full overview'}
        </button>}
      </section>

      {!!cs?.follow_up_actions?.length && (
        <section className="panel border-accent/30">
          <h3 className="section-title">What happens next</h3>
          <ol className="list-decimal space-y-3 pl-5 leading-relaxed">
            {cs.follow_up_actions.map((a, i) => <li key={i}>{a}</li>)}
          </ol>
        </section>
      )}

      <FactSection title="Diagnoses" count={s.diagnoses?.length}>
        <div className="divide-y divide-rule">
          {(s.diagnoses || []).map((dx, i) => (
            <div key={i} className="flex flex-wrap items-start justify-between gap-3 py-4 first:pt-0 last:pb-0">
              <div>
                <p className="font-medium">{dx.name}</p>
                {explainIcdCode(dx.icd_code) && <p className="mt-1 text-sm text-muted">{explainIcdCode(dx.icd_code)}</p>}
              </div>
              {dx.status && <span className="status-badge capitalize">{dx.status.replaceAll('_', ' ')}</span>}
            </div>
          ))}
        </div>
      </FactSection>

      <FactSection title="Medications" count={s.medications?.length}>
        <div className="-mx-5 overflow-x-auto sm:-mx-6">
          <table className="clinical-table">
            <caption className="sr-only">Current medications, dose, and frequency</caption>
            <thead><tr><th scope="col">Medication</th><th scope="col">Dose</th><th scope="col">Frequency</th></tr></thead>
            <tbody>{(s.medications || []).map((m, i) => (
              <tr key={i}><td className="font-medium">{m.name}</td><td>{m.dose || 'Not recorded'}</td><td>{m.frequency || 'Not recorded'}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </FactSection>

      <FactSection title="Recent labs" count={s.lab_results?.length}>
        <div className="-mx-5 overflow-x-auto sm:-mx-6">
          <table className="clinical-table">
            <caption className="sr-only">Laboratory tests, results, and recorded status</caption>
            <thead><tr><th scope="col">Test</th><th scope="col">Result</th><th scope="col">Status</th></tr></thead>
            <tbody>{(s.lab_results || []).map((l, i) => {
              const critical = isCriticalLabFlag(l.flag)
              const abnormal = critical || l.flag === 'high' || l.flag === 'low'
              const status = critical ? (l.flag === 'critical_high' ? 'Critical high' : 'Critical low') :
                l.flag === 'high' ? 'High' : l.flag === 'low' ? 'Low' : l.flag === 'normal' ? 'Normal' : 'Not recorded'
              return (
                <tr key={i} className={critical ? 'bg-critical-subtle' : ''}>
                  <td className="font-medium">{l.test_name}</td>
                  <td className={`tabular-nums ${critical ? 'font-semibold text-critical' : ''}`}>{l.value} <span className="text-sm text-muted">{l.unit}</span></td>
                  <td><span title={l.flag ? explainLabFlag(l.flag) : 'Status not recorded'} className={`status-badge whitespace-nowrap ${critical ? 'border-critical/30 bg-critical-subtle text-critical' : abnormal ? 'border-caution/30 bg-caution-subtle text-caution' : 'text-muted'}`}>{status}</span></td>
                </tr>
              )
            })}</tbody>
          </table>
        </div>
      </FactSection>

      {technical && (
        <section className="panel space-y-6">
          <h3 className="section-title">Record details</h3>
          <dl className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
            {patient.patient?.dob && <div><dt className="text-muted">Date of birth</dt><dd>{patient.patient.dob}</dd></div>}
            {patient.patient?.mrn && <div><dt className="text-muted">Record number</dt><dd>{patient.patient.mrn}</dd></div>}
          </dl>
          {cs && <div className="space-y-5">
            <TechField label="Chief complaint" value={cs.chief_complaint} />
            <TechField label="History of present illness" value={cs.history_of_present_illness} />
            <TechField label="Clinical assessment" value={cs.clinical_assessment} />
          </div>}
          {!!s.clinical_flags?.length && <div><h4 className="mb-3 font-medium">All recorded flags</h4><ul className="list-disc space-y-3 pl-5">{s.clinical_flags.map((flag, i) => <li key={i}>{typeof flag === 'string' ? flag : flag.text}</li>)}</ul></div>}
          {!!s.diagnoses?.length && <div><h4 className="mb-2 font-medium">ICD codes</h4>
            {s.diagnoses.map((dx, i) => <p key={i} className="text-sm text-muted"><span className="font-mono">{dx.icd_code || '—'}</span> · {dx.name}</p>)}
          </div>}
          {!!s.timeline?.length && <div><h4 className="mb-3 font-medium">Timeline</h4>
            <ol className="space-y-4">{[...s.timeline].reverse().map((t, i) => (
              <li key={i} className="flex flex-col gap-1 border-l-2 border-rule pl-4 sm:flex-row sm:gap-5"><span className="shrink-0 text-sm text-muted">{t.date}</span><span>{t.event}</span></li>
            ))}</ol>
          </div>}
        </section>
      )}
    </div>
  )
}

function FactSection({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  if (!count) return null
  return <details className="panel" open>
    <summary className="font-serif text-xl font-semibold">{title} <span className="ml-2 font-sans text-sm font-normal text-muted">{count}</span></summary>
    <div className="mt-5">{children}</div>
  </details>
}

function TechField({ label, value }: { label: string; value: string }) {
  return <div><h4 className="mb-2 font-medium">{label}</h4><p className="max-w-[68ch] leading-7">{value}</p></div>
}
