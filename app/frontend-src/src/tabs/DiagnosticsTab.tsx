import { useState, type ReactNode } from 'react'
import { api } from '../api'
import { DetailToggle } from '../components/DetailToggle'
import {
  DIAGNOSTIC_STEP_LABELS,
  DIAGNOSTIC_STEP_ORDER,
  DIAGNOSTIC_TECHNICAL_LABELS,
  explainCalculatorKey,
  explainIcdCode,
  sanitizeAuditText,
} from '../labels'
import type { AgentEvent, PatientData } from '../types'

type StepStatus = 'pending' | 'active' | 'done'

export function DiagnosticsTab({ patient }: { patient: PatientData }) {
  const [technical, setTechnical] = useState(false)
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(false)
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [events, setEvents] = useState<AgentEvent[]>([])

  const interactionsEvent = events.find((e) => e.node === 'drug_graph')
  const diagnosisEvent = events.find((e) => e.node === 'diagnosis')
  const calcEvent = events.find((e) => e.node === 'tool_node')
  const summaryEvent = events.find((e) => e.node === 'summarizer')
  const errored = events.some((e) => e.node === '__error__')

  function run() {
    setRunning(true)
    setStarted(true)
    setEvents([])
    setCompletedSteps(new Set())

    const payload = patient._caseKey ? { case: patient._caseKey } : patient
    api
      .runAgentWs(patient.patient_id || 'demo', payload, (event) => {
        setEvents((prev) => [...prev, event])
        if (event.node !== '__start__') {
          setCompletedSteps((prev) => new Set(prev).add(event.node))
        }
        if (event.node === '__done__' || event.node === '__error__') {
          setRunning(false)
        }
      })
      .catch(() => setRunning(false))
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-lg text-ink">Diagnostics</h2>
        <DetailToggle technical={technical} onChange={setTechnical} label="Show technical log" />
      </div>

      {!started && (
        <div className="border border-rule bg-sheet p-6 text-center">
          <p className="mb-4 text-sm text-ink/70">
            Run the assistant to review this patient's medications, consider possible diagnoses, and generate a
            clinical summary.
          </p>
          <button onClick={run} className="bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover">
            Run analysis
          </button>
        </div>
      )}

      {started && (
        <div className="border border-rule bg-sheet p-5">
          <div className="space-y-2">
            {DIAGNOSTIC_STEP_ORDER.map((step, idx) => {
              const nextPendingIdx = DIAGNOSTIC_STEP_ORDER.findIndex((s) => !completedSteps.has(s))
              const status: StepStatus = completedSteps.has(step) ? 'done' : running && idx === nextPendingIdx ? 'active' : 'pending'
              return <StepRow key={step} label={DIAGNOSTIC_STEP_LABELS[step]} status={status} />
            })}
          </div>
          {!running && (
            <button onClick={run} className="mt-4 font-mono text-xs text-accent hover:text-accent-hover">
              Run again
            </button>
          )}
        </div>
      )}

      {errored && (
        <div className="border border-critical/30 bg-critical-subtle p-4 text-sm text-critical">
          Something went wrong while running the analysis. You can try again.
        </div>
      )}

      {interactionsEvent && <InteractionsPanel event={interactionsEvent} />}
      {diagnosisEvent && <DiagnosesPanel event={diagnosisEvent} />}
      {calcEvent && <CalculatorsPanel event={calcEvent} technical={technical} />}
      {summaryEvent && <SummaryPanel event={summaryEvent} />}

      {technical && events.length > 0 && (
        <div className="space-y-1.5 border-t-2 border-accent pt-4 font-mono text-xs text-ink/70">
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
    <div className="flex items-center gap-3 text-sm">
      <span
        className={`flex h-4 w-4 shrink-0 items-center justify-center text-xs ${
          status === 'done' ? 'bg-accent text-white' : status === 'active' ? 'border border-accent text-accent' : 'border border-rule text-ink/30'
        }`}
      >
        {status === 'done' ? '✓' : status === 'active' ? '…' : ''}
      </span>
      <span className={status === 'pending' ? 'text-ink/35' : 'text-ink/85'}>{label}</span>
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
        <p className="text-sm text-ink/60">No medication interactions were found.</p>
      </Panel>
    )
  }
  return (
    <Panel title="Medication check" badge={`Risk: ${risk}`}>
      <div className="space-y-2">
        {interactions.map((i, idx) => (
          <div key={idx} className="border-b border-rule pb-2 last:border-0">
            <div className="text-sm font-medium text-ink">{((i.drugs as string[]) || []).join(' + ')}</div>
            <div className="text-xs text-ink/50">{i.clinical_significance as string}</div>
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
                <span className="text-sm font-medium text-ink">{dx.name as string}</span>
                {isPrimary && <span className="font-mono text-[10px] text-accent">most likely</span>}
              </div>
              {hint && <div className="text-xs text-ink/50">{hint}</div>}
              <p className="mt-1 text-sm text-ink/70">{dx.reasoning as string}</p>
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
  return (
    <Panel title="Clinical calculators">
      <div className="space-y-3">
        {results.map((r, idx) => {
          if (r.error) return null
          const res = (r.result as Record<string, unknown>) || {}
          return (
            <div key={idx} className="border-b border-rule pb-2 last:border-0">
              <div className="text-sm font-medium text-ink">{(res.tool as string) || (r.tool as string)}</div>
              {technical ? (
                <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-xs text-ink/60">
                  {Object.entries(res)
                    .filter(([k]) => k !== 'tool')
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <span className="text-ink/35">{explainCalculatorKey(k)}</span>
                        <span>{String(v)}</span>
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-xs text-ink/50">Result available in technical view.</p>
              )}
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
      {summary.patient_facing_summary && <p className="text-sm text-ink/80">{summary.patient_facing_summary}</p>}
      {summary.follow_up_actions?.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-ink/70">
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
    <section className="border-t border-rule pt-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-serif text-base text-ink">{title}</h3>
        {badge && <span className="font-mono text-xs text-ink/50">{badge}</span>}
      </div>
      {children}
    </section>
  )
}
