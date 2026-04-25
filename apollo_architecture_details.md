# Apollo Healthcare Agent: Complete System Architecture & Implementation Details

This document outlines the entire architecture, implemented features, codebase breakdown, and performance analysis of the Apollo Healthcare Agent.

## 1. Overview of Implemented Features

The Apollo Healthcare Agent is a multi-agent clinical intelligence platform built using FastAPI, LangGraph, Qdrant, and Groq/Gemini. It provides reasoning capabilities, RAG (Retrieval-Augmented Generation), and clinical calculators to assist in medical decision-making.

*   **Multi-Agent Clinical Orchestration:** A sequential LangGraph workflow that extracts structured parameters from clinical text, runs clinical calculators, checks for drug interactions via a Knowledge Graph, generates differential diagnoses, and synthesises a final clinical summary.
*   **Agentic RAG Pipeline:** A highly sophisticated pipeline for the "Ask" feature that streams its reasoning. It categorises user queries, routes them to local patient documents or external clinical research, executes web searches, assesses context sufficiency, generates grounded answers, evaluates itself for hallucinations, and dynamically suggests follow-up questions.
*   **Hybrid Retrieval (RRF):** The system uses a combination of Dense Vector Search (Qdrant + BAAI/bge-small-en-v1.5) and Sparse Keyword Search (BM25Okapi). It fuses the results using Reciprocal Rank Fusion (RRF) for highly accurate context retrieval.
*   **Medical Knowledge Graph (KG):** A Neo4j-backed graph (with a local JSON fallback) that models conditions, symptoms, risk factors, subtypes, and drug interactions.
*   **Persistent Caching:** An aggressive, persistent SQLite caching layer that stores PubMed research queries and generated RAG answers to achieve sub-second latency on repeated queries and survive container restarts.
*   **Dynamic Document Ingestion:** Endpoints that allow dynamic uploading of PDFs and text files, parsing them with IBM Docling, chunking, and embedding them seamlessly into the Qdrant vector store.
*   **Web Fallback (Tavily/DuckDuckGo):** When PubMed results are insufficient, the RAG agent automatically queries high-authority clinical domains (like nih.gov, nejm.org, bmj.com) using the Tavily API (or DuckDuckGo as a fallback).
*   **Safety & Evaluation Guardrails:** Answers are generated strictly from context. An Eval Agent checks the response for faithfulness. If it hallucinates or scores low, the response is still shown to the clinician but is prominently flagged with warnings.

---

## 2. File-by-File Breakdown

### Core API & Config
*   **`app/main.py`**: The FastAPI entry point. It configures CORS, mounts the static frontend files, registers all API routers, and uses a `lifespan` context manager to check the Neo4j connection upon startup.
*   **`app/config.py`**: Handles environment variables via Pydantic Settings. Stores API keys (Groq, Gemini, OpenRouter, Tavily) and database configurations (Qdrant, Neo4j).
*   **`app/models.py`**: Contains Pydantic models defining the data structures used across the API, such as `ClinicalSummary`, `SummarizeRequest`, and various agent state definitions.

### Routers (API Endpoints)
*   **`app/routers/agent.py`**: Provides the `/api/agent/run` endpoint, which triggers the primary LangGraph clinical orchestration workflow for a patient.
*   **`app/routers/rag.py`**: Houses the RAG functionality. Includes the WebSocket endpoint `/stream/{patient_id}` for streaming the agentic RAG thinking process, the `POST /ingest` endpoint for document uploads, and the `GET /sources` endpoint for listing embedded documents.
*   **`app/routers/kg.py`**: Provides endpoints to interact with the Knowledge Graph, such as querying condition details or bulk-seeding Neo4j.
*   **`app/routers/summarize.py`**: An endpoint to quickly fetch patient summaries. It includes fallback logic to raise a `404 Not Found` if a patient doesn't exist, preventing blank data from breaking the summariser.

