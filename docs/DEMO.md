# Connected document demo

Open Apollo at http://localhost:8000 and choose **Robert Chen**. Actual, selectable-text PDFs live in `data/demo_documents/robert_chen/`. Every page identifies its contents as synthetic training records. The fictional record dates are June 2024 and match Robert's age and existing patient identity; they are not current clinical observations.

Matching text exports are available alongside the three PDFs. Use one PDF for a short demonstration, or all three to connect the workflow.

## Suggested sequence

1. Show Robert's existing Overview. Open Documents > Add document and upload `01_clinic_follow_up.pdf`.
2. Open linked evidence to highlight the exact text in the parsed PDF. There are eight proposals: report date, name, DOB, MRN, three diagnosis statements and a follow-up action. Pneumonia remains **negated**, not a confirmed diagnosis.
3. Enter a reviewer name. Accept each field with a reason. Show that finalization stays disabled while decisions are pending. Finalize and save, then show Overview > Reviewed document fields.
4. Upload `02_medication_review.pdf`. There are nine proposals. Correct Ramipril frequency from `daily` to `once daily`, giving a reason. Keep metformin's **held** status. Inspect the aspirin/bronchospasm source passage. Review and finalize every field.
5. Upload `03_laboratory_report.pdf`. There are eight proposals, including four laboratory results. Show creatinine **138 µmol/L** with its printed **H** flag. Its sample date is **2024-06-12**, while its report date is **2024-06-13**. Review and finalize.
6. Overview now contains 25 approved fields with individual source/reviewer provenance. Current medications and diagnoses remain intact. Reload to show persistence, then open a saved document review and its audit history.
7. Run Analysis. Approved document fields enter the clinical context and are included in the new analysis's evidence sources. Missing calculator inputs remain explicit. Provider-generated reasoning requires a configured generation key; calculator and heuristic fallback paths remain available without one.
8. With a tested Groq or OpenRouter key, use Ask for `Which medication is held?`, `What reaction to aspirin is recorded?`, and `What creatinine value and sample date are recorded?`. Show citations and explain that answer evaluation is separate from human review.

The sample records intentionally use explicit clinical labels and a clean laboratory table. They demonstrate the implemented extractor's supported formats rather than unrestricted clinical NLP or image OCR. Reference intervals are fictional training metadata. Never present this packet as real patient data or as a clinical validation study.

## Using the packet

The default install now includes pypdf for embedded-text PDFs. Scanned PDFs, Word and images still need the optional document model stack. The new text path does not load Torch or download OCR weights. Invalid/encrypted PDFs return actionable upload errors.

The finished PDFs and matching text exports are ready to use directly. Their PDF/text extraction outputs and complete review flow are covered in `tests/test_demo_documents.py`.

Demo verification uses an isolated temporary SQLite database, so automated accepted fields do not enter the normal local patient record. A real demo session persists its own reviews; repeated imports with the same document hash and approved values do not duplicate fields.
