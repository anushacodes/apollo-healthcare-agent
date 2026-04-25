from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.middleware import RequestContextMiddleware
from app.routers import summarize
from app.routers import agent as agent_router
from app.routers import kg as kg_router
from app.routers import rag as rag_router

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.has_neo4j:
        try:
            from app.agent.kg_loader import kg_status
            status = kg_status()
            log.info(
                f"[startup] Neo4j available. "
                f"Local: {status['local_conditions']} conditions, "
                f"Neo4j: {status['neo4j_conditions_seeded']} seeded. "
                f"KG loads on-demand — use POST /api/kg/seed to bulk import."
            )
        except Exception as exc:
            log.warning(f"[startup] Neo4j status check failed (non-fatal): {exc}")
    else:
        log.info("[startup] Neo4j not configured — using local JSON KG with on-demand loading")

    # Pre-load the sentence-transformers encoder once so the first request is instant.
    # This also warms the Qdrant connection so the first query doesn't pay a cold-start penalty.
    try:
        import asyncio
        from app.ingestion.embedder import _get_encoder, _get_client
        await asyncio.to_thread(_get_encoder)
        await asyncio.to_thread(_get_client)
        log.info("[startup] Embedding model and Qdrant client pre-loaded.")
    except Exception as exc:
        log.warning("[startup] Embedding pre-load failed (non-fatal): %s", exc)

    yield
    # Shutdown (nothing to clean up yet)


app = FastAPI(
    title="Apollo — Clinical Intelligence Platform",
    description="Multi-agent clinical reasoning: RAG, KG, calculators, LLM orchestration.",
    version="0.2.0-alpha",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(summarize.router)
app.include_router(agent_router.router)
app.include_router(kg_router.router)
app.include_router(rag_router.router)

app.mount("/", StaticFiles(directory="app/frontend", html=True), name="frontend")

log.info("Apollo API started")
