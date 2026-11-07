import { useRef, useState } from 'react'
import { api } from '../api'
import type { PatientData } from '../types'

interface QueueItem {
  name: string
  status: 'uploading' | 'done' | 'error'
}

export function DocumentsTab({ patient, readOnly }: { patient: PatientData; readOnly: boolean }) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const docs = Object.entries(patient.source_documents || {})

  async function handleFiles(files: File[]) {
    for (const file of files) {
      setQueue((prev) => [...prev, { name: file.name, status: 'uploading' }])
      try {
        await api.ingestDocument(patient.patient_id, file)
        setQueue((prev) => prev.map((q) => (q.name === file.name ? { ...q, status: 'done' } : q)))
      } catch {
        setQueue((prev) => prev.map((q) => (q.name === file.name ? { ...q, status: 'error' } : q)))
      }
    }
  }

  return (
    <div className="page-content space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-2xl font-semibold">Documents</h2>
        {!readOnly && <>
          <button className="primary-button" onClick={() => inputRef.current?.click()}>Add documents</button>
          <input ref={inputRef} type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.tiff,.txt,.docx" onChange={(e) => {
            if (e.target.files) handleFiles(Array.from(e.target.files))
            e.target.value = ''
          }} />
        </>}
      </div>
      {queue.length > 0 && <div className="space-y-2" aria-live="polite">{queue.map((item, i) => (
        <div key={i} className="panel flex flex-wrap justify-between gap-2">
          <span className="break-words">{item.name}</span>
          <span className={`text-sm ${item.status === 'error' ? 'text-critical' : 'text-muted'}`}>
            {item.status === 'uploading' ? 'Uploading…' : item.status === 'done' ? 'Ready' : 'Upload failed — try again'}
          </span>
        </div>
      ))}</div>}
      {docs.length ? <div className="space-y-3">{docs.map(([name, text]) => (
        <details key={name} className="panel">
          <summary className="font-medium capitalize">{name.replaceAll('_', ' ')}</summary>
          <div className="mt-5 max-h-[60vh] overflow-y-auto border-t border-rule pt-4">
            <p className="max-w-[75ch] whitespace-pre-wrap break-words leading-7">{text || 'No text available.'}</p>
          </div>
        </details>
      ))}</div> : <p className="panel text-muted">No documents attached to this record.</p>}
    </div>
  )
}
