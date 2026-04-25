from __future__ import annotations

import json
import logging

import httpx
from groq import Groq

from app.config import settings
from app.agent import kg_loader
from app.agent.tools import TOOL_MAP
from app.agent.drug_interaction_agent import run_drug_interaction_agent
from app.agent.diagnosis_agent import run_diagnosis_agent
from app.agent.sqlite_cache import get_node_cache, hash_payload, set_node_cache
from app.agent.summarizer import build_context, run_summarizer
from app.agent.diagnostics.prompts import _ORCHESTRATOR_PROMPT
from app.agent.diagnostics.state import AgentState
from app.models import ClinicalSummary

log = logging.getLogger(__name__)


# ── LLM helpers ──────────────────────────────────────────────────────────────

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
    race     = hints.get("race", "white")
    on_bp_tx = any(kw in m for m in meds for kw in
                   ["ramipril", "lisinopril", "amlodipine", "atenolol",
                    "metoprolol", "losartan", "perindopril", "bisoprolol"])
    is_smoker    = any(kw in s.get("summary_narrative", "").lower() for kw in ["smok", "tobacco", "cigarette"])
    has_diabetes = any("diabetes" in d or "type 2" in d for d in dx)

    if age and tc and hdl and sbp and sex in ("male", "female"):
        params["ascvd_risk_calculator"] = {
            "age": int(age), "total_cholesterol": tc, "hdl_cholesterol": hdl,
            "systolic_bp": sbp, "on_bp_treatment": on_bp_tx, "is_smoker": is_smoker,
            "has_diabetes": has_diabetes, "sex": sex, "race": race,
        }

    # Wells DVT
    narrative     = s.get("summary_narrative", "").lower()
    active_cancer = any("cancer" in d or "malignan" in d or "lymphoma" in d
                        or "leukaemia" in d or "leukemia" in d for d in dx)
    bedridden   = any(kw in narrative for kw in ["bedridden", "post-op", "post op", "surgical", "immobil"])
    leg_swollen = any(kw in narrative for kw in ["leg swollen", "ankle oedema", "ankle edema", "calf swelling"])
    prev_dvt    = any(kw in narrative for kw in ["previous dvt", "prior dvt", "history of dvt", "prior pe"])

    if any(kw in narrative for kw in ["dvt", "deep vein", "thrombosis", "pe ", "embolism", "emboli"]) or \
       any(kw in d for d in dx for kw in ["dvt", "thrombosis", "embolism", "pe"]):
        params["wells_dvt_score"] = hints.get("wells_dvt_score", {}) or {
            "active_cancer":                  active_cancer,
            "bedridden_3_days_or_surgery_12wk": bedridden,
            "entire_leg_swollen":             leg_swollen,
            "previous_dvt":                   prev_dvt,
            "alternative_diagnosis_as_likely": False,
        }

    # CHA₂DS₂-VASc
    has_af = any(kw in narrative or kw in d for d in dx for kw in ["atrial fibrillation", "af ", "afib"])
    if has_af and age:
        params["cha2ds2_vasc_score"] = hints.get("cha2ds2_vasc_score", {}) or {
            "congestive_heart_failure": any("heart failure" in d or "hfref" in d or "hfpef" in d for d in dx),
            "hypertension":             any("hypertension" in d for d in dx),
            "age_75_or_over":           int(age) >= 75,
            "diabetes":                 has_diabetes,
            "vascular_disease":         any(kw in d for d in dx for kw in
                                            ["coronary", "peripheral artery", "mi ", "myocardial"]),
            "age_65_to_74":             65 <= int(age) <= 74,
            "female_sex":               sex == "female",
        }

    return params


# ── Nodes ─────────────────────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> AgentState:
    log.info("[orchestrator] Starting")
    context    = build_context(state["patient_data"])
    structured = _extract_structured_params(state["patient_data"])

    llm_params:  dict = {}
    error_chain: list = []

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

    llm_calls    = {c["tool"]: c.get("params", {}) for c in llm_params.get("calculator_calls", [])}
    merged_calls = []
    for tool_name, struct_params in structured.items():
        llm_booleans = {k: v for k, v in llm_calls.get(tool_name, {}).items()
                        if isinstance(v, bool) and k not in struct_params}
        merged_calls.append({"tool": tool_name, "params": {**struct_params, **llm_booleans}})

    for tool_name, llm_p in llm_calls.items():
        if tool_name not in structured:
            merged_calls.append({"tool": tool_name, "params": llm_p})

    params = {
        "calculator_calls": merged_calls,
        "symptoms_for_kg":  llm_params.get("symptoms_for_kg", []),
        "routing_notes":    llm_params.get("routing_notes", ""),
    }

    audit_entry = (
        f"Orchestrator: {len(merged_calls)} calculator call(s) "
        f"({len(structured)} from structured data, {len(llm_calls)} from LLM). "
        f"{len(params['symptoms_for_kg'])} KG symptom(s)."
    )
    if error_chain:
        audit_entry += f" [provider errors: {'; '.join(error_chain)}]"

    return {"anonymized_notes": context, "extracted_params": params, "audit_log": [audit_entry]}


