# API reference

[Back to Apollo](../README.md) · Interactive docs: `http://localhost:8000/docs`

## API examples

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/agent/cases

curl -X POST http://localhost:8000/api/agent/run/demo-case-a \
  -H 'Content-Type: application/json' -d '{"case":"case_a"}'

# Upload synthetic text to a separate patient namespace.
curl -X POST http://localhost:8000/api/rag/ingest/example-patient \
  -F 'file=@data/seed/case_a_labs.txt'
curl http://localhost:8000/api/rag/sources/example-patient

curl -X POST http://localhost:8000/api/patients/case_a/summarize \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"case_a","force_regenerate":true}'
```

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Process health and selected LLM provider; not upstream readiness |
| `/api/agent/cases` | GET | Available synthetic cases |
| `/api/agent/cases/{case_key}` | GET | Full case record |
| `/api/agent/run/{patient_id}` | POST / WS | Diagnostics; send `{"case":"case_a"}` or a patient record |
| `/api/rag/stream/{patient_id}` | WS | Ask; send `{"question":"...","case_key":"case_a"}`; omit `case_key` for an uploaded namespace |
| `/api/rag/ingest/{patient_id}` | POST | Multipart `file`; text/selectable PDFs by default; scans and other formats with `inference` |
| `/api/rag/sources/{patient_id}` | GET | Indexed source names from SQLite, including sparse-only ingestion |
| `/api/kg/status` | GET | Knowledge-base condition count |
| `/api/kg/conditions` | GET | Condition names |
| `/api/kg/conditions/{name}` | GET | Condition knowledge block |
| `/api/patients/{patient_id}/summarize` | POST | Summary for demo keys `case_a`, `case_b`, `case_c` |
| `/mcp/` | MCP HTTP | Guideline search tool |

Upload errors distinguish unsupported types (415), empty/unindexable content (422), and size violations (413). Uploads support RAG retrieval and return a separate structured-extraction draft. Accepted or corrected extraction fields enter the record only after review finalization. Uploads do not create a patient in the selector. The summary endpoint does not summarize uploaded patient namespaces. Its `cached` response flag is currently conservative (`false`), even when the underlying summarizer uses its cache.


## Human review

Both diagnostics transports now save drafts. The HTTP response includes `review_run`; WebSockets send `node="__review__"` with that run before `__done__`. Original diagnostics fields remain available as draft outputs.

| Endpoint under `/api/review` | Method | Purpose |
| --- | --- | --- |
| `/session` | GET / POST | Inspect session / create a local self-declared reviewer session (`{"name":"Reviewer"}`) |
| `/patients/{patient_id}/runs` | GET | List up to 50 recent saved analyses; use `?kind=extraction` for document reviews |
| `/patients/{patient_id}/extract` | POST | Propose fields from `{source_name, text}`; creates a draft without committing fields |
| `/patients/{patient_id}/fields` | GET | Finalized document fields with source and reviewer provenance |
| `/runs/{run_id}` | GET | Current review state, findings, source snapshots, and clarifications |
| `/runs/{run_id}/sources/{source_id}` | GET | Stored evidence source; source IDs can contain `/` |
| `/runs/{run_id}/findings/{finding_id}/decision` | POST | Accept, edit, reject, or request clarification |
| `/runs/{run_id}/clarifications/{id}` | POST | Supply calculator inputs or skip with a reason |
| `/runs/{run_id}/clarifications/{id}/response` | POST | Respond to a finding clarification |
| `/runs/{run_id}/finalize` | POST | Finalize after all findings and clarifications are resolved |
| `/runs/{run_id}/final` | GET | Accepted/edited findings only; 409 until finalized |
| `/runs/{run_id}/audit` | GET | Decision history and audit-chain integrity result |

Mutations require a valid reviewer cookie and the current run `version`. Decisions use actions `accepted`, `edited`, `rejected`, or `clarification_requested`, with a nonempty `reason`; `edited_text` is required for analysis edits. Extraction edits require structured `edited_data` instead. Both are forbidden for non-edit actions. The server attaches reviewer identity from its session, not the JSON body. Stale versions or finalized-state changes return 409; missing sessions return 401; unsupported input or missing required content returns 422.

```bash
# Keep the server-issued cookie for later mutation requests.
curl -c /tmp/apollo-review-cookie -X POST http://localhost:8000/api/review/session \
  -H 'Content-Type: application/json' -d '{"name":"Local Reviewer"}'

# Substitute IDs and use the latest version returned by the API.
curl -b /tmp/apollo-review-cookie -X POST \
  http://localhost:8000/api/review/runs/RUN_ID/findings/FINDING_ID/decision \
  -H 'Content-Type: application/json' \
  -d '{"version":1,"action":"accepted","reason":"Compared the finding with its source passage"}'
```

See [review behavior and limitations](REVIEW.md), including self-declared identities, local access scope, source-matching limitations, and audit guarantees.

See [structured extraction](EXTRACTION.md) for supported formats, field schemas, review behavior, and fixture validation.
