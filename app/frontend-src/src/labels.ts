// Single source of truth for translating internal pipeline/schema vocabulary
// into plain language shown to end users by default. Technical views may show
// the raw internal name alongside the friendly one; the simple view never
// shows the raw name at all.

export const DIAGNOSTIC_STEP_LABELS: Record<string, string> = {
  orchestrator: 'Reviewing the case',
  drug_graph: 'Checking medications for interactions',
  diagnosis: 'Considering possible diagnoses',
  tool_node: 'Running clinical calculators',
  summarizer: 'Writing the summary',
  __start__: 'Starting',
  __done__: 'Done',
  __error__: 'Something went wrong',
}

export const DIAGNOSTIC_STEP_ORDER = ['orchestrator', 'drug_graph', 'diagnosis', 'tool_node', 'summarizer']

// Technical view keeps the original internal terms for people who want them.
export const DIAGNOSTIC_TECHNICAL_LABELS: Record<string, string> = {
  orchestrator: 'Orchestrator',
  drug_graph: 'Drug / KG Agent',
  diagnosis: 'Diagnosis Agent',
  tool_node: 'Calculators',
  summarizer: 'Summarizer',
  __start__: 'Pipeline Start',
  __done__: 'Complete',
  __error__: 'Error',
}

export const ASK_STEP_LABELS: Record<string, string> = {
  query_router: 'Understanding your question',
  patient_retriever: 'Looking through patient records',
  research_fetcher: 'Checking medical guidelines',
  web_search: 'Searching the web',
  context_assembler: "Gathering what's relevant",
  sufficiency_judge: 'Checking there’s enough information',
  generator: 'Writing the answer',
  eval_agent: 'Double-checking the answer',
  follow_up_agent: 'Thinking of follow-up questions',
  cache: 'Using a saved answer',
  error: 'Something went wrong',
}

export const ASK_TECHNICAL_LABELS: Record<string, string> = {
  query_router: 'Query Router',
  patient_retriever: 'Patient Docs',
  research_fetcher: 'Corpus Search',
  web_search: 'Web Search',
  context_assembler: 'Assembler',
  sufficiency_judge: 'Coverage Check',
  generator: 'Generator',
  eval_agent: 'Eval Agent',
  follow_up_agent: 'Follow-Up Agent',
  cache: 'Cache',
  error: 'Error',
}

const COMMON_ICD_HINTS: Record<string, string> = {
  M32: 'Lupus (an autoimmune disease)',
  N04: 'Kidney condition (nephrotic syndrome)',
  I50: 'Heart failure',
  J44: 'COPD (a lung disease)',
  E11: 'Type 2 diabetes',
  I10: 'High blood pressure',
  I26: 'Blood clot in the lung',
  I82: 'Blood clot in a vein',
  D68: 'Blood clotting disorder',
  I25: 'Coronary artery disease',
}

export function explainIcdCode(code?: string): string | null {
  if (!code) return null
  const prefix = code.split('.')[0]
  return COMMON_ICD_HINTS[prefix] ?? null
}

export function explainLabFlag(flag?: string): string {
  if (flag === 'critical_high') return 'critically higher than the normal range'
  if (flag === 'critical_low') return 'critically lower than the normal range'
  if (flag === 'high') return 'higher than the normal range'
  if (flag === 'low') return 'lower than the normal range'
  return 'within the normal range'
}

export function isCriticalLabFlag(flag?: string): boolean {
  return flag === 'critical_high' || flag === 'critical_low'
}

export function explainCalculatorKey(key: string): string {
  return key.replace(/_/g, ' ')
}

export function faithfulnessPlain(pct: number): string {
  if (pct >= 90) return 'This answer closely matches its sources.'
  if (pct >= 70) return 'This answer mostly matches its sources, with minor gaps.'
  return 'This answer may not be fully backed by its sources — double check it.'
}

export function sanitizeAuditText(text: string): string {
  // Strip raw Python exception noise (e.g. "Traceback...", "<class '...'>") so
  // nothing internal leaks into any UI mode; the full error still goes to
  // server logs from the backend.
  return text
    .replace(/Traceback \(most recent call last\)[\s\S]*/g, '')
    .replace(/<class '[^']+'>:?/g, '')
    .trim()
}
