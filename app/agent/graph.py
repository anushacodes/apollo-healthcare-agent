from __future__ import annotations

import json
import logging
import operator
from typing import Annotated, Any, AsyncGenerator, TypedDict

import httpx
from langgraph.graph import StateGraph, END
from groq import Groq

from app.config import settings
from app.agent import kg_loader
from app.agent.tools import TOOL_MAP
from app.agent.drug_interaction_agent import run_drug_interaction_agent
from app.agent.diagnosis_agent import run_diagnosis_agent
from app.agent.sqlite_cache import get_node_cache, hash_payload, set_node_cache
from app.agent.summarizer import build_context, run_summarizer
from app.models import ClinicalSummary

log = logging.getLogger(__name__)


# Graph state
class AgentState(TypedDict):
    patient_id: str
    patient_data: dict               # full patient dict
    anonymized_notes: str            # flattened text for LLM consumption
    extracted_params: dict           # orchestrator output: calculator calls + symptoms
    calculator_results: list[dict]   # tool_node output
    diagnoses: dict                  # diagnosis_agent output
    interactions: dict               # drug_interaction_agent output
    kg_matches: list[dict]           # symptom→condition KG matches
    final_summary: ClinicalSummary | None
    audit_log: Annotated[list[str], operator.add]
    error: str | None


_ORCHESTRATOR_PROMPT = """\
You are a clinical orchestrator. Read the patient context and extract structured
parameters for clinical calculators. Only include a calculator call if you have
enough data to meaningfully populate it.

AVAILABLE CALCULATORS AND THEIR EXACT PARAMETER NAMES:

1. ascvd_risk_calculator — 10-year cardiovascular risk (ACC/AHA)
   Required: age (int), total_cholesterol (float, mg/dL), hdl_cholesterol (float, mg/dL),
             systolic_bp (float, mmHg), on_bp_treatment (bool), is_smoker (bool),
             has_diabetes (bool), sex ("male"/"female"), race ("white"/"african_american")

2. wells_dvt_score — Deep vein thrombosis probability
   All fields are boolean (true/false), default false if not mentioned:
   active_cancer, paralysis_or_immobilization, bedridden_3_days_or_surgery_12wk,
   localized_tenderness, entire_leg_swollen, calf_swelling_3cm_greater,
   pitting_oedema, collateral_superficial_veins, previous_dvt,
   alternative_diagnosis_as_likely

3. cha2ds2_vasc_score — Stroke risk in atrial fibrillation
   All fields are boolean, default false if not mentioned:
   congestive_heart_failure, hypertension, age_75_or_over, diabetes,
   stroke_or_tia_history, vascular_disease, age_65_to_74, female_sex

Return ONLY valid JSON:
{
  "calculator_calls": [
    {
      "tool": "<exact tool name from above>",
      "params": { "<exact param name>": <value>, ... }
    }
  ],
  "symptoms_for_kg": ["<symptom 1>", "<symptom 2>", ...],
  "routing_notes": "<brief note on which agents to prioritise>"
}

Rules:
- Use EXACT parameter names as listed above (e.g. "active_cancer" not "malignancy").
- Omit boolean params you cannot determine — they default to false safely.
- Only call a calculator if the patient's clinical picture makes it relevant.
- Extract up to 6 key symptoms for the knowledge graph.
"""


def _call_groq_json(system: str, user: str, max_tokens: int = 1024) -> dict:
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _call_openrouter_json(system: str, user: str) -> dict:
    """OpenRouter (free tier) — fallback for orchestrator only."""
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openrouter_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


# Nodes — run sequentially: orchestrator → drug_graph → diagnosis → tool_node → summarizer
# This order ensures kg_matches (from drug_graph) are available to diagnosis_node.

def _lab_val(labs: list[dict], *names: str) -> float | None:
    """Pull a numeric lab value by test_name (case-insensitive)."""
    for lab in labs:
        if lab.get("test_name", "").lower() in {n.lower() for n in names}:
            try:
                return float(str(lab.get("value", "")).replace(",", "").split()[0])
            except (ValueError, IndexError):
                continue
    return None


