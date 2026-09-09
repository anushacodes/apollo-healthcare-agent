from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.client import call_search_clinical_guidelines


@pytest.mark.asyncio
async def test_search_clinical_guidelines_returns_chunks():
    fake_chunks = [{"text": "ACE inhibitors are first-line in HFrEF.", "source_doc": "heart_failure_hfref.md"}]
    with patch("app.mcp.server.search_chunks_async", new=AsyncMock(return_value=fake_chunks)):
        result = await call_search_clinical_guidelines("heart failure treatment", top_k=3)

    assert result == fake_chunks


@pytest.mark.asyncio
async def test_search_clinical_guidelines_empty_when_no_matches():
    with patch("app.mcp.server.search_chunks_async", new=AsyncMock(return_value=[])):
        result = await call_search_clinical_guidelines("nonexistent condition")

    assert result == []
