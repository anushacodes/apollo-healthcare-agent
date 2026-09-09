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
  summary_narrative?: string
  diagnoses?: Diagnosis[]
  medications?: Medication[]
  lab_results?: LabResult[]
  clinical_flags?: (ClinicalFlag | string)[]
  allergies?: string[]
  timeline?: TimelineEvent[]
  clinical_summary?: ClinicalSummary | null
}

export interface SourceDocument {
  icon?: string
  label: string
  description?: string
}

export interface PatientData {
  patient_id: string
  patient?: PatientInfo
  summary: PatientSummary
  source_documents?: SourceDocument[]
  case_label?: string
  _caseKey?: string
}

export interface AgentEvent {
  node: string
  audit_entry?: string
  error?: string
  interactions?: Record<string, unknown>
  diagnoses?: Record<string, unknown>
  calculator_results?: Array<Record<string, unknown>>
  final_summary?: ClinicalSummary
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