### Orchestration & Agents
*   **`app/agent/graph.py`**: Defines the main clinical orchestration LangGraph. It runs nodes sequentially: `orchestrator` -> `drug_graph` -> `diagnosis` -> `tool_node` -> `summarizer`.
*   **`app/agent/rag_agent.py`**: Defines the Agentic RAG LangGraph. The nodes are: `query_router`, `patient_retriever`, `research_fetcher` (PubMed), `web_search` (Tavily), `context_assembler`, `sufficiency_judge`, `generator`, `eval_agent`, and `follow_up_agent` (generates dynamic next-questions).
*   **`app/agent/research_agent.py`**: Interacts directly with PubMed APIs (via BioPython) to fetch clinical trial abstracts and guidelines based on the patient's diagnoses.
*   **`app/agent/eval_agent.py`**: Uses an LLM to evaluate generated RAG answers against the retrieved chunks. It checks for faithfulness, context relevance, and completeness, returning warning flags if claims are unsupported.
*   **`app/agent/drug_interaction_agent.py`**: Evaluates potential drug-drug interactions and contraindications using the patient's medication list and the Neo4j Knowledge Graph.
*   **`app/agent/diagnosis_agent.py`**: Processes clinical notes and symptoms through Gemini/Groq to propose primary and differential diagnoses, enriched by KG context.
*   **`app/agent/summarizer.py`**: Synthesises outputs from all other agents into a clean, structured `ClinicalSummary` containing key concerns, timeline, and actionable follow-ups.
*   **`app/agent/tools.py`**: Defines exact Python functions for clinical scoring algorithms (ASCVD Risk, Wells DVT Score, CHA2DS2-VASc), including proper ACC/AHA coefficients.
*   **`app/agent/kg_loader.py`**: Manages the singleton connection to Neo4j. Handles Cypher queries for conditions/symptoms, and manages local JSON fallbacks if Neo4j is offline.
*   **`app/agent/seed_patient.py`**: Contains hardcoded synthetic patient records (Case A, B, C) used for demos, so the app functions without requiring an external database.
*   **`app/agent/sqlite_cache.py`**: Connects to `apollo_cache.db` to persistently store PubMed fetch results and RAG generated answers, drastically reducing API calls.

### Data Ingestion
*   **`app/ingestion/embedder.py`**: Connects to Qdrant. Implements a highly robust Hybrid Search: it executes a dense vector search using local `sentence-transformers`, executes a sparse BM25 ranking across patient chunks, and merges both lists using Reciprocal Rank Fusion (RRF).
*   **`app/ingestion/chunker.py`**: Handles text splitting logic, ensuring clinical documents are cut into appropriate semantic sizes before embedding.
*   **`app/ingestion/extractors/pdf_extractor.py`**: Uses IBM Docling to convert raw PDF documents into structured markdown format.
*   **`app/ingestion/extractors/transcript_extractor.py`**: Parses audio transcriptions, separating speakers and timelines into structured text blocks.

### Frontend
*   **`app/frontend/app.html`**: The unified HTML shell for the application.
*   **`app/frontend/static/js/app.js`**: Core UI logic, tab switching, and API interactions for the main patient summary screen.
*   **`app/frontend/static/js/ask.js`**: Handles the RAG chat UI. Connects to the WebSocket, renders the real-time collapsible "thinking trace", displays citations, formats eval warnings, and dynamically renders the follow-up suggestion chips.
*   **`app/frontend/static/css/clinical.css`**: Defines the premium, clean visual aesthetic of the application, including pill-badges, trace animations, and refusal cards.

---

## 3. Dissection of Weak Points (Vulnerabilities & Latency Bottlenecks)

While the pipeline is functionally robust and agentic, several systemic bottlenecks heavily impact latency and scale.

1.  **Sequential Graph Execution (Major Latency Bottleneck)**
    *   **The Issue**: Both `graph.py` and `rag_agent.py` are built as strictly sequential LangGraphs. In RAG, `patient_retriever`, `research_fetcher`, and `web_search` execute one after another. If each takes 2 seconds, the retrieval phase alone blocks for 6 seconds.
    *   **Impact**: RAG responses can take 10–15 seconds before the generator even begins typing.

