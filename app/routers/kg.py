from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agent import kg_loader

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])


@router.get("/status")
async def get_kg_status():
    """Show how many conditions are loaded from the local knowledge base."""
    return kg_loader.kg_status()


@router.get("/conditions")
async def list_conditions():
    """List all available condition names."""
    return {"conditions": kg_loader.get_all_condition_names()}


@router.get("/conditions/{name}")
async def get_condition(name: str):
    """Fetch the knowledge block for a specific condition."""
    result = kg_loader.get_condition(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Condition '{name}' not found in KG.")
    return result
