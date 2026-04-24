from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import summarize

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(
    title="MedContext — Apollo Clinical Intelligence",
    description="Multi-agent clinical reasoning API.",
    version="0.1.0-alpha",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(summarize.router)

# Static frontend
app.mount("/", StaticFiles(directory="app/frontend", html=True), name="frontend")

log.info("Apollo MedContext API started")
