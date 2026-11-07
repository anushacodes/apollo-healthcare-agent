import { useEffect, useState, type ReactNode } from 'react'
import { api, reviewRequest } from '../api'
import { ReviewPanel } from '../components/ReviewPanel'
import { DetailToggle } from '../components/DetailToggle'
import {
  DIAGNOSTIC_STEP_LABELS,
  DIAGNOSTIC_STEP_ORDER,
  DIAGNOSTIC_TECHNICAL_LABELS,
  explainCalculatorKey,
  explainIcdCode,
  sanitizeAuditText,
} from '../labels'
import type { AgentEvent, PatientData, ReviewRun } from '../types'

type StepStatus = 'pending' | 'active' | 'done'

export function DiagnosticsTab({ patient }: { patient: PatientData }) {
  const [technical, setTechnical] = useState(false)
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(false)
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [reviewRun, setReviewRun] = useState<ReviewRun | null>(null)
  const [savedRuns, setSavedRuns] = useState<{ id: string; created_at: string; status: string }[]>([])
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    reviewRequest<{ runs: { id: string; created_at: string; status: string }[] }>(`/patients/${encodeURIComponent(patient.patient_id)}/runs`)
      .then(async data => {
        if (!alive) return
        setSavedRuns(data.runs)
        if (data.runs.length) {
          const latest = await reviewRequest<ReviewRun>(`/runs/${data.runs[0].id}`)
          if (alive) { setReviewRun(latest); setStarted(true) }
        }
      }).catch(() => { if (alive) setLoadError('Could not load saved reviews. Reload to try again.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [patient.patient_id])

  const interactionsEvent = events.find((e) => e.node === 'drug_graph')
  const diagnosisEvent = events.find((e) => e.node === 'diagnosis')
  const calcEvent = events.find((e) => e.node === 'tool_node')
  const summaryEvent = events.find((e) => e.node === 'summarizer')
  const errored = events.some((e) => e.node === '__error__')

  function run() {
    setRunning(true)
    setLoadError('')
    setReviewRun(null)
    setStarted(true)
    setEvents([])
    setCompletedSteps(new Set())

    const payload = patient._caseKey ? { case: patient._caseKey } : patient
    api
      .runAgentWs(patient.patient_id || 'demo', payload, (event) => {
        setEvents((prev) => [...prev, event])
        if (event.review_run) {
          const draft = event.review_run
          setReviewRun(draft)
          setSavedRuns(prev => [{ id: draft.id, created_at: draft.created_at, status: draft.status }, ...prev])
        }
        if (event.node !== '__start__') {
          setCompletedSteps((prev) => new Set(prev).add(event.node))
        }
        if (event.node === '__done__' || event.node === '__error__') {
          setRunning(false)
        }
      })
      .then(() => setRunning(false))
      .catch(() => { setRunning(false); setLoadError('Analysis could not complete. Please try again.') })
  }

  return (
    <div className="page-content space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-2xl text-ink">Analysis</h2>
        <DetailToggle technical={technical} onChange={setTechnical} label="Details" />
      </div>

      {loadError && <p role="alert" className="panel text-critical">{loadError}</p>}
      {!!savedRuns.length && <label className="block text-sm text-muted">Saved analyses<select aria-label="Saved analyses" className="mt-2 block w-full rounded-lg border border-rule bg-sheet p-3 text-base text-ink" value={reviewRun?.id || ''} disabled={running || loading} onChange={async e => {
        setLoading(true); setLoadError('')
        try { setReviewRun(await reviewRequest<ReviewRun>(`/runs/${e.target.value}`)); setEvents([]); setStarted(true) }
        catch { setLoadError('Could not open this analysis.') } finally { setLoading(false) }
      }}><option value="" disabled>Select an analysis</option>{savedRuns.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.status.replaceAll('_', ' ')}</option>)}</select></label>}
      {loading && <p role="status" className="text-muted">Loading saved analysis…</p>}
      {!started && !loading && (
        <div className="panel text-center">
          <p className="mb-4 text-base text-muted">
            Review medications, possible diagnoses, and clinical risk scores.
          </p>
          <button onClick={run} className="primary-button">
            Run analysis
          </button>
        </div>
      )}

      {started && events.length > 0 && (running || technical) && (
        <div className="panel">
          <div className="space-y-2">
            {DIAGNOSTIC_STEP_ORDER.map((step, idx) => {
              const nextPendingIdx = DIAGNOSTIC_STEP_ORDER.findIndex((s) => !completedSteps.has(s))
              const status: StepStatus = completedSteps.has(step) ? 'done' : running && idx === nextPendingIdx ? 'active' : 'pending'
              return <StepRow key={step} label={DIAGNOSTIC_STEP_LABELS[step]} status={status} />
            })}
          </div>
          {!running && (
            <button onClick={run} className="secondary-button mt-5">
              Run again
            </button>
          )}
        </div>
      )}

      {started && !running && !technical && <div className="flex items-center justify-between gap-3">
        <p role="status" className="text-sm text-muted">{errored ? 'Analysis interrupted' : reviewRun?.status === 'finalized' ? 'Review finalized' : 'Draft analysis'}</p>
        <button onClick={run} className="secondary-button">Run again</button>
      </div>}

      {errored && (
        <div className="border border-critical/30 bg-critical-subtle p-4 text-base text-critical">
          Something went wrong while running the analysis. You can try again.
        </div>
      )}

      {!reviewRun && interactionsEvent && <InteractionsPanel event={interactionsEvent} />}
      {!reviewRun && diagnosisEvent && <DiagnosesPanel event={diagnosisEvent} />}
      {!reviewRun && calcEvent && <CalculatorsPanel event={calcEvent} technical={technical} />}
      {!reviewRun && summaryEvent && <SummaryPanel event={summaryEvent} />}

      {reviewRun && <ReviewPanel key={reviewRun.id} run={reviewRun} onChange={setReviewRun} />}

      {technical && events.length > 0 && (
        <div className="space-y-1.5 border-t-2 border-accent pt-4 font-mono text-sm text-muted">
          <div className="mb-2 text-accent">Technical execution log</div>
          {events.map((e, i) => (
            <div key={i}>
              <span className="text-accent">[{DIAGNOSTIC_TECHNICAL_LABELS[e.node] || e.node}]</span>{' '}
              {sanitizeAuditText(e.audit_entry || e.error || '')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StepRow({ label, status }: { label: string; status: StepStatus }) {
  return (
    <div className="flex items-center gap-3 text-base">
      <span
        className={`flex h-4 w-4 shrink-0 items-center justify-center text-sm ${
          status === 'done' ? 'bg-accent text-white' : status === 'active' ? 'border border-accent text-accent' : 'border border-rule text-muted'
        }`}
      >
        {status === 'done' ? '✓' : status === 'active' ? '…' : ''}
      </span>
      <span className={status === 'pending' ? 'text-muted' : 'text-ink'}>{label}</span>
    </div>
  )
}

function InteractionsPanel({ event }: { event: AgentEvent }) {
  const data = (event.interactions || {}) as Record<string, unknown>
  const interactions = (data.interactions as Array<Record<string, unknown>>) || []
  const risk = (data.overall_risk as string) || 'unknown'
  if (!interactions.length) {
    return (
      <Panel title="Medication check">
        <p className="text-base text-muted">{data.error || risk === 'unknown' ? 'Medication analysis is unavailable. No safety conclusion can be drawn from this result.' : 'No medication interactions were identified in this analysis.'}</p>
      </Panel>
    )
  }
  return (
    <Panel title="Medication check" badge={`Risk: ${risk}`}>
      <div className="space-y-2">
        {interactions.map((i, idx) => (
          <div key={idx} className="border-b border-rule pb-2 last:border-0">
            <div className="text-base font-medium text-ink">{((i.drugs as string[]) || []).join(' + ')}</div>
            <div className="text-sm text-muted">{i.clinical_significance as string}</div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function DiagnosesPanel({ event }: { event: AgentEvent }) {
  const data = (event.diagnoses || {}) as Record<string, unknown>
  const proposed = (data.proposed_diagnoses as Array<Record<string, unknown>>) || []
  return (
    <Panel title="Possible diagnoses considered">
      <div className="space-y-3">
        {proposed.map((dx, idx) => {
          const icd = dx.icd_code as string | undefined
          const hint = explainIcdCode(icd)
          const isPrimary = dx.name === data.primary_diagnosis
          return (
            <div key={idx} className={`border-b border-rule pb-3 last:border-0 ${isPrimary ? 'border-l-2 border-l-accent pl-3' : ''}`}>
              <div className="flex items-center gap-2">
                <span className="text-base font-medium text-ink">{dx.name as string}</span>
                {isPrimary && <span className="text-sm font-medium text-accent">most likely</span>}
              </div>
              {hint && <div className="text-sm text-muted">{hint}</div>}
              <p className="mt-1 text-base text-muted">{dx.reasoning as string}</p>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function CalculatorsPanel({ event, technical }: { event: AgentEvent; technical: boolean }) {
  const results = event.calculator_results || []
  if (!results.length) return null
  const names: Record<string, string> = {
    ascvd_risk_calculator: 'ASCVD · 10-year cardiovascular risk',
    wells_dvt_score: 'Wells · DVT probability',
    cha2ds2_vasc_score: 'CHA₂DS₂-VASc · Stroke risk',
  }
  const labels: Record<string, string> = {
    '10_year_risk_pct': '10-year risk', risk_category: 'Risk category', score: 'Score',
    dvt_probability: 'DVT probability', approximate_dvt_likelihood: 'Estimated likelihood',
    annual_stroke_risk_estimate: 'Estimated annual stroke risk',
  }
  return (
    <Panel title="Clinical calculators">
      <div className="space-y-6">
        {results.map((r, idx) => {
          const res = (r.result as Record<string, unknown>) || {}
          const error = r.error || res.error
          return (
            <div key={idx} className="border-b border-rule pb-5 last:border-0 last:pb-0">
              <h4 className="mb-3 font-medium">{names[r.tool as string] || (res.tool as string) || (r.tool as string)}</h4>
              {error ? <p className="rounded-lg bg-caution-subtle p-3 text-sm text-caution">{String(error)}</p> : <>
                <dl className="grid gap-3 sm:grid-cols-2">
                  {Object.entries(labels).filter(([key]) => res[key] != null).map(([key, label]) => (
                    <div key={key} className="rounded-lg bg-paper p-4">
                      <dt className="text-sm text-muted">{label}</dt>
                      <dd className="mt-1 text-xl font-semibold tabular-nums">{String(res[key])}{key === '10_year_risk_pct' ? '%' : ''}</dd>
                    </div>
                  ))}
                </dl>
                {res.recommendation != null && <p className="mt-4 leading-7">{String(res.recommendation)}</p>}
                {technical && <dl className="mt-4 space-y-2 border-t border-rule pt-4 text-sm">
                  {Object.entries(res).filter(([key]) => key !== 'tool').map(([key, value]) => (
                    <div key={key} className="flex flex-wrap justify-between gap-2"><dt className="text-muted">{explainCalculatorKey(key)}</dt><dd className="font-mono">{String(value)}</dd></div>
                  ))}
                </dl>}
              </>}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function SummaryPanel({ event }: { event: AgentEvent }) {
  const summary = event.final_summary
  if (!summary) return null
  return (
    <Panel title="Summary">
      {summary.patient_facing_summary && <p className="text-base text-ink">{summary.patient_facing_summary}</p>}
      {summary.follow_up_actions?.length > 0 && (
        <ul className="mt-3 space-y-1 text-base text-muted">
          {summary.follow_up_actions.map((a, i) => (
            <li key={i} className="border-l-2 border-rule pl-3">
              {a}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function Panel({ title, badge, children }: { title: string; badge?: string; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-serif text-xl font-semibold text-ink">{title}</h3>
        {badge && <span className="font-mono text-sm text-muted">{badge}</span>}
      </div>
      {children}
    </section>
  )
}