2.  **BM25 In-Memory Re-computation**
    *   **The Issue**: In `embedder.py`, true BM25 requires the entire corpus. Currently, to perform hybrid search, the system issues a `client.scroll()` to fetch *all* chunks for a patient from Qdrant, tokenizes them, and builds a `BM25Okapi` index in memory on-the-fly *for every single query*.
    *   **Impact**: While fine for a single patient with 50 chunks, if a patient file has thousands of chunks (e.g., decades of records), fetching them over the network and rebuilding BM25 in memory will cripple the system.

3.  **PubMed Fetching is Blocking and Slow**
    *   **The Issue**: `research_agent.py` calls the NCBI E-utilities API synchronously. This API is notoriously slow and heavily rate-limited. Fetching abstracts and embedding them via `sentence-transformers` during a live user query heavily spikes latency.
    *   **Impact**: Up to 10+ seconds of blocking time when a user asks a research question for the first time (before the SQLite cache saves it).

4.  **Local Sentence Transformers on CPU**
    *   **The Issue**: `BAAI/bge-small-en-v1.5` is loaded directly into the app memory via `sentence-transformers` and runs on the CPU.
    *   **Impact**: CPU-bound embedding computation blocks the FastAPI event loop during document ingestion or PubMed abstract processing.

5.  **State Size Overhead in LangGraph**
    *   **The Issue**: The `RAGState` passes the entire text of `all_chunks` (which could be megabytes) between nodes in the graph over and over.

6.  **Hardcoded Data Models vs. Real Databases**
    *   **The Issue**: Patient data currently relies heavily on `seed_patient.py`. The `_resolve_patient` endpoint has no active connection to a PostgreSQL/FHIR database. If a patient doesn't exist in seed data, it strictly relies on whatever chunks were just uploaded.

---

## 4. Optimization Plan: How to Make it Faster

To transition this system from a functional prototype to a high-speed, production-ready enterprise application, the following architectural shifts are required:

### 1. Parallelize LangGraph Execution
*   **Fix**: Utilize LangGraph's parallel fan-out capabilities. The `query_router` should branch out to `patient_retriever` and `research_fetcher` simultaneously.
*   **Result**: Retrieval time will drop to the speed of the slowest retriever (e.g., from 6 seconds sequential to 2.5 seconds parallel).

### 2. Native Sparse Vectors in Qdrant (Replace In-Memory BM25)
*   **Fix**: Abandon `rank-bm25`. Instead, compute sparse vectors (using SPLADE or BM25 models) at ingestion time. Upload both dense and sparse vectors directly to Qdrant.
*   **Result**: Qdrant handles the hybrid search natively via its API in milliseconds, completely eliminating the need to pull all chunks into Python memory.

### 3. Asynchronous / Background PubMed Fetching
*   **Fix**: Abstract the PubMed fetching into a background worker (e.g., Celery or Python `asyncio.create_task`). When a patient is loaded, the system should aggressively pre-fetch and embed relevant literature *before* the user even asks a question.
*   **Result**: The RAG agent will query Qdrant instantly instead of waiting on the NCBI HTTP API.

### 4. Migrate Embeddings to a Dedicated Service or GPU
*   **Fix**: Do not run `sentence-transformers` in the main FastAPI thread. Either host the embedding model on a dedicated Inference Server (like Ollama or vLLM), use an API (OpenAI/Cohere), or offload the compute to a background queue.

### 5. Stream the Generator Response
*   **Fix**: Currently, the `generator` node waits for the entire LLM response to complete before passing it to `eval_agent`. We should stream the tokens directly to the frontend while simultaneously passing the full string to the eval agent asynchronously.
*   **Result**: Time-to-First-Token (TTFT) perceived by the user will drop to <1 second, making the system feel lightning fast.

### 6. Introduce a Real Patient Database (PostgreSQL/FHIR)
*   **Fix**: Implement PostgreSQL with SQLAlchemy or a true FHIR server (like HAPI FHIR) to manage patient state, demographics, and encounter metadata, rather than relying on static JSON files and caching logic.
