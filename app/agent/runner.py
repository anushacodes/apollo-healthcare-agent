# TODO: Step 8 — Async agent runner (called as asyncio.create_task)
# async run_research_agent(patient_id, summary):
#   1. Create agent_run record in DB (status=running)
#   2. Compile LangGraph graph (if not already compiled)
#   3. graph.ainvoke(initial_state)  — do NOT use asyncio.run() inside BackgroundTask
#   4. Update agent_run on completion (status=completed, papers_found=N)