def _extract_structured_params(patient_data: dict) -> dict:
    """
    Pre-populate calculator params directly from structured patient data.
    This bypasses the LLM for numeric/demographic fields that are already
    machine-readable — e.g. age, labs, medication flags.
    Returns a dict keyed by tool name → partial params dict.
    """
    p   = patient_data.get("patient", {})
    s   = patient_data.get("summary", {})
    labs = s.get("lab_results", [])
    dx   = [d.get("name", "").lower() if isinstance(d, dict) else str(d).lower()
            for d in s.get("diagnoses", [])]
    meds = [m.get("name", "").lower() if isinstance(m, dict) else str(m).lower()
            for m in s.get("medications", [])]

    # Override with explicit hints authored in the seed data
    hints = patient_data.get("calculator_hints", {})

    age = p.get("age") or hints.get("age")
    sex = (p.get("sex") or hints.get("sex") or "unknown").lower()
    sex = "male" if sex.startswith("m") else "female" if sex.startswith("f") else sex

    params: dict[str, dict] = {}

    # ── ASCVD ──────────────────────────────────────────────────────────────
    tc  = hints.get("total_cholesterol") or _lab_val(labs, "total cholesterol", "cholesterol total", "tc")
    hdl = hints.get("hdl_cholesterol")   or _lab_val(labs, "hdl", "hdl cholesterol", "hdl-c")
    sbp = hints.get("systolic_bp")       or _lab_val(labs, "systolic bp", "sbp", "systolic blood pressure")
    race = hints.get("race", "white")

    on_bp_tx = any(kw in m for m in meds for kw in ["ramipril", "lisinopril", "amlodipine",
                   "atenolol", "metoprolol", "losartan", "perindopril", "bisoprolol"])
    is_smoker   = any(kw in s.get("summary_narrative", "").lower() for kw in ["smok", "tobacco", "cigarette"])
    has_diabetes = any("diabetes" in d or "type 2" in d for d in dx)

    if age and tc and hdl and sbp and sex in ("male", "female"):
        params["ascvd_risk_calculator"] = {
            "age": int(age), "total_cholesterol": tc, "hdl_cholesterol": hdl,
            "systolic_bp": sbp, "on_bp_treatment": on_bp_tx, "is_smoker": is_smoker,
            "has_diabetes": has_diabetes, "sex": sex, "race": race,
        }

    # ── Wells DVT ──────────────────────────────────────────────────────────
    narrative = s.get("summary_narrative", "").lower()
    active_cancer = any("cancer" in d or "malignan" in d or "lymphoma" in d or "leukaemia" in d or "leukemia" in d
                        for d in dx)
    bedridden = any(kw in narrative for kw in ["bedridden", "post-op", "post op", "surgical", "immobil"])
    leg_swollen = any(kw in narrative for kw in ["leg swollen", "ankle oedema", "ankle edema", "calf swelling"])
    prev_dvt = any(kw in narrative for kw in ["previous dvt", "prior dvt", "history of dvt", "prior pe"])
    alt_dx_likely = False  # conservative default

    # Only include Wells if there's a clinical reason (PE/DVT in dx or narrative)
    if any(kw in narrative for kw in ["dvt", "deep vein", "thrombosis", "pe ", "embolism", "emboli"]) or \
       any(kw in d for d in dx for kw in ["dvt", "thrombosis", "embolism", "pe"]):
        params["wells_dvt_score"] = hints.get("wells_dvt_score", {}) or {
            "active_cancer": active_cancer,
            "bedridden_3_days_or_surgery_12wk": bedridden,
            "entire_leg_swollen": leg_swollen,
            "previous_dvt": prev_dvt,
            "alternative_diagnosis_as_likely": alt_dx_likely,
        }

    # ── CHA₂DS₂-VASc ───────────────────────────────────────────────────────
    has_af = any(kw in narrative or kw in d for d in dx for kw in ["atrial fibrillation", "af ", "afib"])
    if has_af and age:
        params["cha2ds2_vasc_score"] = hints.get("cha2ds2_vasc_score", {}) or {
            "congestive_heart_failure": any("heart failure" in d or "hfref" in d or "hfpef" in d for d in dx),
            "hypertension": any("hypertension" in d for d in dx),
            "age_75_or_over": int(age) >= 75,
            "diabetes": has_diabetes,
            "vascular_disease": any(kw in d for d in dx for kw in ["coronary", "peripheral artery", "mi ", "myocardial"]),
            "age_65_to_74": 65 <= int(age) <= 74,
            "female_sex": sex == "female",
        }

    return params


