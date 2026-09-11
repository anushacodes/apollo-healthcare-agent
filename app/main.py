import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.mcp.server import mcp
from app.middleware import RequestContextMiddleware
from app.routers import agent as agent_router
from app.routers import kg as kg_router
from app.routers import rag as rag_router
from app.routers import summarize

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)


mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp_app.lifespan(app))
        await _startup(app)
        yield
    # Shutdown (nothing to clean up yet)


async def _startup(app: FastAPI) -> None:
    try:
        from app.agent.kg_loader import kg_status
        status = kg_status()
        log.info(f"[startup] Local KG loaded: {status['local_conditions']} conditions.")
    except Exception as exc:
        log.warning(f"[startup] KG status check failed (non-fatal): {exc}")

    # Pre-load the sentence-transformers encoder once so the first request is instant.
    # This also warms the Qdrant connection so the first query doesn't pay a cold-start penalty.
    try:
        import asyncio

        from app.ingestion.embedder import _get_client, _get_encoder
        await asyncio.to_thread(_get_encoder)
        await asyncio.to_thread(_get_client)
        log.info("[startup] Embedding model and Qdrant client pre-loaded.")
    except Exception as exc:
        log.warning("[startup] Embedding pre-load failed (non-fatal): %s", exc)

    # One-time embed of the curated corpus (idempotent — skips already-indexed files)
    try:
        from app.ingestion.corpus import index_corpus
        upserted = await index_corpus()
        log.info("[startup] Curated corpus indexed (%d new chunks upserted).", upserted)
    except Exception as exc:
        log.warning("[startup] Curated corpus indexing failed (non-fatal): %s", exc)


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


@app.get("/app.html")
@app.get("/index.html")
async def legacy_frontend_redirect():
    return RedirectResponse(url="/", status_code=307)


app.mount("/mcp", mcp_app)
app.mount("/", StaticFiles(directory="app/frontend_dist", html=True), name="frontend")

log.info("Apollo API started")
