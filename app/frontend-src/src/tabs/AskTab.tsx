import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { BrandMark, Icon, type IconName } from '../components/Icon'
import { MarkdownAnswer } from '../components/MarkdownAnswer'
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
  followUps?: string[]
  evaluating?: boolean
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
  const cancelRef = useRef<(() => void) | null>(null)
  useEffect(() => () => cancelRef.current?.(), [])

  function ask(question: string) {
    if (!question.trim() || busy) return
    setBusy(true)
    setInput('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: question, trace: [] },
      { role: 'agent', trace: [], busy: true },
    ])

    function update(fn: (m: Message) => Message) {
      setMessages((prev) =>
        prev.map((m, i) => (i === prev.length - 1 ? fn(m) : m)),
      )
    }

    cancelRef.current = api.streamAsk(
      patient.patient_id || 'unknown',
      question,
      patient._caseKey || null,
      (evt: AskEvent) => {
        if (evt.type === 'thinking') {
          update((m) => ({
            ...m,
            trace: [...m.trace, { node: evt.node || '', message: evt.message || '', type: 'thinking' }],
          }))
        } else if (evt.type === 'result') {
          update((m) => ({
            ...m,
            trace: [...m.trace, { node: evt.node || '', message: evt.message || '', type: 'result' }],
          }))
        } else if (evt.type === 'done') {
          const data = evt.data || {}
          update((m) => ({
            ...m,
            busy: false,
            answer: data.final_response as string,
            citations: data.citations as Citation[],
            isRefusal: Boolean(data.is_refusal),
            evalScores: data.eval_scores as EvalScores,
            followUps: data.follow_ups as string[],
            evaluating: !data.is_refusal && evt.node !== 'cache',
          }))
        } else if (evt.type === 'patch_eval') {
          const data = evt.data || {}
          update((m) => ({ ...m, evaluating: false, evalScores: data.eval_scores as EvalScores,
            answer: (data.final_response as string) || m.answer }))
        } else if (evt.type === 'patch_followups') {
          update((m) => ({ ...m, followUps: evt.data?.follow_ups as string[] }))
        } else if (evt.type === 'error') {
          update((m) => ({
            ...m,
            busy: false,
            evaluating: false,
            answer: '',
            trace: [...m.trace, { node: 'error', message: evt.message || 'Something went wrong.', type: 'error' }],
          }))
        }
      },
      () => {
        setBusy(false)
        update((m) => ({ ...m, busy: false, evaluating: false }))
      },
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mx-auto flex w-full max-w-6xl shrink-0 flex-wrap items-center justify-between gap-3 px-4 pt-6 sm:px-6 lg:px-8">
        <div>
          <h2 className="page-title">Ask</h2>
        </div>
        <DetailToggle technical={technical} onChange={setTechnical} label="Details" />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="page-content space-y-6" aria-live="polite" aria-relevant="additions text">
        {messages.length === 0 && (
          <div className="ask-empty">
            <BrandMark />
            <h3 className="ask-empty-title">Ask the patient record</h3>
            <p className="mt-3 text-base text-muted">What would you like to know about this patient?</p>
            <div className="ask-suggestions">
              {SUGGESTIONS.map((q, index) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="ask-suggestion"
                >
                  <Icon name={(['diagnosis', 'lab', 'document', 'medication'] as IconName[])[index]} /><span>{q}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <div className="w-full max-w-[60ch] rounded-xl bg-accent px-5 py-4 text-base text-white">{m.text}</div>
            </div>
          ) : (
            <AgentMessage key={i} message={m} technical={technical} onAsk={ask} disabled={busy} />
          ),
        )}
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(input)
        }}
        className="mx-auto w-full max-w-6xl shrink-0 px-4 pb-5 pt-3 sm:px-6 lg:px-8"
      >
        <div className="ask-composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this patient…"
          aria-label="Your question"
          disabled={busy}
          className="min-w-0 flex-1 rounded-lg border border-rule px-4 py-3 text-base focus:border-accent focus:outline-none disabled:bg-paper"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="primary-button"
        >
          Send <Icon name="send" />
        </button>
        </div>
      </form>
    </div>
  )
}