def orchestrator_node(state: AgentState) -> AgentState:
    log.info("[orchestrator] Starting")
    context = build_context(state["patient_data"])

    # Step 1: structured extraction from patient JSON (reliable, no LLM)
    structured = _extract_structured_params(state["patient_data"])

    # Step 2: LLM fills in clinical booleans and symptoms
    llm_params: dict = {}
    error_chain = []

    if settings.has_groq:
        try:
            llm_params = _call_groq_json(_ORCHESTRATOR_PROMPT, context)
        except Exception as exc:
            error_chain.append(f"Groq: {exc}")

    if not llm_params and settings.has_openrouter:
        try:
            llm_params = _call_openrouter_json(_ORCHESTRATOR_PROMPT, context)
        except Exception as exc:
            error_chain.append(f"OpenRouter: {exc}")

    # Step 3: merge — structured data wins over LLM guesses for numeric fields
    # Inject structured calculator calls, LLM booleans fill gaps
    llm_calls = {c["tool"]: c.get("params", {}) for c in llm_params.get("calculator_calls", [])}
    merged_calls = []
    for tool_name, struct_params in structured.items():
        llm_booleans = {k: v for k, v in llm_calls.get(tool_name, {}).items()
                        if isinstance(v, bool) and k not in struct_params}
        merged_calls.append({"tool": tool_name, "params": {**struct_params, **llm_booleans}})

    # Add any LLM-only tools not covered by structured extraction
    for tool_name, llm_p in llm_calls.items():
        if tool_name not in structured:
            merged_calls.append({"tool": tool_name, "params": llm_p})

    params = {
        "calculator_calls": merged_calls,
        "symptoms_for_kg": llm_params.get("symptoms_for_kg", []),
        "routing_notes": llm_params.get("routing_notes", ""),
    }

    audit_entry = (
        f"Orchestrator: {len(merged_calls)} calculator call(s) "
        f"({len(structured)} from structured data, {len(llm_calls)} from LLM). "
        f"{len(params['symptoms_for_kg'])} KG symptom(s)."
    )
    if error_chain:
        audit_entry += f" [provider errors: {'; '.join(error_chain)}]"

    return {
        "anonymized_notes": context,
        "extracted_params": params,
        "audit_log": [audit_entry],
    }



