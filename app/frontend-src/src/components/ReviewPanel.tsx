import { useEffect, useRef, useState } from 'react'
import { reviewRequest } from '../api'
import type { Reviewer, ReviewRun, ReviewAction, ReviewEvidence, ReviewClarification } from '../types'

const LABELS: Record<string, string> = {
  unavailable: 'Unavailable', conflicting: 'Conflicting records', documented: 'Documented', suspected: 'Suspected', historical: 'Historical', negated: 'Negated',
  ai_suggested: 'AI suggested', computed: 'Calculated', reviewer_supplied: 'Reviewer supplied',
  ruled_out: 'Ruled out',
  pending: 'Needs review', accepted: 'Accepted', edited: 'Edited', rejected: 'Rejected',
  clarification_requested: 'Needs clarification',
}

export function ReviewPanel({ run, onChange }: { run: ReviewRun; onChange: (run: ReviewRun) => void }) {
  const [reviewer, setReviewer] = useState<Reviewer | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [active, setActive] = useState<{ id: string; action: ReviewAction } | null>(null)
  const [reason, setReason] = useState('')
  const [edited, setEdited] = useState('')
  const [editedData, setEditedData] = useState<Record<string, string>>({})
  const [evidence, setEvidence] = useState<ReviewEvidence | null>(null)
  const [history, setHistory] = useState<{ events: { event: string; at: string; reviewer: Reviewer | null; details: Record<string, unknown> }[]; chain_valid: boolean } | null>(null)
  const [finalOutput, setFinalOutput] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    reviewRequest<{ reviewer: Reviewer | null }>('/session').then(data => {
      if (alive) setReviewer(data.reviewer)
    }).catch(() => { if (alive) setError('Could not load your reviewer session.') })
    return () => { alive = false }
  }, [])

  async function save(path: string, body?: unknown) {
    setSaving(true); setError('')
    try {
      const updated = await reviewRequest<ReviewRun>(`/runs/${run.id}${path}`, body)
      onChange(updated); setActive(null); setReason(''); setHistory(null); setFinalOutput(null)
    } catch (err) {
      setError((err as Error).message)
    } finally { setSaving(false) }
  }

  async function reload() {
    setSaving(true)
    try { onChange(await reviewRequest<ReviewRun>(`/runs/${run.id}`)); setError(''); setActive(null); setEvidence(null) }
    catch (err) { setError((err as Error).message) }
    finally { setSaving(false) }
  }

  const pending = run.findings.filter(f => f.status === 'pending' || f.status === 'clarification_requested').length
  const unresolved = run.clarifications.filter(q => q.status === 'pending')
  const finalized = run.status === 'finalized'
  const extraction = run.kind === 'extraction'
  const canFinalize = run.findings.length > 0 && pending === 0 && unresolved.length === 0

  return <section className="space-y-5" aria-labelledby="review-title">
    <div className="panel space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h3 id="review-title" className="font-serif text-xl font-semibold">{finalized ? 'Review finalized' : extraction ? 'Review extracted fields' : 'Review findings'}</h3>
          <p className="mt-1 text-sm text-muted">{finalized ? 'Accepted findings and corrections are saved.' : `${pending} finding${pending === 1 ? '' : 's'} need review${unresolved.length ? ` · ${unresolved.length} clarification${unresolved.length === 1 ? '' : 's'} pending` : ''}`}</p>
        </div>
        <button className="secondary-button" disabled={saving} onClick={reload}>Reload review</button>
      </div>
      {extraction && <p className="max-w-[75ch] text-sm text-muted">{finalized ? 'Approved fields are saved to the patient record with their source and recorded status.' : 'Check each field against its source. Accepted fields and corrections enter the patient record when you finalize this review.'}</p>}
      {extraction && !!run.analysis?.warnings?.length && <ul className="list-disc space-y-2 pl-5 text-sm text-caution">{run.analysis.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
      {!reviewer && !finalized ? <form className="flex flex-wrap items-end gap-3" onSubmit={async e => {
        e.preventDefault(); setError(''); setSaving(true)
        try { const result = await reviewRequest<{ reviewer: Reviewer }>('/session', { name }); setReviewer(result.reviewer) }
        catch (err) { setError((err as Error).message) } finally { setSaving(false) }
      }}>
        <label className="space-y-1 text-sm"><span>Your reviewer name</span><input required minLength={2} maxLength={80} value={name} onChange={e => setName(e.target.value)} className="block rounded-lg border border-rule px-3 py-2 text-base" /></label>
        <button className="primary-button" disabled={saving}>Start review</button>
      </form> : reviewer && <div className="flex flex-wrap items-center gap-3 text-sm text-muted"><p>Reviewing as {reviewer.name}</p>{!finalized && <button className="underline underline-offset-4" onClick={() => { setName(''); setReviewer(null) }}>Change reviewer</button>}</div>}
      {error && <p role="alert" className="rounded-lg bg-critical-subtle p-3 text-critical">{error}</p>}
    </div>

    {unresolved.map(q => <ClarificationForm key={q.id} question={q} disabled={!reviewer || saving || finalized} onSubmit={(body, finding) => save(`/clarifications/${q.id}${finding ? '/response' : ''}`, { ...body, version: run.version })} />)}

    {run.findings.length === 0 && <p className="panel text-muted">{extraction ? 'No supported fields were found. Use explicit English field labels, medication lists, or laboratory tables. Keep the original document for manual review.' : 'No reviewable findings were produced. Resolve missing inputs or run a new analysis.'}</p>}
    {run.findings.map(finding => <article key={finding.id} className="panel space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h4 className="font-medium">{finding.title}</h4>
        <div className="flex flex-wrap gap-2"><span className="status-badge">{LABELS[finding.assertion] || finding.assertion}</span><span className={`status-badge ${finding.status === 'rejected' ? 'text-critical' : finding.status === 'pending' ? 'text-caution' : 'text-accent'}`}>{LABELS[finding.status]}</span></div>
      </div>
      {finding.extracted ? <dl className="grid gap-3 sm:grid-cols-2">{finding.field_schema?.map(field => {
        const value = (finding.decision?.edited_data || finding.extracted)?.data[field.name]
        return value ? <div key={field.name}><dt className="text-sm text-muted">{field.label}</dt><dd className="mt-1 whitespace-pre-wrap break-words">{field.choices.length ? value.replaceAll('_', ' ') : value}</dd></div> : null
      })}</dl> : <p className="whitespace-pre-wrap break-words leading-7">{finding.decision?.edited_text || finding.original_text}</p>}
      {finding.decision?.edited_text && <details><summary className="text-sm text-muted">Original suggestion</summary><p className="mt-2 whitespace-pre-wrap text-sm">{finding.original_text}</p></details>}
      {finding.decision && <p className="text-sm text-muted">{finding.decision.reviewer.name} · {new Date(finding.decision.at).toLocaleString()}<br />{finding.decision.reason}</p>}
      {finding.assertion === 'conflicting' && <p className="rounded-lg bg-caution-subtle p-3 text-sm text-caution">The record contains conflicting assertions. Inspect the sources and edit, reject, or request clarification.</p>}
      {finding.evidence.length ? <div className="flex flex-wrap gap-2">{finding.evidence.map((span, i) => <button key={`${span.source_id}:${span.start}:${i}`} className="secondary-button text-left" onClick={() => setEvidence(span)}>
        View {run.sources[span.source_id]?.label || 'source'}{span.assertion !== 'documented' ? ` · ${LABELS[span.assertion] || span.assertion}` : ''}
      </button>)}</div> : <p className="text-sm text-caution">No exact source passage is linked. Review this inference before using it.</p>}
      {!finalized && <div className="flex flex-wrap gap-2">{([
        ['accepted', 'Accept'], ['edited', 'Edit'], ['rejected', 'Reject'], ['clarification_requested', 'Ask for clarification'],
      ] as [ReviewAction, string][]).map(([action, label]) => <button key={action} className="secondary-button" disabled={!reviewer || saving || finding.status === 'clarification_requested' || (action === 'accepted' && (!finding.evidence.length || finding.assertion === 'conflicting'))} onClick={() => {
        setActive({ id: finding.id, action }); setReason(''); setEdited(finding.decision?.edited_text || finding.original_text)
        setEditedData({ ...(finding.decision?.edited_data || finding.extracted)?.data })
      }}>{label}</button>)}</div>}
      {active?.id === finding.id && <form className="space-y-3 border-t border-rule pt-4" onSubmit={e => {
        e.preventDefault()
        save(`/findings/${encodeURIComponent(finding.id)}/decision`, { version: run.version, action: active.action, reason, ...(active.action === 'edited' ? finding.extracted ? { edited_data: editedData } : { edited_text: edited } : {}) })
      }}>
        {active.action === 'edited' && (finding.extracted ? <div className="grid gap-4 sm:grid-cols-2">{finding.field_schema?.map(field => <label key={field.name} className="block text-sm">{field.label}{field.required ? ' *' : ''}
          {field.choices.length ? <select required={field.required} value={editedData[field.name] || ''} onChange={e => setEditedData({ ...editedData, [field.name]: e.target.value })} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base">{field.choices.map(choice => <option key={choice} value={choice}>{choice.replaceAll('_', ' ')}</option>)}</select> : <input required={field.required} maxLength={2000} value={editedData[field.name] || ''} onChange={e => setEditedData({ ...editedData, [field.name]: e.target.value })} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" />}
        </label>)}</div> : <label className="block text-sm">Corrected finding<textarea required value={edited} onChange={e => setEdited(e.target.value)} rows={4} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /></label>)}
        <label className="block text-sm">{active.action === 'clarification_requested' ? 'What needs clarification?' : 'Reason for your decision'}<textarea required minLength={3} maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} rows={2} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /></label>
        <div className="flex gap-2"><button className="primary-button" disabled={saving}>Save decision</button><button type="button" className="secondary-button" onClick={() => setActive(null)}>Cancel</button></div>
      </form>}
    </article>)}

    <div className="panel space-y-4">
      <div className="flex flex-wrap gap-3">
        {!finalized && <button className="primary-button" disabled={!reviewer || saving || !canFinalize} onClick={() => save('/finalize', { version: run.version })}>{extraction ? 'Finalize and save fields' : 'Finalize review'}</button>}
        {finalized && <button className="primary-button" onClick={async () => {
          try { setFinalOutput(JSON.stringify(await reviewRequest(`/runs/${run.id}/final`), null, 2)) }
          catch (err) { setError((err as Error).message) }
        }}>View finalized findings</button>}
        <button className="secondary-button" onClick={async () => {
          if (history) { setHistory(null); return }
          try { setHistory(await reviewRequest(`/runs/${run.id}/audit`)) }
          catch (err) { setError((err as Error).message) }
        }}>{history ? 'Hide history' : 'Review history'}</button>
      </div>
      {!finalized && !canFinalize && <p className="text-sm text-muted">Review every finding and resolve or skip clarifications before finalizing.</p>}
      {history && <div className="space-y-3 text-sm"><p className={history.chain_valid ? 'text-accent' : 'text-critical'}>{history.chain_valid ? 'Audit chain intact' : 'Audit integrity check failed'}</p>
        <ol className="space-y-3">{history.events.map((event, i) => <li key={i}><p className="font-medium">{event.event.replaceAll('_', ' ')}</p><p className="text-muted">{event.reviewer?.name || 'Analysis'} · {new Date(event.at).toLocaleString()}</p><details className="mt-2"><summary>View change</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-paper p-3 text-sm">{JSON.stringify(event.details, null, 2)}</pre></details></li>)}</ol>
      </div>}
      {finalOutput && <pre className="max-h-96 overflow-auto rounded-lg bg-paper p-4 text-sm">{finalOutput}</pre>}
    </div>
    {evidence && <EvidenceViewer evidence={evidence} run={run} onClose={() => setEvidence(null)} />}
  </section>
}

function ClarificationForm({ question, disabled, onSubmit }: { question: ReviewClarification; disabled: boolean; onSubmit: (body: Record<string, unknown>, finding: boolean) => void }) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const [response, setResponse] = useState('')
  const [skip, setSkip] = useState(false)
  return <form className="panel space-y-4 border-caution/40" onSubmit={e => {
    e.preventDefault()
    const parsed = Object.fromEntries((question.fields || []).map(field => [field.name, field.type === 'boolean' ? values[field.name] === 'true' : field.type === 'number' ? Number(values[field.name]) : values[field.name]]))
    onSubmit(question.kind === 'finding' ? { response } : { action: skip ? 'skip' : 'answer', values: skip ? {} : parsed, reason }, question.kind === 'finding')
  }}>
    <h4 className="font-medium">{question.kind === 'calculator' ? 'Missing calculator inputs' : 'Clarification requested'}</h4>
    <p>{question.question}</p>
    {question.kind === 'finding' ? <label className="block text-sm">Your clarification<textarea required minLength={3} value={response} onChange={e => setResponse(e.target.value)} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" disabled={disabled} /></label> : <>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={skip} onChange={e => setSkip(e.target.checked)} disabled={disabled} />Skip this calculator</label>
      {!skip && <div className="grid gap-4 sm:grid-cols-2">{question.fields?.map(field => <label key={field.name} className="block text-sm">{field.label}
        {field.type === 'number' ? <input aria-label={field.label} type="number" required min="0.01" max="1000" step="any" value={values[field.name] || ''} onChange={e => setValues({ ...values, [field.name]: e.target.value })} disabled={disabled} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /> :
          <select aria-label={field.label} required value={values[field.name] || ''} onChange={e => setValues({ ...values, [field.name]: e.target.value })} disabled={disabled} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base"><option value="">Choose…</option>{(field.type === 'boolean' ? ['true', 'false'] : field.choices).map(value => <option key={value} value={value}>{value === 'true' ? 'Yes' : value === 'false' ? 'No' : value.replaceAll('_', ' ')}</option>)}</select>}
      </label>)}</div>}
      <label className="block text-sm">Source or reason<textarea required minLength={3} maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} disabled={disabled} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /></label>
    </>}
    <button className="primary-button" disabled={disabled}>{question.kind === 'finding' ? 'Save clarification' : skip ? 'Skip calculator' : 'Save inputs and recalculate'}</button>
  </form>
}

function EvidenceViewer({ evidence, run, onClose }: { evidence: ReviewEvidence; run: ReviewRun; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const mark = useRef<HTMLElement>(null)
  const source = run.sources[evidence.source_id]
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    mark.current?.scrollIntoView({ block: 'center' })
    return () => element?.close()
  }, [evidence])
  const text = Array.from(source?.text || '')
  return <dialog ref={dialog} onClose={onClose} className="m-auto max-h-[85dvh] w-[min(90vw,52rem)] rounded-xl border border-rule bg-sheet p-5 text-ink shadow-xl backdrop:bg-ink/40">
    <div className="flex items-center justify-between gap-3"><h3 className="font-serif text-xl font-semibold">{source?.label || 'Source passage'}</h3><button className="secondary-button" onClick={onClose}>Close source</button></div>
    <p className="my-3 text-sm text-muted">{LABELS[evidence.assertion] || evidence.assertion} · {source?.kind === 'computed' ? 'Calculator trace' : 'Exact source passage'}</p>
    <div className="max-h-[60dvh] overflow-y-auto whitespace-pre-wrap break-words border-t border-rule pt-4 leading-7">{text.slice(0, evidence.start).join('')}<mark ref={mark} className="rounded bg-caution-subtle px-1 text-ink">{text.slice(evidence.start, evidence.end).join('')}</mark>{text.slice(evidence.end).join('')}</div>
  </dialog>
}
