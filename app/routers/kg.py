from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agent import kg_loader

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])


@router.get("/status")
async def get_kg_status():
    """Show how many conditions are loaded locally vs seeded into Neo4j."""
    return kg_loader.kg_status()


@router.get("/conditions")
async def list_conditions():
    """List all available condition names (local JSON or Neo4j)."""
    return {"conditions": kg_loader.get_all_condition_names()}


@router.get("/conditions/{name}")
async def get_condition(name: str):
    """Fetch knowledge block for a specific condition. Seeds to Neo4j on-demand."""
    result = kg_loader.get_condition(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Condition '{name}' not found in KG.")
    return result


@router.post("/seed")
async def bulk_seed(background_tasks: BackgroundTasks, force: bool = False):
    """
    Bulk seed all local KG JSON files into Neo4j.
    Runs in the background — returns immediately.
    Set force=true to re-seed already-present conditions.
    """
    def _run_seed():
        count = kg_loader.seed_neo4j(force=force)
        return count

    background_tasks.add_task(_run_seed)
    return {
        "status": "seeding started in background",
        "force": force,
        "message": "Check GET /api/kg/status to monitor progress.",
    }


@router.post("/seed/{condition_name}")
async def seed_single_condition(condition_name: str):
    """Seed a single condition into Neo4j on-demand."""
    seeded = kg_loader.seed_condition_on_demand(condition_name)
    if not seeded:
        status = kg_loader.kg_status()
        if not status["neo4j_available"]:
            raise HTTPException(status_code=503, detail="Neo4j is not available.")
        return {"status": "already_seeded", "condition": condition_name}
    return {"status": "seeded", "condition": condition_name}
