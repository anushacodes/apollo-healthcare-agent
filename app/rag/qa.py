# TODO: Step 6 — RAG Q&A streaming
# async ask_question_stream(patient_id, question, include_research=False):
#   1. retrieve() top 5 chunks from patient collection
#   2. If include_research → retrieve_research() top 3 from research collection
#   3. Build context with [Doc: filename, Page: N] citations
#   4. System prompt enforces grounded-only answers, no hallucination
#   5. LLM priority: Groq → Gemini → Ollama (small, for lower quality but free)
#   6. Stream response via SSE: data: {"type":"token","content":"..."}
#   7. Final event:              data: {"type":"done","sources":[...]}
#   8. DEV_MODE: return canned response, log chunk count
#   9. LangFuse trace
