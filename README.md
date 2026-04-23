# APOLLO 🏥
### Autonomous Polyagent Clinical Intelligence System

> A production-grade, multi-agent AI system for clinical decision support — combining knowledge graphs, RAG, fine-tuned models, LLM evals, and a self-improving feedback loop into a single unified platform.


## What Is APOLLO?

APOLLO is not a chatbot. It is not a single model wrapped in a UI.

It is a **multi-agent clinical reasoning system** where specialized AI agents collaborate, challenge each other, and synthesize a unified, safety-checked response to complex clinical queries. Every decision is traceable. Every agent output is evaluated. Every low-confidence answer triggers a deeper reasoning loop before it reaches a clinician.

**The problem it solves:**
A clinician enters a patient summary — symptoms, history, current medications, recent labs. Instead of one model giving one answer, APOLLO deploys a coordinated team of agents: one retrieves from medical literature, one traverses a drug knowledge graph, one summarizes findings in plain language, one verifies the reasoning, and one ensures nothing unsafe or non-compliant leaves the system. The orchestrator synthesizes everything into a structured clinical brief with full reasoning transparency.

**What makes it different from every other healthcare AI project:**
- Agents are not linear chains — they form a **stateful graph with conditional loops**
- Low-confidence outputs **re-route back** for deeper retrieval before surfacing
- An **LLM-as-Judge eval agent** scores every response in real time
- Poor scores don't just get logged — they feed a **fine-tuning pipeline** that improves the system over time
- A **safety compliance agent** acts as the final gatekeeper on every output
- Every decision carries a **full audit trail** — which agent, which model version, which retrieval chunk

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APOLLO SYSTEM                                │
│                                                                     │
│   FRONTEND (HTML/CSS/JS)                                            │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  Clinical Query Input  │  Agent Trace Panel  │  Eval Dashboard│  │
│   └──────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│   FASTAPI GATEWAY            ▼                                      │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              REST API + WebSocket for live traces            │  │
│   └──────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│   LANGGRAPH ORCHESTRATION    ▼                                      │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                   Orchestrator Agent                         │  │
│   │         (routes, coordinates, aggregates, resolves)          │  │
│   │                          │                                   │  │
│   │     ┌────────────────────┼────────────────────┐             │  │
│   │     ▼                    ▼                    ▼             │  │
│   │ Diagnosis Agent    Drug Interaction     Summarization        │  │
│   │ (RAG + KG)         Agent (Neo4j KG)     Agent               │  │
│   │     │                    │              (Fine-tuned          │  │
│   │     └─────────┬──────────┘              FLAN-T5)            │  │
│   │               ▼                              │               │  │
│   │     [Confidence < threshold?]                │               │  │
│   │          │         │                         │               │  │
│   │        YES         NO                        │               │  │
│   │          │         │                         │               │  │
│   │     AutoGen        │◄────────────────────────┘               │  │
│   │  Verification      │                                         │  │
│   │     Loop           ▼                                         │  │
│   │          │    Safety & Compliance Agent                      │  │
│   │          │         │                                         │  │
│   │          └────────►▼                                         │  │
│   │              Eval Agent (LLM-as-Judge)                       │  │
│   │                    │                                         │  │
│   └────────────────────┼─────────────────────────────────────────┘  │
│                        │                                            │
│   DATA LAYER           ▼                                            │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  PostgreSQL (audit logs) │ Redis (agent memory) │ DuckDB     │  │
│   │  Neo4j (knowledge graph) │ Qdrant (vector store)             │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   DATA PIPELINE                                                     │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  Airflow DAGs → PySpark Jobs → DuckDB Warehouse              │  │
│   │  Sources: PubMed, DrugBank, MIMIC-III, ICD-10, SNOMED-CT     │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│   FEEDBACK LOOP                                                     │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  Eval scores logged → Low scores flagged → Human review      │  │
│   │  Reviewed samples → Fine-tuning dataset → Modal training job │  │
│   │  New model version → MLflow registry → Auto-promoted         │  │
│   └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent Roster