function AgentMessage({ message, technical, onAsk, disabled }: { message: Message; technical: boolean; onAsk: (q: string) => void; disabled: boolean }) {
  if (message.busy) {
    const lastTrace = message.trace[message.trace.length - 1]
    return (
      <div className="w-full max-w-[72ch] space-y-2">
        <div className="flex items-center gap-2 border border-rule bg-sheet px-4 py-3 text-base text-muted">
          <span className="inline-block h-2 w-2 animate-ping rounded-full bg-accent" />
          <span className="text-sm text-muted">
            {lastTrace ? (ASK_STEP_LABELS[lastTrace.node] || lastTrace.message) : 'Analyzing records…'}
          </span>
        </div>
        {technical && message.trace.length > 0 && (
          <div className="space-y-1 break-words border-l-2 border-accent bg-sheet p-3 text-sm font-mono text-muted">
            {message.trace.map((t, i) => (
              <div key={i}>
                [{ASK_TECHNICAL_LABELS[t.node] || t.node}] {t.message}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (!message.answer && message.trace.some((t) => t.type === 'error')) {
    const err = message.trace.find((t) => t.type === 'error')
    return (
      <div className="w-full max-w-[72ch] border border-red-300 bg-red-50 px-4 py-3 text-base text-red-700">
        ⚠️ {err?.message || 'Unable to complete request. Please verify server connection.'}
      </div>
    )
  }

  if (message.isRefusal) {
    return (
      <div className="w-full max-w-[72ch] border border-rule bg-sheet px-4 py-3 text-base text-muted">
        Nothing relevant was found in the patient's records or the clinical guideline library. Try a more specific question or select another case.
      </div>
    )
  }

  const faith = message.evalScores?.skipped ? undefined : message.evalScores?.faithfulness
  const faithPct = faith != null ? Math.round(faith * 100) : null

  const assessment = message.evaluating ? 'Checking sources…' : message.evalScores?.skipped || faithPct == null ?
    'Evaluation unavailable' : message.evalScores?.hallucination_detected || faithPct < 70 ?
    'Source review flagged concerns' : 'Source review complete'
  const caution = !message.evaluating && (message.evalScores?.skipped || faithPct == null || message.evalScores?.hallucination_detected || faithPct < 70)

  return (
    <div className="w-full max-w-[72ch] space-y-3">
      <p role="status" className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${caution ? 'bg-caution-subtle text-caution' : 'bg-accent-subtle text-accent'}`}>
        <span aria-hidden>{message.evaluating ? '◌' : caution ? '!' : '✓'}</span> {assessment}
      </p>
      <div className="panel text-base text-ink">
        <MarkdownAnswer>{message.answer || ''}</MarkdownAnswer>
      </div>

      {message.citations && message.citations.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm text-muted">
          {message.citations.map((c, i) => (
            <span key={i} className="max-w-full break-words rounded-md border border-rule bg-sheet px-3 py-1.5">
              [{c.ref}] {c.url && /^https?:\/\//i.test(c.url) ? <a className="text-accent underline underline-offset-2" href={c.url} target="_blank" rel="noopener noreferrer">{c.title || c.source_doc}</a> : (c.source_doc || c.title)}
            </span>
          ))}
        </div>
      )}

      {faithPct != null && !technical && <div className="text-sm text-muted">{faithfulnessPlain(faithPct)}</div>}

      {technical && (
        <div className="space-y-2 break-words border-l-2 border-accent bg-sheet p-3 text-sm">
          <div className="font-mono text-accent">Reasoning trace</div>
          {message.trace.map((t, i) => (
            <div key={i} className="font-mono text-muted">
              [{ASK_TECHNICAL_LABELS[t.node] || t.node}] {t.message}
            </div>
          ))}
          {faithPct != null && (
            <div className="flex flex-wrap gap-3 pt-1 text-sm text-muted">
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

      {message.followUps && message.followUps.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.followUps.map((q) => (
            <button key={q} disabled={disabled} onClick={() => onAsk(q)} className="secondary-button text-left">{q}</button>
          ))}
        </div>
      )}


    </div>
  )
}
