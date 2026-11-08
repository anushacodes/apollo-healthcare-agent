# Structured document extraction

Apollo uses its existing document parser followed by `app/ingestion/structured.py`. The new English extractor is implemented locally; no external patient examples or extraction code were copied.

## Workflow

Documents supports extraction from a bundled source, pasted text, or an uploaded document. Text extraction needs no provider key. Existing scanned PDF/Word/image parser dependencies remain optional. Each proposed field carries its original data, exact Unicode-codepoint source offsets, source text, field schema, and recorded assertion/status. It starts pending.

The existing review session, version checks, reasons, clarification flow, and per-run audit chain apply. Structured corrections are validated against allowed properties, required fields, choices, calendar dates, and length limits. Free-text edits cannot replace typed extraction data.

Finalization atomically stores accepted/corrected fields in `reviewed_document_fields` and finalizes the review/audit event. Rejected fields remain in review history. Partial decisions cannot enter the patient record. A stable patient/document-content/approved-field fingerprint prevents duplicate imports. Record entries carry original quotes plus correction details and reviewer provenance.

Approved fields appear separately in Overview and in diagnostic/summarization/Ask context, retaining dates and statuses. They do not replace current medication or diagnosis lists. Unapproved client-supplied reviewed-field overlays are discarded before loading persisted fields. Retrieval continues to index raw uploads independently of structured approval.

## Supported input

- Explicit Patient/Name, DOB/Date of Birth, MRN, Report Date/Date labels.
- Diagnosis labels and diagnosis/past-history bullet lists.
- Medication labels or medication-list bullets containing a name and numeric dose/unit; recorded, held, stopped, and historical status.
- Markdown laboratory tables with Test/Result/Units/Reference/Flag columns. Flags must be explicitly recorded; blank/unknown/tick flags remain not recorded.
- Allergy labels/bullets, including explicit negative allergy statements.
- Follow-up/Plan labels and bullet lists.

English month names and ISO dates are supported. Numeric slash dates are normalized only when an element greater than twelve disambiguates day/month order. Numeric timestamps and narrative statements are not used to guess dates. Sample collection dates take precedence over report dates for laboratory results. No generic clinical NLP or general extraction accuracy claim is made.

Limits: 100,000 characters per extraction, 2,000 characters per field value, 200-character document name. Longer uploaded documents still index for search and return an extraction warning. Short documents with recognizable fields can produce a review without being indexed. Unsupported prose produces an empty draft, which cannot finalize. Patient-name mismatches and conflicting same-document values block unchanged acceptance.

## API

- `POST /api/review/patients/{patient_id}/extract`: `{ "source_name": "Clinic letter", "text": "Diagnosis: Hypertension" }`.
- `GET /api/review/patients/{patient_id}/runs?kind=extraction`: saved extraction reviews. Default `kind=analysis` keeps analysis history separate.
- `GET /api/review/patients/{patient_id}/fields`: finalized approved fields and provenance.
- Existing source, decision, clarification, finalize, final-output, and audit endpoints apply.
- Extraction corrections use `edited_data` with the finding's property names. The backend retains immutable original `extracted` data and stores the correction under `decision.edited_data`.
- `POST /api/rag/ingest/{patient_id}` additionally returns `review_run` or `extraction_warning` with its existing indexing counts.

## Validation

`data/evaluation/extraction_cases.json` has ten hand-authored synthetic documents and expected fields. Run `uv run --frozen python -m app.ingestion.evaluate_extraction` for exact-field precision/recall and verbatim-span checks. Labels were authored independently of the extractor. Tests also pin known values, units, flags, and dates in the existing synthetic Case A report, and prove that deliberately changed labels fail evaluation.

API tests exercise session enforcement, structured validation, stale versions, partial/final gating, rejected-field exclusion, persistence, provenance, duplicate imports, patient scoping, name mismatches, and context integration. Relevant reviewed fields receive separate RAG chunks so that per-chunk prompt truncation cannot hide them behind a long patient summary. An injected audit-write failure is tested to ensure finalization and committed fields roll back together. This is a regression suite, not a clinical validation study.
