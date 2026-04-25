# Apollo
**Multi-agent clinical intelligence platform** — a local-first system where AI agents collaborate to analyse patient records, flag drug interactions, propose differential diagnoses, and generate structured clinical summaries.

Built to demonstrate production-grade LLM orchestration, knowledge graph integration, and real-time agent streaming — not a chatbot wrapper.

---

## Demo

> 📸 _Screenshot or GIF here_

> 🎥 _Demo video link here_

---

## What It Does

A clinician loads a patient record. The system runs a sequential multi-agent pipeline, streaming each step live to the UI:

```
Orchestrator → Drug/KG Agent → Diagnosis Agent → Clinical Calculators → Summarizer
```

**Each agent has a defined role:**

| Agent | What it does |
|---|---|
| Orchestrator | Parses patient context, extracts structured calculator inputs from labs/demographics, routes to other agents |
| Drug / KG Agent | Checks medication combinations against a Neo4j knowledge graph; flags interactions and contraindications |
| Diagnosis Agent | Proposes a ranked differential diagnosis with ICD-10 codes, confidence levels, and supporting evidence |
| Clinical Calculators | Runs ASCVD 10-year risk, Wells DVT score, and CHA₂DS₂-VASc — inputs extracted from structured patient data |
| Summarizer | Generates a structured clinical brief + plain-English patient summary |

---

## Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (stateful sequential graph) |
| Primary LLM | Groq — `llama-3.3-70b-versatile` |
| Fallback LLM | Google Gemini — `gemini-2.0-flash` |
| Third-string | OpenRouter — `llama-3-8b-instruct:free` |
| Knowledge Graph | Neo4j — 25 DiReCT clinical conditions, lazy on-demand seeding |
| Document Parsing | Docling, PyMuPDF, Pillow |
| Vector Store | Qdrant _(wired, RAG pipeline pending)_ |
| API | FastAPI + WebSocket streaming |
| Frontend | Vanilla HTML/CSS/JS — clinical light theme, no framework |
| Infra | Docker Compose (Neo4j, Qdrant, Langfuse) |

---

## Features

- **Live agent trace** — each node streams an audit entry to the UI as it completes
- **Progressive result panels** — drug interactions, diagnoses, calculators, and summary appear sequentially
- **Structured calculator extraction** — numeric inputs (cholesterol, BP) read directly from lab JSON; LLM fills in clinical booleans from notes
- **KG fallback** — if Neo4j is offline, falls back to local JSON (25 conditions always available)
- **Multi-provider fallback** — Groq → Gemini → OpenRouter, each agent tries in order
- **3 demo patients** — Case A: SLE/Lupus Nephritis, Case B: COPD/Heart Failure, Case C: Post-surgical PE
- **Document ingestion pipeline** — PDF, image, audio transcript extraction (chunker/embedder wired, RAG pending)

---

## Screenshots

> 📸 _Summary tab_

> 📸 _Diagnostics tab — live agent audit trail_

> 📸 _Drug interactions panel_

---

## What's Coming

- [ ] **RAG / Ask tab** — hybrid BM25 + semantic retrieval over uploaded documents
- [ ] **Research Agent** — PubMed integration, guideline surfacing
- [ ] **Eval Agent** — LLM-as-judge scoring on every pipeline run
- [ ] **Fine-tuning pipeline** — feedback loop from flagged low-confidence outputs
- [ ] **Auth** — basic session auth for multi-user use
- [ ] **Whisper transcription** — audio consultation upload

---

## Run It

See [`RUNNING.md`](RUNNING.md) for the full setup guide.

**TL;DR:**
```bash
git clone https://github.com/anushacodes/apollo-healthcare-agent.git
cd apollo-healthcare-agent
uv sync
cp .env.example .env       # add GROQ_API_KEY at minimum
docker-compose up qdrant neo4j -d
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/app.html?case=case_a**

---

## Project Structure

```
app/
├── agent/
│   ├── graph.py               # LangGraph pipeline definition
│   ├── tools.py               # ASCVD, Wells DVT, CHA₂DS₂-VASc calculators
│   ├── diagnosis_agent.py     # Differential diagnosis (Gemini / Groq)
│   ├── drug_interaction_agent.py  # Drug checks (Gemini / Groq + Neo4j)
│   ├── summarizer.py          # Clinical summary (Groq / Gemini)
│   ├── kg_loader.py           # Neo4j driver + local JSON fallback
│   └── seed_patient.py        # Demo case definitions
├── routers/
│   ├── agent.py               # WebSocket streaming endpoint
│   ├── summarize.py           # REST summarization endpoint
│   └── kg.py                  # KG admin endpoints
├── ingestion/                 # Document parsing pipeline
├── rag/                       # Retriever stubs (pending)
├── frontend/                  # HTML/CSS/JS UI
└── main.py                    # FastAPI app + lifespan

kg/                            # 25 DiReCT condition JSON files
data/seed/                     # Demo patient records (James Hartwell case files)
docker-compose.yml
pyproject.toml
RUNNING.md
```
