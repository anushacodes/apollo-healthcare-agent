import functools
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_KG_DIR = Path(__file__).parent.parent.parent / "knowledge_graph"


@functools.cache
def _load_local() -> dict[str, dict]:
    kg: dict[str, dict] = {}
    for path in _KG_DIR.glob("*.json"):
        try:
            kg[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(f"[kg] Failed to load {path.name}: {exc}")
    log.info(f"[kg] Loaded {len(kg)} conditions from local JSON")
    return kg


def search_by_symptoms(symptoms: list[str]) -> list[dict[str, Any]]:
    """Look up conditions matching the given symptoms from the local JSON knowledge base."""
    kg = _load_local()
    matches = []
    for condition, payload in kg.items():
        knowledge = payload.get("knowledge", {})
        all_text = json.dumps(knowledge).lower()
        matched = [s for s in symptoms if s.lower() in all_text]
        if matched:
            suspected_key = next(iter(knowledge), None)
            suspected = knowledge.get(suspected_key, {}) if suspected_key else {}
            matches.append({
                "condition": condition,
                "matched_symptoms": matched,
                "score": len(matched),
                "symptom_description": suspected.get("Symptoms", "")[:300],
                "risk_factors": suspected.get("Risk Factors", ""),
            })
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:10]


def get_condition(name: str) -> dict[str, Any] | None:
    """Fetch a condition's knowledge block from the local JSON knowledge base."""
    kg = _load_local()
    name_lower = name.lower()
    for key, payload in kg.items():
        if name_lower in key.lower() or key.lower() in name_lower:
            knowledge = payload.get("knowledge", {})
            suspected_key = next(iter(knowledge), None)
            suspected = knowledge.get(suspected_key, {}) if suspected_key else {}
            subtree = payload.get("diagnostic", {})
            subtypes = list(list(subtree.values())[0].keys()) if subtree else []
            return {
                "name": key,
                "symptoms": suspected.get("Symptoms", ""),
                "risk_factors": suspected.get("Risk Factors", ""),
                "signs": suspected.get("Signs", ""),
                "subtypes": subtypes,
            }
    return None


def get_all_condition_names() -> list[str]:
    return sorted(_load_local().keys())


def kg_status() -> dict[str, Any]:
    """Return current KG status — useful for the admin endpoint."""
    return {"local_conditions": len(_load_local())}
