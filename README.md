# Apollo

[![lint](https://github.com/anushacodes/apollo-healthcare-agent/actions/workflows/lint.yml/badge.svg)](https://github.com/anushacodes/apollo-healthcare-agent/actions/workflows/lint.yml)

A multi-agent system that reasons over patient records — load a patient, ask
clinical questions, get grounded answers with citations and faithfulness
scores. Healthcare is the domain; the point of the project is the agentic
orchestration, retrieval, and evaluation underneath it.

![Home UI](assets/ask_ui.png)

---

## What it does

Two independent LangGraph pipelines run off the same patient record:

**Diagnostics pipeline** — runs on page load, streams each step live:
- Drug/KG agent checks medication combinations against a local clinical knowledge base, then an LLM analyzes interaction risk
- Diagnosis agent proposes a ranked differential with ICD-10 codes and supporting evidence
- Clinical calculators run ASCVD 10-year risk, Wells DVT, and CHA₂DS₂-VASc scores from structured lab data
- Summarizer generates a structured clinical brief + plain-English patient summary
- Real fan-out/fan-in graph: orchestrator branches into the drug/KG agent and calculator tool node in parallel before merging into diagnosis and summarization

**RAG ask pipeline** — triggered by a question, also streamed:
- Query router classifies the question and picks retrieval sources
- Patient docs (Qdrant hybrid search), a curated clinical guideline corpus, and live web search run as needed
- Structured patient record is always injected as the top-ranked context chunk
- Generator answers using `llama-3.3-70b-versatile`, citing specific sources
- A deterministic + LLM-judge eval pass scores faithfulness and hallucination before the answer streams back
- SQLite answer cache makes repeated questions instant

![Architecture](assets/flowchart.png)

---

## Engineering highlights

This project is built as a showcase of agentic AI / ML engineering practice,
not clinical depth:

- **Real graph orchestration** — the diagnostics pipeline has genuine
  parallel fan-out/fan-in branches in LangGraph, not just a linear chain
  dressed up as a graph.
- **Hybrid retrieval** — dense vector search (Qdrant) fused with sparse BM25
  (SQLite FTS5) via reciprocal rank fusion, the same pipeline serving both
  patient documents and the curated corpus.
- **Retrieval without a live external dependency** — the guideline corpus is
  chunked and embedded once at startup and re-used from then on, rather than
  hitting a live API per request (see `app/ingestion/corpus.py`).
- **Eval as a pipeline stage, not an afterthought** — every RAG answer is
  scored for faithfulness and hallucination against its retrieved chunks
  before it's considered final.
- **CI on every push/PR** — ruff lint gate (badge above); a mocked test suite
  and CD are tracked next in `docs/TASKS.md`.

---

## Stack

| | |
|---|---|
| Orchestration | LangGraph (real fan-out/fan-in graph + linear RAG graph) |
| LLM | Groq `llama-3.3-70b-versatile` (generation), `llama-3.1-8b-instant` (eval) |
| Knowledge base | Local JSON — 25 clinical conditions |
| Vector store | Qdrant (dense) + SQLite FTS5 (sparse), fused with RRF |
| Cache | SQLite (answers, summaries, chunks) |
| Document parsing | Docling, PyMuPDF |
| Web search | Tavily (clinical-domain restricted), DuckDuckGo fallback |
| API | FastAPI + WebSocket streaming |
| Frontend | CSS/JS |
| Dependency management | `uv` |
| CI | GitHub Actions (ruff lint) |
| Infra | Docker Compose |

---

## Running it

**With Docker:**

```bash
git clone https://github.com/anushacodes/apollo-healthcare-agent.git
cd apollo-healthcare-agent
cp .env.example .env   # add GROQ_API_KEY
docker-compose up --build
```

**Without Docker** (uses [uv](https://docs.astral.sh/uv/)):

```bash
git clone https://github.com/anushacodes/apollo-healthcare-agent.git
cd apollo-healthcare-agent
cp .env.example .env   # add GROQ_API_KEY
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Qdrant is optional at runtime — the app logs a warning and skips vector
search (falling back to sparse-only retrieval) if it's unreachable, so a bare
Python + Groq key is enough to boot and use the diagnostics pipeline.

Open `http://localhost:8000/app.html`

Minimum: `GROQ_API_KEY`. Optional: `GEMINI_API_KEY` (better summaries),
`TAVILY_API_KEY` (web search fallback).

---

## Project structure

```
app/
├── agent/
│   ├── rag/                   # RAG pipeline package
│   │   ├── prompts.py         # prompt strings
│   │   ├── state.py           # RAGState TypedDict
│   │   ├── nodes.py           # LangGraph node functions
│   │   └── graph.py           # graph builder + streaming runner
│   ├── diagnostics/           # diagnostics pipeline package
│   │   ├── prompts.py         # orchestrator prompt
│   │   ├── state.py           # AgentState TypedDict
│   │   ├── nodes.py           # LangGraph node functions (real fan-out/fan-in)
│   │   └── graph.py           # graph builder + streaming runner
│   ├── eval_agent.py          # faithfulness + hallucination scoring
│   ├── diagnosis_agent.py     # differential diagnosis
│   ├── drug_interaction_agent.py
│   ├── summarizer.py
│   ├── tools.py               # ASCVD, Wells DVT, CHA₂DS₂-VASc calculators
│   ├── sqlite_cache.py        # all caching logic (thread-local connections, WAL mode)
│   ├── kg_loader.py           # local JSON knowledge base lookup
│   └── seed_patient.py        # demo patient definitions
├── ingestion/
│   ├── corpus.py              # one-time curated-corpus embedding (idempotent)
│   ├── chunker.py             # header-aware chunking with overlap
│   ├── embedder.py            # Qdrant + SQLite FTS5 hybrid embed/search
│   └── extractors/            # PDF, image, audio/transcript parsing (Docling)
├── routers/                   # FastAPI endpoints (WebSocket, REST)
├── llm_client.py              # shared Groq client singleton
├── config.py                  # pydantic-settings, single source of runtime config
├── frontend/                  # HTML/CSS/JS UI
└── main.py

assets/
├── ask_ui.png                 # home UI screenshot
└── flowchart.png              # system architecture diagram
data/seed/                     # demo patient files (Case A/B/C)
data/corpus/                   # curated guideline corpus (retrieval-quality demo)
knowledge_graph/                # 25 condition JSON files
tests/                          # pipeline smoke tests
docker-compose.yml
```

---

## Project status

Apollo is mid-refactor, moving from a clinical demo toward a more complete
agentic AI / ML engineering showcase (real graph orchestration, evaluation,
observability, data engineering, guardrails). The live task tracker for that
work isn't part of this public repo — see the project's own working notes if
you have access to them.
