# TODO: Step 8 — LangGraph StateGraph
#
# AgentState: patient_id, summary, search_queries, pubmed_results,
#             web_results, downloaded_docs, indexed_count, status, error
#
# Nodes (in order):
#   1. extract_queries  — LLM (Groq → Gemini → Ollama) generates 5 PubMed + 3 web queries
#   2. search_pubmed    — calls pubmed_search for each query, deduplicates by PMID
#   3. search_web       — calls web_search, filters to trusted domains
#   4. download_papers  — calls download_and_parse, max 10 downloads
#   5. index_research   — chunks + embeds into `research_{patient_id}` collection
#   6. finalize         — updates agent_runs table: status=completed
#
# Conditional edge: any error → error_handler node (logs + updates DB)
# Graph compiled once and reused (graph = workflow.compile())
