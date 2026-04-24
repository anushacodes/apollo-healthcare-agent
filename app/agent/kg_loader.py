from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from neo4j import GraphDatabase, Driver

from app.config import settings

log = logging.getLogger(__name__)

_KG_DIR = Path(__file__).parent.parent.parent / "kg"
_LOCAL_CACHE: dict[str, dict] = {}

# Singleton Neo4j driver — created once, reused across all calls
_driver: Driver | None = None
_driver_failed: bool = False  # avoid retrying a permanently broken connection

# Neo4j Cypher — schema adapted from wbw520/DiReCT
_CREATE_CONDITION = """
MERGE (c:Condition {name: $name})
SET c.symptoms     = $symptoms,
    c.risk_factors = $risk_factors,
    c.signs        = $signs,
    c.seeded       = true
"""

_CREATE_SUBTYPE = """
MERGE (parent:Condition {name: $parent_name})
MERGE (child:Condition  {name: $child_name})
MERGE (parent)-[:HAS_SUBTYPE]->(child)
"""

_SYMPTOM_MATCH_QUERY = """
WITH $symptoms AS input_symptoms
MATCH (c:Condition)
WITH c, [s IN input_symptoms WHERE toLower(c.symptoms) CONTAINS toLower(s)] AS matched
WHERE size(matched) > 0
RETURN c.name AS condition, matched AS matched_symptoms, size(matched) AS score,
       c.symptoms AS symptom_description, c.risk_factors AS risk_factors
ORDER BY score DESC
LIMIT 10
"""

_DRUG_INTERACTION_QUERY = """
MATCH (d1:Drug)-[r:INTERACTS_WITH]->(d2:Drug)
WHERE d1.name IN $drug_names AND d2.name IN $drug_names
RETURN d1.name AS drug_a, d2.name AS drug_b,
       r.severity AS severity, r.mechanism AS mechanism
"""

_DRUG_CONTRAINDICATION_QUERY = """
MATCH (d:Drug)-[r:CONTRAINDICATED_IN]->(c:Condition)
WHERE d.name IN $drug_names AND c.name IN $conditions
RETURN d.name AS drug, c.name AS condition, r.reason AS reason
"""

_CONDITION_LOOKUP_QUERY = """
MATCH (c:Condition {name: $name})
OPTIONAL MATCH (c)-[:HAS_SUBTYPE]->(sub:Condition)
RETURN c.name AS name, c.symptoms AS symptoms,
       c.risk_factors AS risk_factors, c.signs AS signs,
       collect(sub.name) AS subtypes
"""

_CONDITION_EXISTS_QUERY = """
MATCH (c:Condition {name: $name, seeded: true})
RETURN count(c) AS n
"""


def _get_driver() -> Driver | None:
    global _driver, _driver_failed
    if _driver_failed or not settings.has_neo4j:
        return None
    if _driver is not None:
        return _driver
    try:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        _driver.verify_connectivity()
        log.info("[kg] Neo4j driver initialised")
        return _driver
    except Exception as exc:
        log.warning(f"[kg] Neo4j connection failed (will use local JSON): {exc}")
        _driver_failed = True
        return None


