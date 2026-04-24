/**
 * demo-data.js
 * Embedded demo patient — James Hartwell (SLE, complex case)
 * Loaded directly without a backend API call when ?demo=true
 */

window.DEMO_PATIENT = {
  patient_id: "demo-jh-001",
  patient: { name: "James Hartwell", dob: "1966-03-14", mrn: "JH-001", age: 58 },
  summary: {
    patient_id: "demo-jh-001",
    generated_at: "2023-11-22T14:30:00Z",
    summary_narrative:
      "Mr James Hartwell is a 58-year-old man with a six-year history of Systemic Lupus " +
      "Erythematosus (SLE) complicated by Class III lupus nephritis, recurrent " +
      "pericarditis/serositis, secondary Sjögren's syndrome, autoimmune haemolytic anaemia " +
      "(AIHA), and antiphospholipid syndrome (APS). He was admitted acutely in October 2023 " +
      "with a major flare involving severe renal impairment (creatinine 198 µmol/L, PCR " +
      "487 mg/mmol), pericardial effusion, and falling haemoglobin (9.2 g/dL). He received " +
      "IV methylprednisolone and commenced mycophenolate mofetil. At November 2023 review " +
      "his renal function has improved significantly (creatinine 142, eGFR 49, PCR 88 mg/mmol), " +
      "though ongoing monitoring and gradual steroid tapering is planned.",

    diagnoses: [
      { name: "Systemic Lupus Erythematosus (SLE)",        icd_code: "M32.9",  date_first_noted: "2017",       status: "active" },
      { name: "Lupus Nephritis Class III (focal)",          icd_code: "M32.14", date_first_noted: "2023-10-14", status: "active — partial response" },
      { name: "Lupus Pericarditis / Serositis",             icd_code: "M32.12", date_first_noted: "2023-10-11", status: "resolving" },
      { name: "Secondary Sjögren's Syndrome",               icd_code: "M35.0",  date_first_noted: "2020",       status: "active" },
      { name: "Antiphospholipid Syndrome (APS)",            icd_code: "D68.61", date_first_noted: "2023-10",    status: "active" },
      { name: "Autoimmune Haemolytic Anaemia (AIHA)",       icd_code: "D59.1",  date_first_noted: "2023-10-11", status: "improving" },
      { name: "Steroid-induced hyperglycaemia",             icd_code: "E73.9",  date_first_noted: "2023-11",    status: "suspected" },
      { name: "Dyslipidaemia (steroid-related)",            icd_code: "E78.5",  date_first_noted: "2023-11",    status: "active" },
    ],

    medications: [
      { name: "Prednisolone",                   dose: "60mg (tapering −10mg/2 wks)",        frequency: "Once daily (morning)",       start_date: "2023-10-14" },
      { name: "Mycophenolate mofetil (MMF)",    dose: "1.5g (increased from 1g at clinic)", frequency: "Twice daily (BD) with food", start_date: "2023-10-16" },
      { name: "Hydroxychloroquine",             dose: "200mg (reduced from 400mg)",         frequency: "Twice daily (BD)",           start_date: "2017" },
      { name: "Warfarin",                       dose: "Adjusted to INR 2.5–3.5 (2.8)",      frequency: "Once daily (evening)",       start_date: "2023-10-17" },
      { name: "Omeprazole",                     dose: "20mg",                               frequency: "Once daily",                 start_date: "2023-10-14" },
      { name: "Calcium carbonate + Vit D3",     dose: "1500mg/400IU",                       frequency: "Twice daily",                start_date: "2023-10-14" },
      { name: "Hypromellose 0.3% eye drops",   dose: "1–2 drops per eye",                  frequency: "As needed (~10× daily)",     start_date: "2020" },
    ],

    allergies: ["Penicillin — anaphylaxis (2009)", "Sulfonamides — rash (2015)"],

    lab_results: [
      { test_name: "Creatinine",       value: "142",         unit: "µmol/L",      date: "2023-11-20", flag: "high" },
      { test_name: "eGFR (CKD-EPI)",  value: "49",          unit: "mL/min/1.73m²", date: "2023-11-20", flag: "low"  },
      { test_name: "Urine PCR",       value: "88",          unit: "mg/mmol",     date: "2023-11-20", flag: "high" },
      { test_name: "Haemoglobin",     value: "11.4",        unit: "g/dL",        date: "2023-11-20", flag: "low"  },
      { test_name: "anti-dsDNA",      value: "248",         unit: "IU/mL",       date: "2023-11-20", flag: "high" },
      { test_name: "Complement C3",   value: "0.65",        unit: "g/L",         date: "2023-11-20", flag: "low"  },
      { test_name: "Complement C4",   value: "0.09",        unit: "g/L",         date: "2023-11-20", flag: "low"  },
      { test_name: "INR",             value: "2.8",         unit: "—",           date: "2023-11-20", flag: "normal" },
      { test_name: "Fasting Glucose", value: "6.4",         unit: "mmol/L",      date: "2023-11-20", flag: "high" },
      { test_name: "HbA1c",           value: "43",          unit: "mmol/mol",    date: "2023-11-20", flag: "normal" },
      { test_name: "ANA titre",       value: "1:320 (homog.)", unit: "—",        date: "2023-11-20", flag: "high" },
      { test_name: "ESR",             value: "64",          unit: "mm/hr",       date: "2023-11-20", flag: "high" },
      { test_name: "CRP",             value: "18",          unit: "mg/L",        date: "2023-11-20", flag: "high" },
      { test_name: "Vitamin D 25-OH", value: "38",          unit: "nmol/L",      date: "2023-11-20", flag: "low"  },
    ],

    timeline: [
      { date: "2017",        event: "SLE diagnosis. ANA 1:1280, anti-dsDNA 187 IU/mL. Started HCQ 400mg + prednisolone 5mg.", category: "diagnosis" },
      { date: "2019",        event: "Prednisolone successfully weaned. Disease in clinical remission.", category: "medication" },
      { date: "2020",        event: "Secondary Sjögren's confirmed on salivary gland biopsy. Hypromellose drops started.", category: "diagnosis" },
      { date: "Sep 2023",    event: "3-week history of worsening fatigue, arthralgia, malar rash, dry mouth/eyes. Presented to GP.", category: "visit" },
      { date: "09 Oct 2023", event: "GP visit — dipstick protein +++, blood ++. Referred urgently. Prednisolone → 40mg.", category: "visit" },
      { date: "11 Oct 2023", event: "Hospital admission. Cr 198, eGFR 34. ECG pericarditis. Hb 9.2, DAT+ve. IV methylprednisolone 500mg × 3.", category: "visit" },
      { date: "13 Oct 2023", event: "Echo: pericardial effusion 12mm, EF 63%. CXR: left pleural effusion, cardiomegaly.", category: "procedure" },
      { date: "14 Oct 2023", event: "Renal biopsy — Class III lupus nephritis. APS confirmed (LA+, aCL IgG 68 GPL).", category: "procedure" },
      { date: "16 Oct 2023", event: "MMF 1g BD started. Warfarin commenced for APS.", category: "medication" },
      { date: "19 Oct 2023", event: "Discharged home. Prednisolone 60mg, MMF 1g BD, HCQ 200mg BD, warfarin, omeprazole, Ca+VitD.", category: "visit" },
      { date: "20 Nov 2023", event: "Bloods: Cr 142, eGFR 49, PCR 88, Hb 11.4. Significant improvement across all markers.", category: "lab" },
      { date: "22 Nov 2023", event: "Rheumatology clinic: MMF → 1.5g BD. Steroid taper started. MRI brain + neurology referral. DEXA requested.", category: "visit" },
    ],

    clinical_flags: [
      { text: "Borderline fasting glucose (6.4 mmol/L) + HbA1c 43 — possible steroid-induced diabetes developing. OGTT in 4 weeks.", type: "warn" },
      { text: "New persistent headaches (3 months) — neuropsychiatric lupus or APS cerebrovascular event must be excluded. MRI arranged.", type: "warn" },
      { text: "Dyslipidaemia (LDL 3.6, TG 2.4, HDL 0.9) — likely steroid-related. Statin deferred until disease stable.", type: "warn" },
      { text: "Vitamin D insufficiency (38 nmol/L) — continue supplementation, recheck in 3 months.", type: "info" },
      { text: "Borderline elevated RVSP on echo (34 mmHg) — monitor for pulmonary hypertension given APS/SLE overlap.", type: "warn" },
      { text: "Smoker (5 cig/day) — increases clot risk with APS. Smoking cessation referral placed.", type: "warn" },
      { text: "Hydroxychloroquine >5 years — retinopathy screening booked 15/12/2023.", type: "info" },
      { text: "Warfarin INR 2.8 — within target (2.5–3.5). Monthly INR monitoring.", type: "info" },
    ],

    // ── ClinicalSummary — matches app/models.py ClinicalSummary schema ────
    // Pre-computed demo output (equivalent to what the Summarization Agent
    // would produce from Groq / Gemini for this patient).
    clinical_summary: {
      chief_complaint:
        "Mr James Hartwell, a 58-year-old man with established Systemic Lupus Erythematosus, " +
        "presents following an acute disease flare characterised by severe lupus nephritis, " +
        "pericarditis, autoimmune haemolytic anaemia, and confirmed antiphospholipid syndrome.",

      history_of_present_illness:
        "Mr Hartwell has a 6-year history of SLE, previously well-controlled on hydroxychloroquine " +
        "and low-dose prednisolone. In September 2023 he developed a 3-week prodrome of worsening " +
        "fatigue, diffuse arthralgia, and malar rash. On 9 October 2023 his GP detected dipstick " +
        "proteinuria (+++) and haematuria (++), prompting urgent referral. He was admitted on " +
        "11 October 2023 with creatinine 198 µmol/L (eGFR 34), haemoglobin 9.2 g/dL (DAT positive), " +
        "and electrocardiographic changes consistent with pericarditis. Renal biopsy confirmed " +
        "Class III focal lupus nephritis and antiphospholipid syndrome was established serologically. " +
        "He received 3 pulses of IV methylprednisolone 500mg, commenced mycophenolate mofetil 1g BD " +
        "and warfarin for APS, and was discharged on prednisolone 60mg. At the 22 November 2023 " +
        "clinic review his renal markers have improved significantly (creatinine 142, eGFR 49, PCR 88) " +
        "and haemoglobin has risen to 11.4 g/dL, though disease remains active.",

      clinical_assessment:
        "Partially responding lupus flare with multi-organ involvement. Renal function is improving " +
        "but eGFR remains 49 mL/min/1.73m² indicating moderate CKD in the context of Class III nephritis. " +
        "AIHA is responding to steroids. Pericardial effusion is resolving. APS represents a significant " +
        "thrombotic risk requiring therapeutic anticoagulation. Escalation to MMF 1.5g BD at today's " +
        "clinic visit is appropriate. Steroid taper is planned but will be gradual given renal " +
        "trajectory. Key emerging concerns are borderline steroid-induced hyperglycaemia, " +
        "dyslipidaemia, possible neuropsychiatric lupus (new headaches), and pulmonary " +
        "hypertension risk (borderline RVSP 34 mmHg on echo).",

      current_medications: [
        "Prednisolone — 60mg (tapering −10mg/2 weeks), once daily (morning)",
        "Mycophenolate mofetil — 1.5g, twice daily with food",
        "Hydroxychloroquine — 200mg, twice daily",
        "Warfarin — dose adjusted to INR 2.5–3.5 (current INR 2.8), once daily (evening)",
        "Omeprazole — 20mg, once daily",
        "Calcium carbonate + Vitamin D3 — 1500mg/400IU, twice daily",
        "Hypromellose 0.3% eye drops — 1–2 drops per eye, as needed",
      ],

      patient_facing_summary:
        "You have a condition called lupus (SLE) which has caused inflammation in your kidneys, " +
        "the lining around your heart, and your blood. You were admitted to hospital in October " +
        "where you received strong anti-inflammatory medicines through a drip, and were started " +
        "on new tablets to calm your immune system and protect against blood clots. " +
        "Your kidneys and blood count are improving, which is really good news. " +
        "You will need to stay on your medicines carefully, attend regular blood test appointments, " +
        "and come back for follow-up scans and specialist reviews over the coming months.",

      key_concerns: [
        "Persistent lupus nephritis (eGFR 49) — renal function requires close monitoring",
        "Borderline fasting glucose — possible steroid-induced diabetes developing",
        "New persistent headaches — neuropsychiatric lupus or APS stroke must be excluded (MRI arranged)",
        "Borderline RVSP 34 mmHg — monitor for lupus/APS-related pulmonary hypertension",
        "Dyslipidaemia on high-dose steroids — cardiovascular risk assessment needed",
      ],

      follow_up_actions: [
        "Repeat renal bloods (creatinine, eGFR, urine PCR) in 4 weeks",
        "OGTT for steroid-induced diabetes in 4 weeks",
        "MRI brain + neurology review — urgent (new headaches)",
        "DEXA bone density scan — arrange as outpatient",
        "Hydroxychloroquine retinopathy screening — booked 15/12/2023",
        "Smoking cessation referral — placed today",
        "Monthly INR monitoring (warfarin)",
        "Repeat echo in 3 months (RVSP surveillance)",
      ],

      generated_at: "2023-11-22T14:30:00Z",
      model_used:   "demo/embedded",
      patient_id:   "demo-jh-001",
    },
  },

  source_documents: [
    { name: "james_hartwell_handwritten_note_1.txt", type: "handwritten_note",  label: "GP Handwritten Note — 09 Oct 2023",         icon: "📝", description: "OCR-extracted GP note. Malar rash, joint pain, dipstick protein+++." },
    { name: "james_hartwell_handwritten_note_2.txt", type: "handwritten_note",  label: "Ward Progress Note — 12 Oct 2023",          icon: "📝", description: "Ward SpR note. Inpatient course, IV methylprednisolone, investigations." },
    { name: "james_hartwell_clinical_report.txt",    type: "clinical_letter",   label: "Rheumatology Clinic Letter — 22 Nov 2023",  icon: "📄", description: "Prof Okafor's clinic letter — full history, management plan." },
    { name: "james_hartwell_labs.txt",               type: "lab_report",        label: "Blood Panel + Immunology — 20 Nov 2023",    icon: "🧪", description: "Haematology, biochemistry, immunology, urine — 4 Markdown tables." },
    { name: "james_hartwell_xray_report.txt",        type: "radiology_report",  label: "CXR + Echocardiogram — 13 Oct 2023",        icon: "🫀", description: "Left pleural effusion, pericardial effusion 12mm, EF 63%." },
    { name: "james_hartwell_transcript.txt",         type: "audio_transcript",  label: "Consultation Transcript — 22 Nov 2023",     icon: "🎙️", description: "14m32s Whisper transcript — Prof Okafor & Mr Hartwell." },
  ],

  demo_questions: [
    "What medications is James currently taking and when were they prescribed?",
    "What are James's most recent kidney function results and how have they changed since admission?",
    "What is lupus nephritis Class III and what does it mean for James's prognosis?",
    "Why is James on warfarin and what is his target INR?",
    "What are the clinical flags I should be concerned about at the next review?",
    "Summarise the October 2023 hospital admission in plain English for a patient.",
    "What symptoms does James describe in the consultation recording?",
    "What follow-up appointments does James have scheduled?",
  ],
};
