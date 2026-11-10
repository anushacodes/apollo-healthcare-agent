export interface CaseListItem {
  key: string
  label: string
}

export interface PatientInfo {
  name?: string
  dob?: string
  mrn?: string
  age?: number | string
}

export interface Diagnosis {
  name: string
  icd_code?: string
  status?: string
  date_first_noted?: string
}

export interface Medication {
  name: string
  dose?: string
  frequency?: string
  start_date?: string
}

export interface LabResult {
  test_name: string
  value: string | number
  unit?: string
  flag?: 'high' | 'low' | 'normal' | string
}

export interface ClinicalFlag {
  text?: string
  type?: 'warn' | 'info' | string
}

export interface TimelineEvent {
  date: string
  event: string
  category?: string
}

export interface ClinicalSummary {
  chief_complaint: string
  history_of_present_illness: string
  clinical_assessment: string
  current_medications: string[]
  patient_facing_summary?: string | null
  key_concerns: string[]
  follow_up_actions: string[]
  model_used?: string
}

export interface PatientSummary {
  reviewed_fields?: ReviewedDocumentField[]
  summary_narrative?: string
  diagnoses?: Diagnosis[]
  medications?: Medication[]
  lab_results?: LabResult[]
  clinical_flags?: (ClinicalFlag | string)[]
  allergies?: string[]
  timeline?: TimelineEvent[]
  clinical_summary?: ClinicalSummary | null
}

export interface PatientData {
  patient_id: string
  patient?: PatientInfo
  summary: PatientSummary
  source_documents?: Record<string, string>
  case_label?: string
  _caseKey?: string
}

export interface AgentEvent {
  diagnostic_mode?: 'standard' | 'extended'
  review_run?: ReviewRun
  node: string
  audit_entry?: string
  error?: string
  interactions?: Record<string, unknown>
  diagnoses?: Record<string, unknown>
  calculator_results?: Array<Record<string, unknown>>
  final_summary?: ClinicalSummary
}

export interface DiagnosticReview {
  mode: 'extended'
  status: 'complete' | 'unavailable'
  cached?: boolean
  failure_code?: string
  failed_stage?: string
  disagreements: string[]
  concerns?: string[]
  missing_information: string[]
  stages: {
    stage: string
    model: string
    output: {
      primary_diagnosis?: string
      differential_notes?: string
      concerns?: string[]
      disagreements?: string[]
      missing_information?: string[]
    }
  }[]
}

export interface AskEvent {
  type: 'thinking' | 'result' | 'done' | 'patch_eval' | 'patch_followups' | 'error'
  node?: string
  message?: string
  data?: Record<string, unknown>
}

export interface Citation {
  ref: number
  source_doc?: string
  title?: string
  url?: string
  journal?: string
  year?: string | number
  snippet?: string
}

export interface EvalScores {
  faithfulness?: number
  context_relevance?: number
  answer_completeness?: number
  hallucination_detected?: boolean
  skipped?: boolean
}

export interface ReviewEvidence {
  source_id: string
  start: number
  end: number
  quote: string
  assertion: string
}
export interface Reviewer { id: string; name: string }
export interface ExtractedField { kind: string; data: Record<string, string> }
export interface ReviewedDocumentField extends ExtractedField {
  id: string
  source_name: string
  quote: string
  run_id: string
  recorded_at: string
  reviewer: Reviewer
}
export type ReviewAction = 'accepted' | 'edited' | 'rejected' | 'clarification_requested'
export interface ReviewFinding {
  id: string
  kind: string
  title: string
  original_text: string
  assertion: string
  extracted?: ExtractedField
  field_schema?: { name: string; label: string; required: boolean; choices: string[] }[]
  evidence: ReviewEvidence[]
  status: 'pending' | ReviewAction
  decision: { action: ReviewAction; reason: string; edited_text: string | null; edited_data?: ExtractedField; reviewer: Reviewer; at: string } | null
}
export interface ReviewClarification {
  id: string
  kind: 'calculator' | 'finding'
  tool?: string
  question: string
  status: 'pending' | 'answered' | 'skipped'
  fields?: { name: string; label: string; type: 'boolean' | 'number' | 'choice'; choices: string[] }[]
  reason?: string
  response?: string
}
export interface ReviewRun {
  kind?: 'analysis' | 'extraction'
  committed_fields?: number
  analysis?: {
    source_name?: string; warnings?: string[]; scope?: string
    diagnostic_mode?: 'standard' | 'extended'
    diagnoses?: { _diagnostic_review?: DiagnosticReview }
  }
  id: string
  patient_id: string
  created_at: string
  version: number
  status: 'draft' | 'needs_clarification' | 'finalized'
  findings: ReviewFinding[]
  clarifications: ReviewClarification[]
  sources: Record<string, { label: string; text: string; kind: string }>
}
