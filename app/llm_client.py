from functools import lru_cache

import instructor
from groq import Groq
from instructor import Instructor, Mode, Provider

from app.config import settings


@lru_cache(maxsize=1)
def get_groq_client() -> Groq:
    """Shared Groq client, built once and reused everywhere. Groq's sync
    client wraps httpx.Client, which is safe to share across threads."""
    return Groq(api_key=settings.groq_api_key)


@lru_cache(maxsize=1)
def get_structured_groq_client() -> Instructor:
    """
    Groq client patched with instructor for validated, typed completions —
    pass `response_model=<a pydantic model>` to `.chat.completions.create`
    and get back a validated instance instead of a raw dict from
    `json.loads`. Uses tool-calling mode (Groq doesn't support instructor's
    plain JSON mode).
    """
    return instructor.patch(get_groq_client(), mode=Mode.TOOLS, provider=Provider.GROQ)
