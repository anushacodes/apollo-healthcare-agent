from __future__ import annotations

from functools import lru_cache

from groq import Groq

from app.config import settings


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    """Shared Groq client, built once and reused everywhere. Groq's sync
    client wraps httpx.Client, which is safe to share across threads."""
    return Groq(api_key=settings.groq_api_key)
