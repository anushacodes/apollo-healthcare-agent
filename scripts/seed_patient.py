# TODO: Step 12 — Seed script for James Hartwell demo patient
# 1. POST /api/patients  → creates James Hartwell (DOB 1966-03-14, MRN JH-001)
# 2. POST /api/patients/{id}/documents for each file in data/seed/
#    - james_hartwell_note_1.pdf
#    - james_hartwell_note_2.pdf
#    - james_hartwell_handwritten.jpg  (triggers LightOnOCR fallback)
#    - james_hartwell_labs.pdf         (table detection)
#    - james_hartwell_transcript.m4a   (Whisper transcription)
#    - james_hartwell_xray_report.pdf
# 3. Poll /api/documents/{id}/status for each until status=done
# 4. GET /api/patients/{id} → print generated PatientSummary
# 5. POST /api/patients/{id}/ask with "What medications is James currently taking
#    and when were they prescribed?" → print streaming answer
