import json
import logging
from typing import Any

from fastmcp import Client

from app.mcp.server import mcp

log = logging.getLogger(__name__)


async def call_search_clinical_guidelines(query: str, top_k: int = 6) -> list[dict[str, Any]]:
    """
    Calls the `search_clinical_guidelines` MCP tool over a real (in-memory)
    MCP client/server connection — the RAG graph reaches the curated corpus
    through the MCP protocol rather than a direct function call, per
    docs/TASKS.md Epic 3.2.
    """
    async with Client(mcp) as client:
        result = await client.call_tool("search_clinical_guidelines", {"query": query, "top_k": top_k})

    if result.is_error:
        log.warning("[mcp] search_clinical_guidelines tool call failed: %s", result.content)
        return []

    for block in result.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)

    return result.structured_content.get("result", []) if result.structured_content else []
