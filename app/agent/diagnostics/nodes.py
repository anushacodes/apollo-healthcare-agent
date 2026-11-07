import json
import logging

import httpx
from pydantic import ValidationError

from app.agent import kg_loader
from app.agent.contracts import CalculatorCall, OrchestratorPlan
from app.agent.diagnosis_agent import run_diagnosis_agent
from app.agent.diagnostics.prompts import _ORCHESTRATOR_PROMPT
from app.agent.diagnostics.state import AgentState
from app.agent.drug_interaction_agent import run_drug_interaction_agent
from app.agent.sqlite_cache import get_node_cache, hash_payload, set_node_cache
from app.agent.summarizer import build_context, run_summarizer
from app.config import settings
from app.llm_client import call_llm_json, get_structured_groq_client
from app.review.calculators import execute_call

log = logging.getLogger(__name__)


# ── LLM helpers ──────────────────────────────────────────────────────────────

def _call_orchestrator_llm(context: str) -> OrchestratorPlan:
    messages = [{"role": "system", "content": _ORCHESTRATOR_PROMPT}, {"role": "user", "content": context}]

    if settings.active_llm_provider == "openrouter" and settings.has_openrouter:
        try:
            raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
            return OrchestratorPlan.model_validate(raw_dict)
        except Exception as exc:
            log.warning("[orchestrator] OpenRouter call failed: %s", exc)

    if settings.has_groq:
        try:
            client = get_structured_groq_client()
            return client.chat.completions.create(
                model=settings.groq_model,
                response_model=OrchestratorPlan,
                messages=messages,
                temperature=0.1,
                max_tokens=4096,
                reasoning_effort="low",
            )
        except Exception as exc:
            log.warning("[orchestrator] Groq tool call failed, trying JSON: %s", exc)
            raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
            return OrchestratorPlan.model_validate(raw_dict)

    if settings.has_openrouter:
        raw_dict, _ = call_llm_json(messages, temperature=0.1, max_tokens=4096)
        return OrchestratorPlan.model_validate(raw_dict)

    raise RuntimeError("No LLM provider available for orchestrator")


def _call_openrouter_json(system: str, user: str) -> dict:
    """OpenRouter fallback for orchestrator."""
    raw_dict, _ = call_llm_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        max_tokens=4096,
    )
    return raw_dict