### 1. Orchestrator Agent — LangGraph + CrewAI
**Role:** The brain. Receives the raw clinical query, decomposes it into subtasks, assigns each to the right specialist agent, monitors confidence scores across all agent outputs, and decides whether to surface a final answer or re-route into a verification loop.

**Tools:** LangGraph state machine, CrewAI task delegation, Redis for shared agent memory

**Key behavior:** If any downstream agent returns a confidence score below 0.75, the Orchestrator does not proceed to synthesis. It triggers an AutoGen verification loop between the flagging agent and the Diagnosis Agent before continuing.

---

### 2. Diagnosis Agent — RAG + Knowledge Graph
**Role:** Given a patient symptom profile and history, retrieves relevant clinical evidence from PubMed abstracts and traverses the Neo4j disease-symptom-condition graph to generate a ranked differential diagnosis list with supporting evidence citations.

**Tools:** Qdrant vector store (hybrid BM25 + semantic retrieval), Neo4j graph queries, ClinicalBERT embeddings for domain-accurate retrieval

**Key behavior:** Every diagnosis suggestion is grounded — it cites the exact retrieved chunk and graph path that supports it. No hallucinated diagnoses.

---

### 3. Drug Interaction Agent — Knowledge Graph Specialist
**Role:** Given a list of current and proposed medications, traverses the DrugBank knowledge graph in Neo4j to identify contraindications, interaction risks, and dosing concerns. Returns a structured interaction report with severity ratings.

**Tools:** Neo4j (DrugBank + SIDER graphs), SPARQL-style Cypher queries, severity scoring heuristics

**Key behavior:** This agent never uses an LLM for drug facts — it only queries the structured knowledge graph. LLMs hallucinate drug interactions. Graphs do not.

---

### 4. Summarization Agent — Fine-tuned Model
**Role:** Takes the synthesized clinical output from all agents and generates two versions: a structured clinical brief for the physician, and a plain-English patient summary. Domain-accurate, concise, never fabricates.

**Tools:** Fine-tuned FLAN-T5 on clinical note summarization (trained via Modal on free GPU tier), MLflow for model versioning

**Key behavior:** The fine-tuned model is the only model in the system that was trained specifically for this task. It does not improvise — it compresses and clarifies what other agents have already verified.

---

### 5. Safety & Compliance Agent — Guardrails Layer
**Role:** Every output from every agent passes through this layer before leaving the system. Checks for: definitive diagnostic language (not allowed), specific drug dosing instructions (flagged for physician review), PII in outputs, and HIPAA-relevant compliance signals.

**Tools:** Custom rule engine, Guardrails AI, regex + semantic classifiers for prohibited output patterns

**Key behavior:** This agent can block, modify, or flag any output. It is the only agent with veto power. Its decisions are always logged with full justification.

---

### 6. Eval Agent — LLM-as-Judge
**Role:** After the full multi-agent pipeline completes, this agent independently evaluates the final output on four dimensions: factual accuracy (grounded in retrieved sources), safety compliance, reasoning coherence (does the conclusion follow from the evidence?), and hallucination risk. Returns a structured score per dimension.

**Tools:** GPT-4o-mini or Ollama (local) as the judge model, custom eval rubric, scoring logged to PostgreSQL

**Key behavior:** The Eval Agent has no knowledge of which agents produced the output. It evaluates blindly. Scores below threshold trigger a human review flag and the interaction is queued for the fine-tuning feedback loop.

---

### 7. AutoGen Verification Loop — Adversarial Reasoning
**Role:** When confidence is low, the Orchestrator triggers a two-agent AutoGen debate: one agent argues for the current diagnosis hypothesis, the other challenges it with counterevidence retrieved from the knowledge base. The Orchestrator observes and uses the outcome to either confirm or revise the hypothesis.

**Tools:** Microsoft AutoGen multi-agent conversation framework

