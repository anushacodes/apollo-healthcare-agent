from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.sqlite_cache import get_answer, set_answer


def test_health_cases_and_knowledge_base(client):
    response = client.get("/api/health")
    assert response.json() == {"status": "ok", "llm_provider": "none"}
    assert response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    cases = client.get("/api/agent/cases").json()["cases"]
    assert len(cases) == 3
    for case in cases:
        data = client.get(f"/api/agent/cases/{case['key']}").json()
        assert data["patient_id"]
        assert isinstance(data["source_documents"], dict)
    assert client.get("/api/agent/cases/missing").status_code == 404
    assert client.get("/api/kg/status").json()["local_conditions"] > 0
    assert client.get("/api/kg/conditions/missing").status_code == 404


def test_text_ingestion_without_qdrant_invalidates_cache(client):
    set_answer("patient:abc", "question", {"final_response": "old"})
    response = client.post("/api/rag/ingest/patient", files={
        "file": ("labs.txt", b"Significant proteinuria with elevated creatinine and declining renal function. " * 4),
    })
    assert response.status_code == 200
    assert response.json()["chunks_indexed"] > 0
    assert response.json()["chunks_embedded"] == 0
    assert client.get("/api/rag/sources/patient").json() == {"sources": ["labs.txt"]}
    assert client.get("/api/rag/sources/other").json() == {"sources": []}
    assert get_answer("patient:abc", "question") is None


@pytest.mark.parametrize("name,content,status", [
    ("file.exe", b"unsupported", 415), ("empty.txt", b"", 422), ("short.txt", b" ", 422),
])
def test_invalid_uploads(client, name, content, status):
    assert client.post("/api/rag/ingest/demo", files={"file": (name, content)}).status_code == status


def test_upload_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    response = client.post("/api/rag/ingest/demo", files={"file": ("big.txt", b"x" * (1024 * 1024 + 1))})
    assert response.status_code == 413


@pytest.mark.parametrize("payload", [{"question": ""}, [], {"question": 5}, {"question": "test", "case_key": "missing"}])
def test_rag_invalid_payload_closes_socket(client, payload):
    with client.websocket_connect("/api/rag/stream/demo") as ws:
        ws.send_json(payload)
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_rag_completion_closes_socket(client, monkeypatch):
    from app.routers import rag
    async def stream(*args):
        yield {"type": "done", "data": {"final_response": "answer"}}
        yield {"type": "patch_eval", "data": {"eval_scores": {"faithfulness": 0.9}}}
    monkeypatch.setattr(rag, "run_rag_streaming", stream)
    with client.websocket_connect("/api/rag/stream/demo") as ws:
        ws.send_json({"question": "test"})
        assert ws.receive_json()["type"] == "done"
        assert ws.receive_json()["type"] == "patch_eval"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_summary_passes_force_regenerate(client, case_a, monkeypatch):
    from app.agent.summarizer import run_summarizer
    from app.routers import summarize
    summary = run_summarizer(case_a, force_stub=True)
    mock = AsyncMock(return_value=summary)
    monkeypatch.setattr(summarize.asyncio, "to_thread", mock)
    response = client.post("/api/patients/case_a/summarize", json={"patient_id": "case_a", "force_regenerate": True})
    assert response.status_code == 200
    assert mock.call_args.kwargs["skip_cache"] is True
    assert client.post("/api/patients/unknown/summarize").status_code == 404
    assert client.post("/api/patients/case_a/summarize", json={"patient_id": "other"}).status_code == 400
