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
      <h2 className="text-lg font-semibold text-gray-900">Documents</h2>

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
        className={`rounded-xl border-2 border-dashed p-10 text-center transition ${
          isDemo ? 'cursor-not-allowed border-gray-200 bg-gray-50 opacity-50' : dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300 bg-white cursor-pointer hover:border-gray-400'
        }`}
      >
        <p className="text-sm font-medium text-gray-700">Drop patient documents here</p>
        <p className="text-xs text-gray-500">or click to browse — PDF, image, or text files</p>
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
            <div key={i} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm">
              <span className="truncate text-gray-800">{q.name}</span>
              <span
                className={
                  q.status === 'done' ? 'text-emerald-600' : q.status === 'error' ? 'text-red-600' : 'text-gray-400'
                }
              >
                {q.status === 'uploading' ? 'Uploading…' : q.status === 'done' ? '✓ Ready' : 'Failed'}
              </span>
            </div>
          ))}
        </div>
      )}

      {docs.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            {isDemo ? 'Demo documents' : 'Uploaded documents'}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {docs.map((doc, i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-center gap-2">
                  <span>{doc.icon || '📄'}</span>
                  <span className="text-sm font-medium text-gray-900">{doc.label}</span>
                </div>
                {doc.description && <p className="mt-1 text-xs text-gray-500">{doc.description}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {isDemo && (
        <p className="text-xs text-gray-400">
          This is demo data — uploading new documents is disabled while viewing a demo patient.
        </p>
      )}
    </div>
  )
}