**Key behavior:** This is not used for every query — only when uncertainty is flagged. It adds latency but significantly improves reliability on ambiguous cases.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Agent Orchestration | LangGraph | Stateful, cyclic agent graphs with conditional routing |
| Agent Roles & Crew | CrewAI | Clean role definitions, task delegation, agent collaboration patterns |
| Verification Loops | AutoGen | Adversarial multi-agent debates for low-confidence cases |
| Heavy ML / Fine-tuning | Modal | Free GPU tier, serverless, no infrastructure management |
| Knowledge Graph | Neo4j | Disease, drug, symptom relationship traversal |
| Vector Store | Qdrant | Hybrid BM25 + semantic retrieval over medical literature |
| Embeddings | ClinicalBERT | Domain-accurate medical text embeddings |
| Summarization Model | FLAN-T5 (fine-tuned) | Task-specific, cheap to fine-tune, runs locally |
| Experiment Tracking | MLflow | Model versioning, run tracking, promotion pipeline |
| Data Pipeline | Airflow + PySpark | Scheduled ingestion, large-scale preprocessing |
| Data Warehouse | DuckDB | Local-first, fast, free, handles MIMIC-III scale easily |
| Agent Memory | Redis | Shared state across agents within a session |
| Audit Logs | PostgreSQL | Full decision trail, eval scores, feedback queue |
| Streaming | Kafka | Real-time event log for agent actions and eval results |
| API Gateway | FastAPI | REST + WebSocket for live agent trace streaming |
| Frontend | HTML + CSS + JS | Clean clinical UI, agent trace panel, eval dashboard |
| Guardrails | Guardrails AI | Safety and compliance checks on all outputs |
| CI/CD | GitHub Actions | Automated testing, Docker builds, deployment checks |
| Containerization | Docker Compose | Full stack runs with one command |

---

## Data Sources

All free, public, and research-accessible:

- **MIMIC-III** — de-identified clinical notes, lab results, diagnoses (requires PhysioNet credentialing — free)
- **PubMed abstracts** — medical literature via the free PubMed API (no key required for bulk)
- **DrugBank open data** — drug interaction and pharmacology graph
- **ICD-10 codes** — diagnosis classification, freely available from CMS
- **SNOMED-CT** — clinical terminology ontology, free for research
- **SIDER** — drug side effects database, open access

---

## Feedback Loop — How APOLLO Gets Smarter

```
Every query runs
       │
       ▼
Eval Agent scores the output (accuracy, safety, coherence, hallucination)
       │
       ├── Score ≥ threshold ──► Logged as high-quality example
       │
       └── Score < threshold ──► Flagged for human review
                                        │
                                        ▼
                              Clinician reviews and corrects
                                        │
                                        ▼
                           Added to fine-tuning dataset (versioned)
                                        │
                                        ▼
                    Modal triggers scheduled fine-tuning job (weekly)
                                        │
                                        ▼
                        New model registered in MLflow
                                        │
                                        ▼
                     Passes eval benchmark → auto-promoted to production
                     Fails benchmark → stays in staging, alert raised
```

This means APOLLO is not static. It has a documented, automated path from "this response was wrong" to "the model has been improved and redeployed." That is what separates a real ML system from a demo.

---

## Frontend — What The Clinician Sees

Three panels on a single page, built in vanilla HTML/CSS/JS:

**Panel 1 — Clinical Query Input**
Clean form: patient age, sex, chief complaint, symptom duration, current medications, relevant history. Submit triggers a WebSocket connection to the FastAPI backend for live streaming.

**Panel 2 — Agent Trace (Live)**
As the LangGraph pipeline executes, each agent's status streams in real time — "Diagnosis Agent: retrieving..." → "Drug Interaction Agent: 2 interactions found" → "Safety Agent: output cleared" → "Eval Agent: scoring...". The clinician sees the reasoning unfold, not just a final answer. Every agent result is expandable to show source citations and confidence scores.

**Panel 3 — Eval Dashboard**
Historical view of system quality over time. Average scores per eval dimension, trend lines, flagged interactions waiting for review, fine-tuning job status. This panel tells the story of APOLLO improving over time.

---

## Repository Structure

