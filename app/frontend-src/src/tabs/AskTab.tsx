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
      <div className="flex items-center justify-between border-b border-rule bg-sheet px-6 py-3">
        <div>
          <h2 className="font-serif text-base text-ink">Ask about this patient</h2>
          <p className="text-xs text-ink/50">Answers are grounded in patient records and clinical guidelines.</p>
        </div>
        <DetailToggle technical={technical} onChange={setTechnical} label="Show reasoning steps" />
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md space-y-3 text-center">
            <p className="text-sm text-ink/50">Ask anything about this patient's records or care plan.</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="border border-rule bg-sheet px-3 py-2 text-left text-xs text-ink/70 hover:border-accent hover:text-accent"
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
              <div className="max-w-lg bg-accent px-4 py-2 text-sm text-white">{m.text}</div>
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
        className="flex gap-2 border-t border-rule bg-sheet p-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this patient…"
          disabled={busy}
          className="flex-1 border border-rule px-3 py-2 text-sm focus:border-accent focus:outline-none disabled:bg-paper"
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
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
      <div className="max-w-lg border border-rule px-4 py-2 text-sm text-ink/50">
        <span className="inline-block animate-pulse">Thinking…</span>
      </div>
    )
  }

  if (message.isRefusal) {
    return (
      <div className="max-w-lg border border-rule bg-sheet px-4 py-3 text-sm text-ink/70">
        Nothing relevant was found in the patient's records or the clinical guideline library. Try rephrasing, or
        upload documents in the Documents tab.
      </div>
    )
  }

  const faith = message.evalScores?.faithfulness
  const faithPct = faith != null ? Math.round(faith * 100) : null

  return (
    <div className="max-w-lg space-y-2">
      <div className="border border-rule bg-sheet px-4 py-3 text-sm text-ink/90">{message.answer}</div>

      {message.citations && message.citations.length > 0 && (
        <div className="flex flex-wrap divide-x divide-rule text-xs text-ink/50">
          {message.citations.map((c, i) => (
            <span key={i} className="px-2 first:pl-0">
              {c.source_doc || c.title}
            </span>
          ))}
        </div>
      )}

      {faithPct != null && !technical && <div className="text-xs text-ink/40">{faithfulnessPlain(faithPct)}</div>}

      {technical && (
        <div className="space-y-2 border-l-2 border-accent bg-sheet p-3 text-xs">
          <div className="font-mono text-accent">Reasoning trace</div>
          {message.trace.map((t, i) => (
            <div key={i} className="font-mono text-ink/60">
              [{ASK_TECHNICAL_LABELS[t.node] || t.node}] {t.message}
            </div>
          ))}
          {faithPct != null && (
            <div className="flex divide-x divide-rule pt-1 font-mono text-ink/50">
              <span className="pr-2">faithfulness {faithPct}%</span>
              <span className="px-2">
                relevance {message.evalScores?.context_relevance != null ? Math.round(message.evalScores.context_relevance * 100) : '—'}%
              </span>
              <span className="pl-2">
                completeness {message.evalScores?.answer_completeness != null ? Math.round(message.evalScores.answer_completeness * 100) : '—'}%
              </span>
            </div>
          )}
        </div>
      )}

      {!technical && message.trace.length > 0 && (
        <div className="text-xs text-ink/40">{message.trace.map((t) => ASK_STEP_LABELS[t.node] || t.node).slice(-1)[0]}</div>
      )}
    </div>
  )
}
