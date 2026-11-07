import { useEffect, useRef, useState } from 'react'
import { api, reviewRequest } from '../api'
import { Icon } from '../components/Icon'
import { ReviewPanel } from '../components/ReviewPanel'
import type { PatientData, ReviewRun } from '../types'

type SavedRun = { id: string; created_at: string; status: string }

export function DocumentsTab({ patient, onRecordChange }: { patient: PatientData; onRecordChange: () => Promise<void> }) {
  const [run, setRun] = useState<ReviewRun | null>(null)
  const [runs, setRuns] = useState<SavedRun[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [adding, setAdding] = useState(false)
  const [sourceName, setSourceName] = useState('')
  const [text, setText] = useState('')
  const reviewRef = useRef<HTMLDivElement>(null)
  const docs = Object.entries(patient.source_documents || {})
  const patientPath = `/patients/${encodeURIComponent(patient.patient_id)}`

  useEffect(() => {
    let alive = true
    reviewRequest<{ runs: SavedRun[] }>(`${patientPath}/runs?kind=extraction`).then(async data => {
      if (!alive) return
      setRuns(data.runs)
      if (data.runs.length) {
        const latest = await reviewRequest<ReviewRun>(`/runs/${data.runs[0].id}`)
        if (alive) setRun(latest)
      }
    }).catch(() => { if (alive) setError('Could not load saved document reviews. Reload to try again.') })
    return () => { alive = false }
  }, [patientPath])

  function openRun(next: ReviewRun) {
    setRun(next)
    setRuns(prev => [{ id: next.id, created_at: next.created_at, status: next.status }, ...prev.filter(item => item.id !== next.id)])
    requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  async function extract(name: string, content: string) {
    setBusy(true); setError(''); setMessage('')
    try {
      openRun(await reviewRequest<ReviewRun>(`${patientPath}/extract`, { source_name: name, text: content }))
      setAdding(false)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  async function upload(file: File) {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api.ingestDocument(patient.patient_id, file)
      if (result.review_run) openRun(result.review_run)
      setMessage(result.extraction_warning || `${file.name} is ready for search. Review its extracted fields below.`)
      setAdding(false)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  function updateRun(next: ReviewRun) {
    setRun(next)
    setRuns(prev => prev.map(item => item.id === next.id ? { ...item, status: next.status } : item))
    if (next.status === 'finalized') {
      onRecordChange().catch(() => setError('Fields are saved. Reload the page to refresh the patient record.'))
    }
  }

  return <div className="page-content space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="page-title">Documents</h2>
      <button className="primary-button" disabled={busy} aria-expanded={adding} onClick={() => setAdding(!adding)}>{adding ? 'Close document form' : 'Add document'}</button>
    </div>
    {error && <p role="alert" className="panel text-critical">{error}</p>}
    {message && <p role="status" className="panel text-muted">{message}</p>}
    {busy && <p role="status" className="text-muted">Reading document and preparing fields…</p>}
    {adding && <section className="panel space-y-5" aria-label="Add document">
      <label className="block text-sm">Upload a document<input type="file" accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.txt,.docx" disabled={busy} className="mt-2 block max-w-full text-base" onChange={e => {
        const file = e.target.files?.[0]
        if (file) upload(file)
        e.target.value = ''
      }} /></label>
      <form className="space-y-4 border-t border-rule pt-5" onSubmit={e => { e.preventDefault(); extract(sourceName, text) }}>
        <p className="text-sm text-muted">Or paste document text to extract and review fields.</p>
        <label className="block text-sm">Document name<input required maxLength={200} value={sourceName} onChange={e => setSourceName(e.target.value)} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /></label>
        <label className="block text-sm">Document text<textarea required maxLength={100000} rows={7} value={text} onChange={e => setText(e.target.value)} className="mt-1 block w-full rounded-lg border border-rule p-3 text-base" /></label>
        <button className="primary-button" disabled={busy || !sourceName.trim() || !text.trim()}>Extract fields</button>
      </form>
    </section>}
    {docs.length ? <div className="space-y-3">{docs.map(([name, content]) => <details key={name} className="panel document-details">
      <summary className="document-summary font-medium capitalize"><Icon name="document" /><span className="min-w-0 flex-1 break-words">{name.replaceAll('_', ' ')}</span><Icon name="chevron" className="document-chevron" /></summary>
      <div className="mt-4"><button className="secondary-button" disabled={busy || !content.trim()} onClick={() => extract(name.replaceAll('_', ' '), content)}>Extract fields from this document</button></div>
      <div className="mt-5 max-h-[60vh] overflow-y-auto border-t border-rule pt-4"><p className="max-w-[75ch] whitespace-pre-wrap break-words leading-7">{content || 'No text available.'}</p></div>
    </details>)}</div> : <p className="panel text-muted">No source documents attached. Add a document to extract and review its fields.</p>}
    {!!runs.length && <label className="block text-sm text-muted">Saved document reviews<select aria-label="Saved document reviews" value={run?.id || ''} disabled={busy} className="mt-2 block w-full rounded-lg border border-rule bg-sheet p-3 text-base text-ink" onChange={async e => {
      setBusy(true); setError('')
      try { setRun(await reviewRequest<ReviewRun>(`/runs/${e.target.value}`)) }
      catch (err) { setError((err as Error).message) } finally { setBusy(false) }
    }}><option value="" disabled>Select a document review</option>{runs.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.status.replaceAll('_', ' ')}</option>)}</select></label>}
    <div ref={reviewRef}>{run && <ReviewPanel key={run.id} run={run} onChange={updateRun} />}</div>
  </div>
}