def _load_local() -> dict[str, dict]:
    global _LOCAL_CACHE
    if _LOCAL_CACHE:
        return _LOCAL_CACHE
    for path in _KG_DIR.glob("*.json"):
        try:
            _LOCAL_CACHE[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(f"[kg] Failed to load {path.name}: {exc}")
    log.info(f"[kg] Loaded {len(_LOCAL_CACHE)} conditions from local JSON")
    return _LOCAL_CACHE


def _seed_one(session, condition_name: str, payload: dict) -> None:
    """Seed a single condition + its subtypes into Neo4j (idempotent via MERGE)."""
    knowledge = payload.get("knowledge", {})
    suspected_key = next(iter(knowledge), None)
    suspected = knowledge.get(suspected_key, {}) if suspected_key else {}

    session.run(
        _CREATE_CONDITION,
        name=condition_name,
        symptoms=suspected.get("Symptoms", ""),
        risk_factors=suspected.get("Risk Factors", ""),
        signs=suspected.get("Signs", ""),
    )

    diagnostic = payload.get("diagnostic", {})
    for top_val in diagnostic.values():
        for parent, children in top_val.items():
            if isinstance(children, dict):
                for child in children:
                    session.run(_CREATE_SUBTYPE, parent_name=parent, child_name=child)


def _condition_already_seeded(session, name: str) -> bool:
    result = session.run(_CONDITION_EXISTS_QUERY, name=name).single()
    return bool(result and result["n"] > 0)


# On-demand seeding — seeds only what's needed, when it's needed
def seed_condition_on_demand(condition_name: str) -> bool:
    """
    Seed a single condition into Neo4j if it isn't there yet.
    Called lazily when a condition is first accessed.
    Returns True if seeded, False if already present or Neo4j unavailable.
    """
    driver = _get_driver()
    if not driver:
        return False

    kg = _load_local()
    # Fuzzy match to find the right JSON file
    name_lower = condition_name.lower()
    matched_key = next(
        (k for k in kg if name_lower in k.lower() or k.lower() in name_lower), None
    )
    if not matched_key:
        return False

    try:
        with driver.session() as session:
            if _condition_already_seeded(session, matched_key):
                return False
            _seed_one(session, matched_key, kg[matched_key])
            log.info(f"[kg] On-demand seeded: {matched_key}")
            return True
    except Exception as exc:
        log.warning(f"[kg] On-demand seed failed for {condition_name}: {exc}")
        return False


def seed_neo4j(force: bool = False) -> int:
    """
    Bulk import all local KG JSON files into Neo4j.
    Skips conditions already seeded unless force=True.
    Returns number of conditions newly seeded.
    """
    driver = _get_driver()
    if not driver:
        log.warning("[kg] Neo4j unavailable — skipping bulk seed")
        return 0

    data = _load_local()
    count = 0

    with driver.session() as session:
        for condition_name, payload in data.items():
            if not force and _condition_already_seeded(session, condition_name):
                continue
            _seed_one(session, condition_name, payload)
            count += 1

    log.info(f"[kg] Bulk seeded {count} condition(s) into Neo4j")
    return count


def search_by_symptoms(symptoms: list[str]) -> list[dict[str, Any]]:
    """Query Neo4j for conditions matching symptoms; fall back to local JSON."""
    driver = _get_driver()

    if driver:
        try:
            with driver.session() as session:
                results = session.run(_SYMPTOM_MATCH_QUERY, symptoms=symptoms).data()
            if results:
                return results
        except Exception as exc:
            log.warning(f"[kg] Neo4j symptom search failed: {exc} — using local fallback")

    # Local JSON fallback
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
    """Fetch a condition's knowledge block. Seeds the condition on-demand if Neo4j is available."""
    driver = _get_driver()

    if driver:
        # Seed on-demand if not yet in Neo4j
        seed_condition_on_demand(name)
        try:
            with driver.session() as session:
                result = session.run(_CONDITION_LOOKUP_QUERY, name=name).single()
            if result:
                return dict(result)
        except Exception as exc:
            log.warning(f"[kg] Neo4j condition lookup failed: {exc}")

    # Local JSON fallback
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


def query_drug_interactions(drug_names: list[str], conditions: list[str]) -> dict[str, Any]:
    """Query Neo4j for drug-drug interactions and contraindications. Returns empty if Neo4j unavailable."""
    driver = _get_driver()
    if not driver:
        return {"interactions": [], "contraindications": [], "source": "neo4j_unavailable"}

    try:
        with driver.session() as session:
            interactions = session.run(_DRUG_INTERACTION_QUERY, drug_names=drug_names).data()
            contraindications = session.run(
                _DRUG_CONTRAINDICATION_QUERY, drug_names=drug_names, conditions=conditions
            ).data()
        return {
            "interactions": interactions,
            "contraindications": contraindications,
            "source": "neo4j",
        }
    except Exception as exc:
        log.warning(f"[kg] Drug interaction query failed: {exc}")
        return {"interactions": [], "contraindications": [], "source": "error"}


def get_all_condition_names() -> list[str]:
    driver = _get_driver()
    if driver:
        try:
            with driver.session() as session:
                results = session.run("MATCH (c:Condition) RETURN c.name AS name ORDER BY name").data()
            if results:
                return [r["name"] for r in results]
        except Exception:
            pass
    return sorted(_load_local().keys())


def kg_status() -> dict[str, Any]:
    """Return current KG status — useful for the admin endpoint."""
    local_count = len(_load_local())
    driver = _get_driver()
    neo4j_count = 0
    neo4j_available = False

    if driver:
        try:
            with driver.session() as session:
                result = session.run("MATCH (c:Condition) RETURN count(c) AS n").single()
                neo4j_count = result["n"] if result else 0
            neo4j_available = True
        except Exception:
            pass

    return {
        "local_conditions": local_count,
        "neo4j_available": neo4j_available,
        "neo4j_conditions_seeded": neo4j_count,
        "unseeded": local_count - neo4j_count if neo4j_available else local_count,
    }