```
apollo-healthcare-ai/
│
├── agents/
│   ├── orchestrator.py          # LangGraph state machine + routing logic
│   ├── diagnosis_agent.py       # RAG + Neo4j traversal
│   ├── drug_interaction_agent.py # Knowledge graph queries only
│   ├── summarization_agent.py   # Fine-tuned FLAN-T5 inference
│   ├── safety_agent.py          # Guardrails + compliance rules
│   ├── eval_agent.py            # LLM-as-Judge scoring
│   └── autogen_verifier.py      # AutoGen debate loop
│
├── crew/
│   └── apollo_crew.py           # CrewAI role definitions and task configs
│
├── data_pipeline/
│   ├── airflow_dags/
│   │   ├── pubmed_ingestion.py
│   │   ├── drugbank_ingestion.py
│   │   └── mimic_preprocessing.py
│   ├── spark_jobs/
│   │   ├── clinical_notes_processor.py
│   │   └── feature_extractor.py
│   └── duckdb_warehouse/
│       └── schema.sql
│
├── knowledge/
│   ├── graph/
│   │   ├── neo4j_setup.py       # Graph schema and seed scripts
│   │   ├── disease_symptom_loader.py
│   │   └── drugbank_loader.py
│   └── vectorstore/
│       ├── qdrant_setup.py
│       └── pubmed_embedder.py   # ClinicalBERT embedding pipeline
│
├── ml/
│   ├── fine_tuning/
│   │   ├── train_summarizer.py  # QLoRA fine-tuning on Modal
│   │   ├── modal_runner.py      # Modal deployment config
│   │   └── dataset_builder.py   # Builds training set from feedback queue
│   └── mlflow_tracking/
│       ├── experiment_config.py
│       └── model_promoter.py    # Auto-promotion logic
│
├── feedback/
│   ├── eval_pipeline.py         # Schedules eval runs, logs scores
│   ├── review_queue.py          # Manages flagged interactions
│   └── finetune_trigger.py      # Watches queue, triggers Modal job
│
├── safety/
│   ├── guardrails_config.py
│   ├── pii_scrubber.py
│   └── compliance_rules.py
│
├── api/
│   ├── main.py                  # FastAPI app
│   ├── routes/
│   │   ├── query.py             # Main clinical query endpoint
│   │   ├── eval.py              # Eval dashboard data
│   │   └── feedback.py          # Human review submission
│   └── websocket_manager.py     # Live agent trace streaming
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js                   # WebSocket client + dynamic UI
│
├── docker-compose.yml           # Full stack: Neo4j, Qdrant, Redis, Kafka, Postgres, Airflow
├── .github/
│   └── workflows/
│       ├── ci.yml               # Tests on every push
│       └── deploy.yml           # Docker build + push on merge to main
├── requirements.txt
├── .env.example
└── README.md
```

---

## Build Plan — Week by Week

**Week 1 — Data Foundation**
Set up DuckDB warehouse, Airflow DAGs for PubMed + DrugBank ingestion, PySpark preprocessing for MIMIC-III clinical notes, Neo4j graph schema and seed data loaded.

**Week 2 — Knowledge Layer**
Qdrant vector store populated with ClinicalBERT embeddings of PubMed abstracts. Neo4j drug interaction graph complete and queryable. Hybrid retrieval working end to end.

**Week 3 — Core Agents**
Diagnosis Agent and Drug Interaction Agent built and tested independently. Safety Agent rules defined. CrewAI crew defined with all agent roles.

**Week 4 — Orchestration**
LangGraph state machine wiring all agents together. Conditional routing based on confidence scores working. AutoGen verification loop integrated for low-confidence paths.

**Week 5 — ML Layer**
FLAN-T5 fine-tuning pipeline on Modal. MLflow tracking integrated. Summarization Agent using fine-tuned model. Model versioning and promotion logic working.

**Week 6 — Eval + Feedback Loop**
LLM-as-Judge Eval Agent implemented. Scores logged to PostgreSQL. Human review queue built. Fine-tuning trigger watching queue. Full feedback loop running end to end.

**Week 7 — API + Frontend**
FastAPI gateway complete. WebSocket streaming working. HTML/CSS/JS frontend with all three panels. Live agent trace visible in browser.

**Week 8 — Polish + CI/CD**
Docker Compose for full stack. GitHub Actions CI/CD. README complete with architecture diagram. Demo video recorded.