def drug_graph_node(state: AgentState) -> AgentState:
    """Queries KG and checks drug interactions."""
    log.info("[drug_graph_node] Running")
    s           = state["patient_data"].get("summary", {})
    medications = [m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in s.get("medications", [])]
    diagnoses   = [d.get("name", str(d)) if isinstance(d, dict) else str(d) for d in s.get("diagnoses", [])]
    symptoms    = state["extracted_params"].get("symptoms_for_kg", [])

    cache_key = hash_payload({"medications": medications, "diagnoses": diagnoses, "symptoms": symptoms})
    cached    = get_node_cache("drug_graph", cache_key)
    if cached:
        return {
            "interactions": cached.get("interactions", {}),
            "kg_matches":   cached.get("kg_matches", []),
            "audit_log":    [f"Drug/KG Node: loaded cached analysis for {len(medications)} drug(s)."],
        }

    kg_matches   = kg_loader.search_by_symptoms(symptoms) if symptoms else []
    interactions = run_drug_interaction_agent(medications, diagnoses, symptoms)
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


def diagnosis_node(state: AgentState) -> AgentState:
    """Runs after drug_graph_node so kg_matches are available."""
    log.info("[diagnosis_node] Running")
    enriched_context = state["anonymized_notes"]
    for match in state.get("kg_matches", [])[:3]:
        condition_data = kg_loader.get_condition(match["condition"])
        if condition_data:
            enriched_context += f"\n\nKG CONTEXT — {match['condition']}:\n{json.dumps(condition_data, indent=2)}"

    cache_key = hash_payload({"context": enriched_context, "patient_id": state["patient_id"]})
    cached    = get_node_cache("diagnosis", cache_key)
    if cached:
        return {"diagnoses": cached, "audit_log": ["Diagnosis Agent: loaded cached analysis."]}

    try:
        diagnoses = run_diagnosis_agent(enriched_context)
        primary   = diagnoses.get("primary_diagnosis", "unknown")
        count     = len(diagnoses.get("proposed_diagnoses", []))
        audit_entry = (
            f"Diagnosis Agent: proposed {count} diagnosis/diagnoses. "
            f"Primary: {primary}. KG-enriched context used."
        )
    except Exception as exc:
        baseline_dx = state["patient_data"].get("summary", {}).get("diagnoses", [])
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
        audit_entry = f"Diagnosis Agent: provider unavailable, used structured fallback — {exc}"

    set_node_cache("diagnosis", cache_key, diagnoses)
    return {"diagnoses": diagnoses, "audit_log": [audit_entry]}


def tool_node(state: AgentState) -> AgentState:
    """Runs clinical calculators from orchestrator-extracted parameters."""
    log.info("[tool_node] Running clinical calculators")
    calculator_calls = state["extracted_params"].get("calculator_calls", [])
    results = []

    for call in calculator_calls:
        tool_name = call.get("tool")
        tool_fn   = TOOL_MAP.get(tool_name)
        if tool_fn is None:
            results.append({"tool": tool_name, "error": "Tool not found"})
            continue
        try:
            results.append({"tool": tool_name, "result": tool_fn.invoke(call.get("params", {}))})
        except Exception as exc:
            results.append({"tool": tool_name, "error": str(exc)})

    tool_names  = [r["tool"] for r in results]
    audit_entry = f"Tool Node: ran {len(results)} calculator(s): {', '.join(tool_names) or 'none'}."
    return {"calculator_results": results, "audit_log": [audit_entry]}


def summarizer_node(state: AgentState) -> AgentState:
    """Final node — synthesizes all agent outputs into a ClinicalSummary."""
    log.info("[summarizer_node] Running")
    enriched_patient = dict(state["patient_data"])
    enriched_patient["agent_diagnoses"]    = state.get("diagnoses", {})
    enriched_patient["calculator_results"] = state.get("calculator_results", [])
    enriched_patient["drug_interactions"]  = state.get("interactions", {})

    try:
        summary     = run_summarizer(enriched_patient)
        audit_entry = (
            f"Summarizer: generated ClinicalSummary via {summary.model_used}. "
            f"Key concerns: {len(summary.key_concerns)}, "
            f"follow-up actions: {len(summary.follow_up_actions)}."
        )
    except Exception as exc:
        summary     = None
        audit_entry = f"Summarizer: failed — {exc}"

    return {"final_summary": summary, "audit_log": [audit_entry]}
