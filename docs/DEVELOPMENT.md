# Development guide

[Back to Apollo](../README.md)

## Run locally

Use Python 3.12 (the version tested in CI), [uv](https://docs.astral.sh/uv/), and Node.js 24 LTS with npm. Run commands from the repository root unless indicated otherwise.

```bash
cp .env.example .env
# Set GROQ_API_KEY or OPENROUTER_API_KEY in .env for generated answers.
uv sync --group dev
npm --prefix app/frontend-src install
npm --prefix app/frontend-src run build
uv run --frozen uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>. Select a case, inspect **Overview**, run **Analysis**, and use **Ask**. **Documents** opens the case's raw source files; source records remain available for inspection, and additional documents can be imported through structured review. Case A includes raw notes; Cases B and C primarily use structured records.

Without API keys, browsing, ingestion, sparse search, calculators, and heuristic summary fallback work. Generated RAG answers and LLM evaluations require Groq or OpenRouter. Gemini is a summarizer fallback; it does not enable the entire RAG pipeline on its own.

The API can start before the frontend is built. `/` returns a setup message until the frontend is built and the API restarts; `/docs` and `/api/health` remain available.

### Frontend development

Start the API above, then in a second terminal:

```bash
npm --prefix app/frontend-src run dev
```

Use the URL Vite prints (normally <http://localhost:5173>). Vite proxies `/api`, including WebSockets, to port 8000. Rebuild the frontend and restart the API to serve production assets from port 8000.

### Dense retrieval and document models

The default install supports plain-text and selectable-PDF ingestion and persistent SQLite FTS5 search. Qdrant and local model packages are optional:

```bash
uv sync --group dev --extra inference
docker compose up -d qdrant
uv run --frozen --extra inference uvicorn app.main:app --reload --port 8000
```

The `inference` extra installs Docling, sentence-transformers, and their model dependencies. It enables scanned PDF/Word/image extraction and dense retrieval using `BAAI/bge-small-en-v1.5`. Initial model use can download weights and take time; image OCR may need substantial memory. These model-dependent paths are not exercised by the offline suite.

If Qdrant is unreachable, documents still enter SQLite and remain searchable. The corpus index retries dense indexing on a later startup when dense dependencies are restored. Patient documents can be uploaded again to populate dense vectors after a sparse-only ingest.

### Docker

```bash
cp .env.example .env
# Configure a generation provider in .env.
docker compose up --build
```

The multi-stage Dockerfile builds the frontend and installs the full CPU inference stack. Compose runs the API at port 8000 and Qdrant at port 6333. It persists SQLite data under `./data` and Qdrant data in a named volume. The source directory is not mounted over the built frontend. Model weights may download on first use.

`docker compose --profile observability up` also starts the optional Langfuse infrastructure. Application tracing is not wired to it yet.

## Configuration

Copy [`.env.example`](../.env.example); runtime settings live in [`app/config.py`](../app/config.py).

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Primary generation, structured agent output, and evaluation |
| `OPENROUTER_API_KEY` | Alternative generation provider and fallback |
| `LLM_PROVIDER` | Preferred provider: `groq` or `openrouter` |
| `GROQ_MODEL`, `GROQ_EVAL_MODEL`, `OPENROUTER_MODEL` | Override provider model names |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional summary fallback |
| `QDRANT_URL`, `QDRANT_API_KEY` | Optional dense store; default URL is `http://localhost:6333` |
| `TAVILY_API_KEY` | Clinical-domain web search; DuckDuckGo is the fallback |
| `DATA_ROOT` | Writable patient/cache directory; default `data` |
| `MAX_UPLOAD_SIZE_MB` | Per-file upload cap; default 20 MB |
| `ALLOWED_ORIGINS` | JSON array of permitted HTTP origins |
| `LOG_LEVEL` | Python logging level; default `INFO` |

Seed files, knowledge blocks, and the guideline corpus ship with the repository. `DATA_ROOT` controls runtime storage, not these bundled assets. `SECRET_KEY` and the Langfuse variables are reserved settings and currently do not provide authentication or tracing.

## Verification

```bash
uv sync --group dev
uv run --frozen ruff check .
uv run --frozen pytest -q
npm --prefix app/frontend-src install
npm --prefix app/frontend-src run lint
npm --prefix app/frontend-src run build
```

Tests isolate SQLite in temporary directories, disable credentials and network access, and mock external LLM/retrieval services. They cover conditional RAG routing, refusals, streaming completion, evaluation and caching, upload validation, sparse retrieval and document replacement, patient isolation, MCP search, API behavior, and diagnostics. CI runs Python lint, offline tests, and the frontend lint/typecheck/build as separate jobs. Python and npm lockfiles are generated locally and ignored by Git. Fresh installations resolve dependencies from the manifests, so versions may differ between machines.


## Review storage and evaluation

Analysis reviews use the existing SQLite database, including immutable source snapshots and original drafts. This is operational data: do not delete `data/.cache` to clear answers without first backing up review records. See [review workflow](REVIEW.md).

```bash
uv run --frozen python -m app.evaluation
```

This runs the labeled offline review-policy set. It does not benchmark live model quality. See [evaluation scope](EVALUATION.md).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Setup message at `/` | Build `app/frontend-src` and restart the API. |
| Generation fails or only fallback results appear | Set `GROQ_API_KEY` or `OPENROUTER_API_KEY` in the root `.env`, check provider access, and restart the API. |
| Qdrant is unavailable | Sparse retrieval still works. Start Qdrant and install the `inference` extra to enable dense search. |
| Scanned PDF/image ingestion fails | Upload a selectable-text PDF or text export; OCR requires `--extra inference` and model-download access. |
| New uploaded patient is missing from the selector | Upload namespaces support API-driven RAG only; the selector contains the three bundled cases. |
| Langfuse starts but shows no traces | Infrastructure is optional; application instrumentation is not implemented yet. |

## Structured extraction

See [extraction workflow and validation](EXTRACTION.md). Run `uv run --frozen python -m app.ingestion.evaluate_extraction` for the ten-case offline extraction set. Approved fields live in `reviewed_document_fields` alongside the existing review tables in SQLite; retain this database when upgrading.