# ── Structured extraction ─────────────────────────────────────────────────────

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
    Bypasses the LLM for numeric/demographic fields that are already machine-readable.
    Returns a dict keyed by tool name → partial params dict.
    """
    p    = patient_data.get("patient", {})
    s    = patient_data.get("summary", {})
    labs  = s.get("lab_results", [])
    dx    = [d.get("name", "").lower() if isinstance(d, dict) else str(d).lower()
             for d in s.get("diagnoses", [])]
    meds  = [m.get("name", "").lower() if isinstance(m, dict) else str(m).lower()
             for m in s.get("medications", [])]
    hints = patient_data.get("calculator_hints", {})

    age = p.get("age") or hints.get("age")
    sex = (p.get("sex") or hints.get("sex") or "unknown").lower()
    sex = "male" if sex.startswith("m") else "female" if sex.startswith("f") else sex

    params: dict[str, dict] = {}

    # ASCVD
    tc  = hints.get("total_cholesterol") or _lab_val(labs, "total cholesterol", "cholesterol total", "tc")
    hdl = hints.get("hdl_cholesterol")   or _lab_val(labs, "hdl", "hdl cholesterol", "hdl-c")
    sbp = hints.get("systolic_bp")       or _lab_val(labs, "systolic bp", "sbp", "systolic blood pressure")
    on_bp_tx = any(kw in m for m in meds for kw in
                   ["ramipril", "lisinopril", "amlodipine", "atenolol",
                    "metoprolol", "losartan", "perindopril", "bisoprolol"])
    # Absence of a mention is not a negative finding. Ask for unrecorded criteria.
    is_smoker = hints.get("is_smoker")
    has_diabetes = hints.get("has_diabetes")
    if has_diabetes is None and any(
        isinstance(d, dict) and ("diabetes" in d.get("name", "").lower()) and
        not any(word in d.get("status", "").lower() for word in ("ruled out", "resolved", "suspected"))
        for d in s.get("diagnoses", [])
    ):
        has_diabetes = True
    on_bp_tx = hints.get("on_bp_treatment", True if on_bp_tx else None)

    if tc or hdl or sbp:
        values = {
            "age": int(age) if age else None, "total_cholesterol": tc, "hdl_cholesterol": hdl,
            "systolic_bp": sbp, "on_bp_treatment": on_bp_tx, "is_smoker": is_smoker,
            "has_diabetes": has_diabetes, "sex": sex if sex in ("male", "female") else None,
            "race": hints.get("race"),
        }
        params["ascvd_risk_calculator"] = {k: v for k, v in values.items() if v is not None}

    # Only explicit criterion values are safe to use for these calculators.
    narrative = s.get("summary_narrative", "").lower()
    if hints.get("wells_dvt_score") is not None or any(
        kw in narrative for kw in ("dvt", "deep vein", "thrombosis", "embolism", "emboli")
    ):
        params["wells_dvt_score"] = hints.get("wells_dvt_score", {})
    if hints.get("cha2ds2_vasc_score") is not None or any(
        "atrial fibrillation" in d or "afib" in d for d in dx
    ):
        params["cha2ds2_vasc_score"] = hints.get("cha2ds2_vasc_score", {})

    return params


# ── Nodes ─────────────────────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> dict:
    log.info("[orchestrator] Starting")
    context    = build_context(state.patient_data)
    structured = _extract_structured_params(state.patient_data)

    plan: OrchestratorPlan = OrchestratorPlan()
    error_chain: list[str] = []

    if settings.has_groq:
        try:
            plan = _call_orchestrator_llm(context)
        except Exception as exc:
            error_chain.append(f"Groq: {exc}")

    if not plan.calculator_calls and not plan.symptoms_for_kg and settings.has_openrouter:
        try:
            raw = _call_openrouter_json(_ORCHESTRATOR_PROMPT, context)
            plan = OrchestratorPlan.model_validate(raw)
        except (httpx.HTTPError, ValidationError, json.JSONDecodeError) as exc:
            error_chain.append(f"OpenRouter: {exc}")

    llm_calls: dict[str, dict] = {c.tool: c.params for c in plan.calculator_calls}
    merged_calls: list[CalculatorCall] = []
    for tool_name, struct_params in structured.items():
        llm_booleans = {k: v for k, v in llm_calls.get(tool_name, {}).items()
                        if isinstance(v, bool) and k not in struct_params}
        merged_calls.append(CalculatorCall(tool=tool_name, params={**struct_params, **llm_booleans}))

    for tool_name, llm_p in llm_calls.items():
        if tool_name not in structured:
            merged_calls.append(CalculatorCall(tool=tool_name, params=llm_p))

    params = {
        "calculator_calls": [c.model_dump() for c in merged_calls],
        "symptoms_for_kg":  plan.symptoms_for_kg,
        "routing_notes":    plan.routing_notes,
    }

    audit_entry = (
        f"Orchestrator: {len(merged_calls)} calculator call(s) "
        f"({len(structured)} from structured data, {len(llm_calls)} from LLM). "
        f"{len(params['symptoms_for_kg'])} KG symptom(s)."
    )
    if error_chain:
        log.warning("[orchestrator] LLM provider errors: %s", "; ".join(error_chain))
        audit_entry += " [one or more providers were unavailable, used structured data only]"

    return {"anonymized_notes": context, "extracted_params": params, "audit_log": [audit_entry]}


def drug_graph_node(state: AgentState) -> dict:
    """Queries KG and checks drug interactions."""
    log.info("[drug_graph_node] Running")
    s           = state.patient_data.get("summary", {})
    medications = [m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in s.get("medications", [])]
    diagnoses   = [d.get("name", str(d)) if isinstance(d, dict) else str(d) for d in s.get("diagnoses", [])]
    symptoms    = state.extracted_params.get("symptoms_for_kg", [])

    cache_key = hash_payload({"medications": medications, "diagnoses": diagnoses, "symptoms": symptoms})
    cached    = get_node_cache("drug_graph", cache_key)
    if cached:
        return {
            "interactions": cached.get("interactions", {}),
            "kg_matches":   cached.get("kg_matches", []),
            "audit_log":    [f"Drug/KG Node: loaded cached analysis for {len(medications)} drug(s)."],
        }

    kg_matches = kg_loader.search_by_symptoms(symptoms) if symptoms else []
    interactions, succeeded = run_drug_interaction_agent(medications, diagnoses, symptoms)
    if succeeded:
        set_node_cache("drug_graph", cache_key, {"kg_matches": kg_matches, "interactions": interactions})

    return {
        "interactions": interactions,
        "kg_matches":   kg_matches,
        "audit_log":    [
            f"Drug/KG Node: checked {len(medications)} drug(s) against {len(diagnoses)} diagnosis/diagnoses. "
            f"KG matched {len(kg_matches)} condition(s). "
            f"Interaction risk: {interactions.get('overall_risk', 'unknown')}."
        ],
    }


def diagnosis_node(state: AgentState) -> dict:
    """Runs after drug_graph_node so kg_matches are available."""
    log.info("[diagnosis_node] Running")
    enriched_context = state.anonymized_notes
    if state.calculator_results:
        enriched_context += "\n\nCALCULATOR RESULTS:\n" + json.dumps(state.calculator_results)
    for match in state.kg_matches[:3]:
        condition_data = kg_loader.get_condition(match["condition"])
        if condition_data:
            enriched_context += f"\n\nKG CONTEXT — {match['condition']}:\n{json.dumps(condition_data, indent=2)}"

    cache_key = hash_payload({"context": enriched_context, "patient_id": state.patient_id})
    cached    = get_node_cache("diagnosis", cache_key)
    if cached:
        return {"diagnoses": cached, "audit_log": ["Diagnosis Agent: loaded cached analysis."]}

    used_fallback = False
    try:
        diagnoses = run_diagnosis_agent(enriched_context)
        primary   = diagnoses.get("primary_diagnosis", "unknown")
        count     = len(diagnoses.get("proposed_diagnoses", []))
        audit_entry = (
            f"Diagnosis Agent: proposed {count} diagnosis/diagnoses. "
            f"Primary: {primary}. KG-enriched context used."
        )
    except Exception as exc:
        used_fallback = True
        baseline_dx = state.patient_data.get("summary", {}).get("diagnoses", [])
        diagnoses = {
            "error": str(exc),
            "proposed_diagnoses": [
                {
                    "name":                 d.get("name", str(d)) if isinstance(d, dict) else str(d),
                    "icd_code":             d.get("icd_code") if isinstance(d, dict) else None,
                    "confidence":           "moderate",
                    "supporting_evidence":  ["Derived from structured patient record."],
                    "reasoning":            "Fallback path used because diagnosis LLM was unavailable.",
                }
                for d in baseline_dx[:5]
            ],
            "primary_diagnosis": (
                baseline_dx[0].get("name", "unknown")
                if baseline_dx and isinstance(baseline_dx[0], dict)
                else str(baseline_dx[0]) if baseline_dx else "unknown"
            ),
            "differential_notes":         "Fallback from structured diagnoses — diagnosis model unavailable.",
            "recommended_investigations": [],
        }
        log.warning("[diagnosis_node] LLM provider failed, using fallback: %s", exc)
        audit_entry = "Diagnosis Agent: provider unavailable, used structured fallback."

    if not used_fallback:
        set_node_cache("diagnosis", cache_key, diagnoses)
    return {"diagnoses": diagnoses, "audit_log": [audit_entry]}


def tool_node(state: AgentState) -> dict:
    """Runs clinical calculators from orchestrator-extracted parameters."""
    log.info("[tool_node] Running clinical calculators")
    calculator_calls = state.extracted_params.get("calculator_calls", [])
    results = []

    for call in calculator_calls:
        results.append(execute_call(call.get("tool", ""), call.get("params", {})))

    tool_names  = [r["tool"] for r in results]
    audit_entry = f"Tool Node: ran {len(results)} calculator(s): {', '.join(tool_names) or 'none'}."
    return {"calculator_results": results, "audit_log": [audit_entry]}


def summarizer_node(state: AgentState) -> dict:
    """Final node — synthesizes all agent outputs into a ClinicalSummary."""
    log.info("[summarizer_node] Running")
    enriched_patient = dict(state.patient_data)
    enriched_patient["agent_diagnoses"]    = state.diagnoses
    enriched_patient["calculator_results"] = state.calculator_results
    enriched_patient["drug_interactions"]  = state.interactions

    try:
        summary     = run_summarizer(enriched_patient)
        audit_entry = (
            f"Summarizer: generated ClinicalSummary via {summary.model_used}. "
            f"Key concerns: {len(summary.key_concerns)}, "
            f"follow-up actions: {len(summary.follow_up_actions)}."
        )
    except Exception as exc:
        log.warning("[summarizer_node] Summary generation failed: %s", exc)
        summary     = None
        audit_entry = "Summarizer: failed to generate a summary."

    return {"final_summary": summary, "audit_log": [audit_entry]}
