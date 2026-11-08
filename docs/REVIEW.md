# Evidence-linked human review

[Back to Apollo](../README.md) · [API reference](API.md) · [Evaluation](EVALUATION.md)

## Try it

1. Open a patient and choose **Analysis → Run analysis**.
2. Enter your reviewer name and choose **Start review**. This is a self-declared local session, not a verified account.
3. Complete any **Missing calculator inputs**, or explicitly skip the calculator and give a reason. No absent boolean criterion is automatically treated as false at the calculator boundary.
4. Use a finding's **View source** controls to open the original record with the exact matching text highlighted.
5. Choose **Accept**, **Edit**, **Reject**, or **Ask for clarification** and record a reason. An edit preserves the original text. Missing or conflicting evidence cannot be accepted unchanged; a reviewer correction remains a human judgment, not a newly verified source fact.
6. Respond to requested clarifications and review the finding again. Human responses appear as reviewer-supplied evidence.
7. **Finalize review** becomes available once all findings have decisions and no clarifications remain pending. The backend enforces the same conditions.
8. Reopen a saved analysis to inspect decisions, finalized findings, and review history.

Recalculation refreshes diagnoses, calculator findings, and the summary as pending drafts. Unrelated medication and concern decisions are preserved. Previous drafts and decisions remain in the audit events. Finalized runs cannot be edited; run another analysis to create a new draft.

Automated medication-analysis failures are exposed as unavailable findings, rather than silently implying that medications were checked. Documented condition labels describe the condition in the record; any accompanying draft interpretation remains generated reasoning for the reviewer to assess.

## State and persistence

The existing `apollo_cache.db` now also contains `review_runs`, `review_events`, and `reviewer_sessions`. Review data is durable and is not subject to the answer cache's seven-day TTL. Back up the SQLite database to retain reviews; deleting the cache directory also deletes these records. A future migration should separate operational review storage from disposable caches.

Runs preserve the original analysis, current analysis, source snapshots, findings, clarification state, and a monotonically increasing version. Every mutation checks the client's expected version inside an immediate SQLite transaction. A stale browser gets HTTP 409 and must reload. Changing a different finding also advances the run version.

## Evidence and assertions

Sources include original document text, separately serialized structured record fields, calculator inputs/results, and reviewer clarification responses. Evidence stores a source ID, exact quote, assertion, and start/end offsets into that immutable source snapshot. Offsets count Unicode code points; the frontend uses `Array.from` before highlighting so emoji do not shift the selected passage.

The initial matcher is conservative and deterministic: exact names, sentence/clause-level negation/history rules, and structured diagnosis statuses. A proposal without a documented diagnosis match remains AI suggested. Contradictory affirmative and negative/historical mentions are flagged as conflicting. This is not a clinical entity-linker or complete negation/temporality model. Synonyms, abbreviations, experiencer, long-distance negation, and nuanced temporal changes need additional work. Summary evidence provides context and does not verify every summary claim.

## Reviewer sessions and limits

The server generates an opaque token and reviewer ID; only a hash of the token is stored. Cookies are HttpOnly, SameSite=Strict, expire after seven days, and use Secure on HTTPS. The API rejects cross-origin mutations when the Origin is not allowed. Decision payloads cannot supply a reviewer ID or name; the server attaches the session identity.

Anyone using this local workspace can declare a name and review any stored run. There is no password/OIDC verification, professional-role validation, or patient ownership model. Do not use this as organizational authentication or a production clinical approval system. Shared deployments need verified identities and authorization.

## Audit semantics

Each run has a hash chain of events created in the same transaction as its state update. Events include a timestamp, version, session identity, change details, previous hash, and resulting state hash. The audit endpoint checks chain continuity and that its final state hash matches the stored run. Earlier edits, rejected suggestions, clarification responses, and replaced downstream drafts remain inspectable.

A database administrator can rewrite an entire chain or delete history. There is no external trust anchor, digital signature, WORM storage, or audit-access control. Integrity validation detects inconsistent edits against the retained chain; it is not proof against a privileged rewrite.

## Scope

Human review applies to Analysis findings. The existing summary endpoint and Ask responses remain draft/decision-support outputs and do not use this gate. The finalized review endpoint is the only endpoint providing finalized findings. Human decisions do not automatically retrain models or modify the underlying patient record. FHIR integration remains deferred.
