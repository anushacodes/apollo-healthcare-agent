import type { AgentEvent, AskEvent, CaseListItem, PatientData } from './types'

async function getCases(): Promise<CaseListItem[]> {
  const r = await fetch('/api/agent/cases')
  if (!r.ok) throw new Error(`getCases: ${r.status}`)
  return (await r.json()).cases
}

async function getCaseData(caseKey: string): Promise<PatientData> {
  const r = await fetch(`/api/agent/cases/${caseKey}`)
  if (!r.ok) throw new Error(`getCaseData: ${r.status}`)
  return r.json()
}

async function getKgStatus(): Promise<{ local_conditions: number }> {
  const r = await fetch('/api/kg/status')
  if (!r.ok) throw new Error(`getKgStatus: ${r.status}`)
  return r.json()
}

function runAgentWs(
  patientId: string,
  payload: unknown,
  onEvent: (event: AgentEvent) => void,
): Promise<AgentEvent | null> {
  return new Promise((resolve, reject) => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/agent/run/${patientId}`)

    ws.onopen = () => ws.send(JSON.stringify(payload))
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as AgentEvent
        onEvent(event)
        if (event.node === '__done__' || event.node === '__error__') {
          ws.close()
          resolve(event)
        }
      } catch (err) {
        console.error('[ws] parse error', err)
      }
    }
    ws.onerror = (e) => reject(e)
    ws.onclose = () => resolve(null)
  })
}

function streamAsk(
  patientId: string,
  question: string,
  caseKey: string | null,
  onEvent: (event: AskEvent) => void,
  onClose: () => void,
): () => void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/rag/stream/${patientId}`)
  ws.onopen = () => ws.send(JSON.stringify({ question, case_key: caseKey }))
  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as AskEvent)
    } catch {
      /* ignore malformed frame */
    }
  }
  ws.onerror = () => onEvent({ type: 'error', message: 'Connection error — is the server running?' })
  ws.onclose = () => onClose()
  return () => ws.close()
}

async function ingestDocument(patientId: string, file: File): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`/api/rag/ingest/${patientId}`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(`ingestDocument: ${r.status}`)
}

export const api = { getCases, getCaseData, getKgStatus, runAgentWs, streamAsk, ingestDocument }
