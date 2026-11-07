import os
import socket
import tempfile
import threading

import pytest

# Set before importing app modules so collection cannot create real patient/cache data.
_test_data = tempfile.TemporaryDirectory(prefix="apollo-tests-")
os.environ["DATA_ROOT"] = _test_data.name

from app.agent.seed_patient import get_case  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    from app.agent import sqlite_cache
    from app.config import settings
    from app.ingestion import embedder

    monkeypatch.setattr(sqlite_cache, "DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(sqlite_cache, "_local", threading.local())
    sqlite_cache.init_db()
    for key in ("groq_api_key", "gemini_api_key", "openrouter_api_key", "tavily_api_key"):
        monkeypatch.setattr(settings, key, None)
    monkeypatch.setattr(embedder, "_get_client", lambda: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not access the network or download embedding models")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(embedder, "_get_encoder", forbidden)


@pytest.fixture
def case_a():
    return get_case("case_a")


@pytest.fixture
def case_b():
    return get_case("case_b")


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    async def startup(app):
        return None

    monkeypatch.setattr(main, "_startup", startup)
    with TestClient(main.app) as test_client:
        yield test_client
