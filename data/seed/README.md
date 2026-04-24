# Seed Data — James Hartwell (Synthetic Patient)

## Patient Profile
- **Name:** James Hartwell
- **DOB:** 1966-03-14
- **MRN:** JH-001
- **Age at time of notes:** 58
- **Primary diagnosis:** Systemic Lupus Erythematosus (SLE) — complex multi-organ involvement

## Disease Summary
SLE is an autoimmune disease where the immune system attacks the body's own tissues.
James's case involves:
- **Lupus nephritis Class III** (focal proliferative, 30-50% glomeruli involved)
- **Recurrent serositis** (pericarditis, mild pleural effusion)
- **Secondary Sjögren's syndrome** (sicca symptoms: dry eyes, dry mouth)
- **Antiphospholipid Antibody Syndrome** (APS) — elevated aPL antibodies, DVT history
- **Autoimmune hemolytic anemia (AIHA)**

## Why This Case Is Good for RAG Testing
- Multiple document types (typed notes, handwritten scrawl, labs with tables, imaging report, audio transcript)
- Complex polypharmacy (7 medications with interactions)
- Lab values with flag patterns and trends
- Differentials that require cross-document reasoning
- Temporal reasoning (disease flares vs. remission periods)

## Synthetic Files in This Directory

| Filename | Type | Simulates |
|---|---|---|
| `james_hartwell_handwritten_note_1.txt` | Messy OCR output | GP handwritten visit note (OCR artifacts) |
| `james_hartwell_handwritten_note_2.txt` | Messy OCR output | Hospital ward handwritten progress note |
| `james_hartwell_clinical_report.txt` | Clean Docling text extract | Rheumatology typed clinic letter |
| `james_hartwell_labs.txt` | Docling table extraction | Full blood panel + immunology + urine |
| `james_hartwell_xray_report.txt` | Docling text extract | Chest X-ray + Echo report |
| `james_hartwell_transcript.txt` | Whisper transcript | Doctor–patient consultation audio |
| `dummy_patient.json` | Pre-processed JSON | Full PatientSummary for frontend demo mode |

## Note on File Format
These `.txt` files simulate what **Docling** and **LightOnOCR-2-1B** return
after processing raw PDFs/JPGs/M4A files. They intentionally contain:
- OCR artifacts (misread characters, broken words)
- Inconsistent whitespace and line breaks
- Mixed abbreviations and full terms
- Partially recognised table structures

This stress-tests the chunker and RAG pipeline.
