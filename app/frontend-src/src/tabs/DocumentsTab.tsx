import { useRef, useState } from 'react'
import { api } from '../api'
import type { PatientData } from '../types'

interface QueueItem {
  name: string
  status: 'uploading' | 'done' | 'error'
}

export function DocumentsTab({ patient, isDemo }: { patient: PatientData; isDemo: boolean }) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const docs = patient.source_documents || []

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
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <h2 className="font-serif text-lg text-ink">Documents</h2>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          if (!isDemo) setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (!isDemo) handleFiles(Array.from(e.dataTransfer.files))
        }}
        onClick={() => !isDemo && inputRef.current?.click()}
        className={`border-2 border-dashed p-10 text-center transition-colors ${
          isDemo
            ? 'cursor-not-allowed border-rule bg-sheet opacity-50'
            : dragOver
              ? 'border-accent bg-accent-subtle'
              : 'cursor-pointer border-rule bg-sheet hover:border-accent/50'
        }`}
      >
        <p className="text-sm font-medium text-ink/80">Drop patient documents here</p>
        <p className="text-xs text-ink/50">or click to browse — PDF, image, or text files</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          disabled={isDemo}
          accept=".pdf,.jpg,.jpeg,.png,.tiff,.txt,.docx"
          onChange={(e) => {
            if (e.target.files) handleFiles(Array.from(e.target.files))
            e.target.value = ''
          }}
        />
      </div>

      {queue.length > 0 && (
        <div className="space-y-2">
          {queue.map((q, i) => (
            <div key={i} className="flex items-center justify-between border border-rule bg-sheet px-4 py-2 text-sm">
              <span className="truncate text-ink/80">{q.name}</span>
              <span
                className={
                  q.status === 'done' ? 'font-mono text-xs text-accent' : q.status === 'error' ? 'font-mono text-xs text-critical' : 'font-mono text-xs text-ink/40'
                }
              >
                {q.status === 'uploading' ? 'Uploading…' : q.status === 'done' ? 'Ready' : 'Failed'}
              </span>
            </div>
          ))}
        </div>
      )}

      {docs.length > 0 && (
        <div>
          <div className="mb-2 font-serif text-base text-ink">{isDemo ? 'Demo documents' : 'Uploaded documents'}</div>
          <div className="divide-y divide-rule border-t border-rule">
            {docs.map((doc, i) => (
              <div key={i} className="flex items-start gap-3 py-3">
                <span aria-hidden>{doc.icon || '📄'}</span>
                <div>
                  <div className="text-sm font-medium text-ink">{doc.label}</div>
                  {doc.description && <p className="mt-0.5 text-xs text-ink/50">{doc.description}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isDemo && (
        <p className="text-xs text-ink/40">This is demo data — uploading new documents is disabled while viewing a demo patient.</p>
      )}
    </div>
  )
}
