# Completion audit

Scope: a reproducible local portfolio demo with three synthetic cases, diagnostics, patient/corpus RAG, streaming updates, and offline automated checks. This file separates that baseline from future product work; it does not claim production or clinical readiness.

## Completed

- [x] Resolve Ruff's unused import and import-order failures.
- [x] Regenerate Python/npm lockfiles locally and ignore them as requested; pin the development Python version.
- [x] Add CI jobs for offline Python tests and frontend lint/typecheck/build, alongside lint.
- [x] Replace the live-network RAG smoke test with service-mocked conditional graph tests.
- [x] Isolate test SQLite databases and forbid outbound socket connections and model downloads.
- [x] Support API startup without generated frontend assets; provide a setup response and health endpoint.
- [x] Build the React frontend in Docker and stop Compose from hiding it with a source mount.
- [x] Move Docling/local embedding models into the optional `inference` extra and lazily load extractors.
- [x] Index SQLite chunks even when dense retrieval is unavailable.
- [x] Keep dense point IDs scoped to patient/document chunk identity.
- [x] Replace older chunks when re-uploading a filename; invalidate that patient's answer cache.
- [x] List sources from SQLite so sparse-only uploads remain visible.
- [x] Reject unsupported, empty, unindexable, and oversized uploads with distinct status codes.
- [x] Close RAG WebSockets after final patches and validate malformed request payloads.
- [x] Apply evaluation answer patches and display follow-ups/cached evaluation in the React UI.
- [x] Cancel Ask sockets on unmount; reset tab state on patient changes.
- [x] Match the Documents UI to the backend's source-document dictionary.
- [x] Mark failed evaluation as unavailable; avoid caching unverified/low-faithfulness answers and generation errors.
- [x] Accumulate diagnostics audit logs and include calculator/agent results in downstream reasoning.
- [x] Honor summary force-regeneration and run synchronous summary work outside the API event loop.
- [x] Update vulnerable frontend dependencies within compatible ranges.
- [x] Replace outdated architecture, frontend, test, and setup documentation.
- [x] Share evidence excerpts between generation and evaluation and evaluate the entire answer.
- [x] Require valid source numbers, retry citation failures once, and invalidate earlier answer caches.
- [x] Distinguish missing/invalid keys, quota, credit, model, timeout, connection, and provider failures in Ask.

## Human-review implementation

- [x] Save Analysis drafts and reload earlier runs per patient.
- [x] Link exact source passages and distinguish documented, suspected, historical, negated, conflicting, calculated, reviewer-supplied, and AI-suggested information.
- [x] Add accept/edit/reject and clarification forms with required reasons and server-attached reviewer-session identity.
- [x] Enforce version checks, finalization prerequisites, immutable finalized reviews, and filtered final output in the backend.
- [x] Add calculator input clarification/skip, downstream draft regeneration, and persistent decision history.
- [x] Add per-run transactional hash-chained audit events and integrity verification.
- [x] Add a 10-case labeled offline policy benchmark and regression coverage.
- [x] Extract, review, and persist typed document fields with source/reviewer provenance and regression fixtures.
- [x] Add selectable-text PDF ingestion and three connected PDF/text examples.

## Remaining feature scope

These are separate product decisions, not implemented capabilities:

- [ ] Patient creation/listing and uploaded-record management in the UI. Uploads and reviewed fields work, but the selector and summary endpoint still use three bundled cases. Approved fields do not automatically merge into current medication/diagnosis lists.
- [ ] Authentication and per-patient authorization before using shared deployments or real records.
- [ ] Retention/deletion and cache invalidation across both stores, including deleted/revised corpus assets.
- [ ] Application tracing. Optional Langfuse containers/settings exist; no app instrumentation is connected.
- [ ] Expand the small review-policy fixture into a representative retrieval/evaluation benchmark. The current sufficiency decision counts chunks; model self-evaluation is an annotation, not a clinical safety gate.
- [ ] Browser automation covering case selection, document rendering, streamed warning updates, and follow-up clicks. Current frontend gates are lint/typecheck/build.
- [ ] Review calculator input assumptions, demographics, and guideline currency with appropriate domain expertise before making clinical accuracy claims.
- [ ] Broad exception handling/logging review; avoid treating fallback output as equivalent to a successful provider response.
- [ ] Deployment target, secrets management, resource limits, backup policy, and a release/CD workflow.

## Environment-dependent release checks

- [ ] Run the full Docker image build and Compose startup with a running Docker daemon. Configuration can be checked without a daemon, but image/runtime success has not been established here.
- [x] Verify Groq generation, evaluation, and follow-ups with configured credentials and a synthetic lab question.
- [ ] Verify OpenRouter and live rate-limit/provider failure behavior. Offline tests cover failure classification, fallback, and error delivery without external calls.
- [ ] Verify model downloads, Docling PDF/Word extraction, image OCR, and Qdrant dense retrieval using `--extra inference` on the target machine.
- [ ] Verify web search integrations against real services and review what query data can leave the machine.
- [x] Exercise the built UI and streaming flows in an isolated Chrome session; verify human review separately as features change.

Use `README.md` for exact setup and check commands. Keep open items explicit until there is evidence that each works.
