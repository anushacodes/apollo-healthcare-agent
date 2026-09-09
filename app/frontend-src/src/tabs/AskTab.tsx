import { useState } from 'react'
import { api } from '../api'
import { DetailToggle } from '../components/DetailToggle'
import { ASK_STEP_LABELS, ASK_TECHNICAL_LABELS, faithfulnessPlain } from '../labels'
import type { AskEvent, Citation, EvalScores, PatientData } from '../types'

interface TraceLine {
  node: string
  message: string
  type: 'thinking' | 'result' | 'error'
}

interface Message {
  role: 'user' | 'agent'
  text?: string
  trace: TraceLine[]
  answer?: string
  citations?: Citation[]
  evalScores?: EvalScores
  isRefusal?: boolean
  busy?: boolean
}

const SUGGESTIONS = [
  'What are the key concerns for this patient?',
  'Summarise the most recent lab abnormalities.',
  'What is the current standard of care for the primary diagnosis?',
  'Are there any drug interaction risks in the current medications?',
]

export function AskTab({ patient }: { patient: PatientData }) {
  const [technical, setTechnical] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)

  function ask(question: string) {
    if (!question.trim() || busy) return
    setBusy(true)
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: question, trace: [] }, { role: 'agent', trace: [], busy: true }])

    const agentIndex = messages.length + 1

    function update(fn: (m: Message) => Message) {
      setMessages((prev) => prev.map((m, i) => (i === agentIndex ? fn(m) : m)))
    }

    api.streamAsk(
      patient.patient_id || 'unknown',
      question,
      patient._caseKey || null,
      (evt: AskEvent) => {
        if (evt.type === 'thinking') {
          update((m) => ({ ...m, trace: [...m.trace, { node: evt.node || '', message: evt.message || '', type: 'thinking' }] }))
        } else if (evt.type === 'result') {
          update((m) => ({ ...m, trace: [...m.trace, { node: evt.node || '', message: evt.message || '', type: 'result' }] }))
        } else if (evt.type === 'done') {
          const data = evt.data || {}
          update((m) => ({
            ...m,
            busy: false,
            answer: data.final_response as string,
            citations: data.citations as Citation[],
            isRefusal: Boolean(data.is_refusal),
          }))
        } else if (evt.type === 'patch_eval') {
          const data = evt.data || {}
          update((m) => ({ ...m, evalScores: data.eval_scores as EvalScores }))
        } else if (evt.type === 'error') {
          update((m) => ({ ...m, busy: false, answer: '', trace: [...m.trace, { node: 'error', message: evt.message || 'Something went wrong.', type: 'error' }] }))
        }
      },
      () => setBusy(false),
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Ask about this patient</h2>
          <p className="text-xs text-gray-500">Answers are grounded in patient records and clinical guidelines.</p>
        </div>
        <DetailToggle technical={technical} onChange={setTechnical} label="Show reasoning steps" />
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md space-y-3 text-center">
            <p className="text-sm text-gray-500">Ask anything about this patient's records or care plan.</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-xs text-gray-600 hover:border-indigo-300 hover:bg-indigo-50"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-lg rounded-2xl bg-indigo-600 px-4 py-2 text-sm text-white">{m.text}</div>
            </div>
          ) : (
            <AgentMessage key={i} message={m} technical={technical} />
          ),
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(input)
        }}
        className="flex gap-2 border-t border-gray-200 bg-white p-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this patient…"
          disabled={busy}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 disabled:bg-gray-50"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  )
}

function AgentMessage({ message, technical }: { message: Message; technical: boolean }) {
  if (message.busy) {
    return (
      <div className="max-w-lg rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-500">
        <span className="inline-block animate-pulse">Thinking…</span>
      </div>
    )
  }

  if (message.isRefusal) {
    return (
      <div className="max-w-lg rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600">
        Nothing relevant was found in the patient's records or the clinical guideline library. Try rephrasing, or
        upload documents in the Documents tab.
      </div>
    )
  }

  const faith = message.evalScores?.faithfulness
  const faithPct = faith != null ? Math.round(faith * 100) : null

  return (
    <div className="max-w-lg space-y-2">
      <div className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800">
        {message.answer}
      </div>

      {message.citations && message.citations.length > 0 && (
        <div className="text-xs text-gray-500">
          Sources: {message.citations.map((c) => c.source_doc || c.title).filter(Boolean).join(', ')}
        </div>
      )}

      {faithPct != null && !technical && (
        <div className="text-xs text-gray-400">{faithfulnessPlain(faithPct)}</div>
      )}

      {technical && (
        <div className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3 text-xs">
          <div className="font-semibold uppercase tracking-wide text-indigo-700">Reasoning trace</div>
          {message.trace.map((t, i) => (
            <div key={i} className="font-mono text-gray-600">
              [{ASK_TECHNICAL_LABELS[t.node] || t.node}] {t.message}
            </div>
          ))}
          {faithPct != null && (
            <div className="pt-1 text-gray-500">
              faithfulness {faithPct}% · relevance{' '}
              {message.evalScores?.context_relevance != null ? Math.round(message.evalScores.context_relevance * 100) : '—'}% ·
              completeness{' '}
              {message.evalScores?.answer_completeness != null ? Math.round(message.evalScores.answer_completeness * 100) : '—'}%
            </div>
          )}
        </div>
      )}

      {!technical && message.trace.length > 0 && (
        <div className="text-xs text-gray-400">
          {message.trace.map((t) => ASK_STEP_LABELS[t.node] || t.node).slice(-1)[0]}
        </div>
      )}
    </div>
  )
}