def drug_graph_node(state: AgentState) -> AgentState:
    """Runs after orchestrator. Queries KG and drug interactions."""
    log.info("[drug_graph_node] Running drug interaction + KG queries")
    s = state["patient_data"].get("summary", {})
    medications = [m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in s.get("medications", [])]
    diagnoses = [d.get("name", str(d)) if isinstance(d, dict) else str(d) for d in s.get("diagnoses", [])]
    symptoms = state["extracted_params"].get("symptoms_for_kg", [])

    cache_key = hash_payload(
        {
            "medications": medications,
            "diagnoses": diagnoses,
            "symptoms": symptoms,
        }
    )
    cached = get_node_cache("drug_graph", cache_key)
    if cached:
        kg_matches = cached.get("kg_matches", [])
        interactions = cached.get("interactions", {})
        audit_entry = (
            f"Drug/KG Node: loaded cached interaction analysis for {len(medications)} drug(s) "
            f"and {len(diagnoses)} diagnosis/diagnoses."
        )
        return {
            "interactions": interactions,
            "kg_matches": kg_matches,
            "audit_log": [audit_entry],
        }

    kg_matches = kg_loader.search_by_symptoms(symptoms) if symptoms else []
    interactions = run_drug_interaction_agent(medications, diagnoses, symptoms)
    set_node_cache(
        "drug_graph",
        cache_key,
        {"kg_matches": kg_matches, "interactions": interactions},
    )

    audit_entry = (
        f"Drug/KG Node: Checked {len(medications)} drug(s) against {len(diagnoses)} diagnose(s). "
        f"KG matched {len(kg_matches)} condition(s). "
        f"Interaction risk: {interactions.get('overall_risk', 'unknown')}."
    )

    return {
        "interactions": interactions,
        "kg_matches": kg_matches,
        "audit_log": [audit_entry],
    }


def diagnosis_node(state: AgentState) -> AgentState:
    """Runs after drug_graph_node so kg_matches are available."""
    log.info("[diagnosis_node] Running diagnosis agent (Gemini 1.5 Flash)")

    # Enrich context with KG knowledge for top matched conditions
    enriched_context = state["anonymized_notes"]
    for match in state.get("kg_matches", [])[:3]:
        condition_data = kg_loader.get_condition(match["condition"])
        if condition_data:
            enriched_context += f"\n\nKG CONTEXT — {match['condition']}:\n{json.dumps(condition_data, indent=2)}"

    cache_key = hash_payload(
        {
            "context": enriched_context,
            "patient_id": state["patient_id"],
        }
    )
    cached = get_node_cache("diagnosis", cache_key)
    if cached:
        audit_entry = "Diagnosis Agent: loaded cached diagnosis analysis."
        return {
            "diagnoses": cached,
            "audit_log": [audit_entry],
        }

    try:
        diagnoses = run_diagnosis_agent(enriched_context)
        primary = diagnoses.get("primary_diagnosis", "unknown")
        count = len(diagnoses.get("proposed_diagnoses", []))
        audit_entry = (
            f"Diagnosis Agent: Proposed {count} diagnosis/diagnoses. "
            f"Primary: {primary}. KG-enriched context used."
        )
    except Exception as exc:
        baseline_dx = state["patient_data"].get("summary", {}).get("diagnoses", [])
        diagnoses = {
            "error": str(exc),
            "proposed_diagnoses": [
                {
                    "name": d.get("name", str(d)) if isinstance(d, dict) else str(d),
                    "icd_code": d.get("icd_code") if isinstance(d, dict) else None,
                    "confidence": "moderate",
                    "supporting_evidence": ["Derived from structured patient record."],
                    "reasoning": "Fallback path used because diagnosis LLM was unavailable.",
                }
                for d in baseline_dx[:5]
            ],
            "primary_diagnosis": (
                baseline_dx[0].get("name", "unknown")
                if baseline_dx and isinstance(baseline_dx[0], dict)
                else str(baseline_dx[0]) if baseline_dx else "unknown"
            ),
            "differential_notes": "Fallback from structured diagnoses because the diagnosis model was unavailable.",
            "recommended_investigations": [],
        }
        audit_entry = f"Diagnosis Agent: provider unavailable, used structured fallback — {exc}"

    set_node_cache("diagnosis", cache_key, diagnoses)

    return {
        "diagnoses": diagnoses,
        "audit_log": [audit_entry],
    }


