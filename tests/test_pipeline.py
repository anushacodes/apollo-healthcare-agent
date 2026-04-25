"""
tests/test_pipeline.py
Run with:  python -m pytest tests/ -v
       or:  python tests/test_pipeline.py
"""
from __future__ import annotations

import asyncio


def test_chunker():
    from app.agent.seed_patient import get_case
    from app.ingestion.chunker import chunk_text

    data = get_case("case_a")
    labs = data["source_documents"]["labs"]
    chunks = chunk_text(labs, "demo", "labs")
    assert len(chunks) > 0, "Chunker returned no chunks for labs document"
    print(f"Chunker: {len(chunks)} chunks from labs document")


def test_rag_streaming():
    from app.agent.rag_agent import run_rag_streaming
    from app.agent.seed_patient import get_case

    async def _run():
        patient_data = get_case("case_a")
        events = []
        async for event in run_rag_streaming("demo-case-a", patient_data, "What are the key concerns?"):
            events.append(event)
            print("EVENT:", event.get("node"), event.get("message"))
        assert any(e.get("type") == "done" for e in events), "No done event received"

    asyncio.run(_run())


if __name__ == "__main__":
    test_chunker()
    test_rag_streaming()
    print("\nAll tests passed.")