def tool_node(state: AgentState) -> AgentState:
    """Runs clinical calculators from orchestrator-extracted parameters."""
    log.info("[tool_node] Running clinical calculators")
    calculator_calls = state["extracted_params"].get("calculator_calls", [])
    results = []

    for call in calculator_calls:
        tool_name = call.get("tool")
        tool_params = call.get("params", {})
        tool_fn = TOOL_MAP.get(tool_name)

        if tool_fn is None:
            results.append({"tool": tool_name, "error": "Tool not found"})
            continue

        try:
            result = tool_fn.invoke(tool_params)
            results.append({"tool": tool_name, "result": result})
        except Exception as exc:
            results.append({"tool": tool_name, "error": str(exc)})

    tool_names = [r["tool"] for r in results]
    audit_entry = f"Tool Node: Ran {len(results)} calculator(s): {', '.join(tool_names) or 'none'}."

    return {
        "calculator_results": results,
        "audit_log": [audit_entry],
    }


def summarizer_node(state: AgentState) -> AgentState:
    """Final node — synthesizes all agent outputs into a ClinicalSummary."""
    log.info("[summarizer_node] Running summarizer (Groq)")

    enriched_patient = dict(state["patient_data"])
    enriched_patient["agent_diagnoses"] = state.get("diagnoses", {})
    enriched_patient["calculator_results"] = state.get("calculator_results", [])
    enriched_patient["drug_interactions"] = state.get("interactions", {})

    try:
        summary = run_summarizer(enriched_patient)
        audit_entry = (
            f"Summarizer: Generated ClinicalSummary via {summary.model_used}. "
            f"Key concerns: {len(summary.key_concerns)}, follow-up actions: {len(summary.follow_up_actions)}."
        )
    except Exception as exc:
        summary = None
        audit_entry = f"Summarizer: Failed — {exc}"

    return {
        "final_summary": summary,
        "audit_log": [audit_entry],
    }


def _build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("drug_graph", drug_graph_node)
    workflow.add_node("diagnosis", diagnosis_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_node("summarizer", summarizer_node)

    workflow.set_entry_point("orchestrator")

    # Fan-out after orchestrator: drug_graph and tool_node run in parallel.
    # drug_graph must finish before diagnosis (needs kg_matches).
    # summarizer fans in from both diagnosis and tool_node.
    workflow.add_edge("orchestrator", "drug_graph")
    workflow.add_edge("orchestrator", "tool_node")
    workflow.add_edge("drug_graph", "diagnosis")
    workflow.add_edge("diagnosis", "summarizer")
    workflow.add_edge("tool_node", "summarizer")
    workflow.add_edge("summarizer", END)

    return workflow.compile()


graph = _build_graph()


async def run_graph_streaming(patient_data: dict) -> AsyncGenerator[dict, None]:
    """Run the full agent graph, yielding a state update after every node."""
    patient_id = patient_data.get("patient_id", "unknown")
    initial_state: AgentState = {
        "patient_id": patient_id,
        "patient_data": patient_data,
        "anonymized_notes": "",
        "extracted_params": {},
        "calculator_results": [],
        "diagnoses": {},
        "interactions": {},
        "kg_matches": [],
        "final_summary": None,
        "audit_log": [],
        "error": None,
    }

    async for event in graph.astream(initial_state):
        for node_name, node_state in event.items():
            audit_log = node_state.get("audit_log", [])
            latest_entry = audit_log[-1] if audit_log else ""

            payload: dict[str, Any] = {
                "node": node_name,
                "audit_entry": latest_entry,
                "audit_log": audit_log,
            }

            if node_name == "orchestrator":
                payload["extracted_params"] = node_state.get("extracted_params", {})
            elif node_name == "drug_graph":
                payload["interactions"] = node_state.get("interactions", {})
                payload["kg_matches"] = node_state.get("kg_matches", [])
            elif node_name == "diagnosis":
                payload["diagnoses"] = node_state.get("diagnoses", {})
            elif node_name == "tool_node":
                payload["calculator_results"] = node_state.get("calculator_results", [])
            elif node_name == "summarizer":
                summary = node_state.get("final_summary")
                payload["final_summary"] = summary.model_dump(mode="json") if summary else None

            yield payload
