from __future__ import annotations

import math
from typing import Any

from langchain_core.tools import tool

@tool
def ascvd_risk_calculator(
    age: int,
    total_cholesterol: float,
    hdl_cholesterol: float,
    systolic_bp: float,
    on_bp_treatment: bool,
    is_smoker: bool,
    has_diabetes: bool,
    sex: str,
    race: str,
) -> dict[str, Any]:
    """
    Calculate 10-year ASCVD (Atherosclerotic Cardiovascular Disease) risk
    using the Pooled Cohort Equations (ACC/AHA 2013 guidelines).

    Returns a risk score percentage and risk category.
    sex: 'male' or 'female'
    race: 'white' or 'african_american'
    """
    # Coefficients from ACC/AHA Pooled Cohort Equations
    coefficients = {
        ("white", "male"): {
            "ln_age": 12.344, "ln_total_chol": 11.853, "ln_age_total_chol": -2.664,
            "ln_hdl": -7.990, "ln_age_hdl": 1.769, "ln_sbp_treated": 1.797,
            "ln_sbp_untreated": 1.764, "smoker": 7.837, "ln_age_smoker": -1.795,
            "diabetes": 0.658, "baseline_survival": 0.9144, "mean_coeff_val": 61.18,
        },
        ("white", "female"): {
            "ln_age": -7.574, "ln_total_chol": 17.1141, "ln_age_total_chol": -0.940,
            "ln_hdl": -18.920, "ln_age_hdl": 4.475, "ln_sbp_treated": 29.291,
            "ln_sbp_untreated": 27.819, "ln_age_sbp": -6.087, "smoker": 13.540,
            "ln_age_smoker": -3.114, "diabetes": 0.661,
            "baseline_survival": 0.9665, "mean_coeff_val": -29.799,
        },
        ("african_american", "male"): {
            "ln_age": 2.469, "ln_total_chol": 0.302, "ln_hdl": -0.307,
            "ln_sbp_treated": 1.916, "ln_sbp_untreated": 1.809, "smoker": 0.549,
            "diabetes": 0.645, "baseline_survival": 0.8954, "mean_coeff_val": 19.54,
        },
        ("african_american", "female"): {
            "ln_age": 17.1141, "ln_total_chol": 0.940, "ln_hdl": -18.920,
            "ln_age_hdl": 4.475, "ln_sbp_treated": 29.291,
            "ln_sbp_untreated": 27.819, "ln_age_sbp": -6.087, "smoker": 0.691,
            "diabetes": 0.874, "baseline_survival": 0.9533, "mean_coeff_val": 86.61,
        },
    }

    key = (race.lower(), sex.lower())
    if key not in coefficients:
        return {"error": f"Unsupported sex/race combination: {sex}/{race}"}

    c = coefficients[key]
    ln_age = math.log(age)
    ln_tc = math.log(total_cholesterol)
    ln_hdl = math.log(hdl_cholesterol)
    ln_sbp = math.log(systolic_bp)

    # Compute individual sum (simplified using common terms)
    s = (
        c.get("ln_age", 0) * ln_age
        + c.get("ln_total_chol", 0) * ln_tc
        + c.get("ln_age_total_chol", 0) * (ln_age * ln_tc)
        + c.get("ln_hdl", 0) * ln_hdl
        + c.get("ln_age_hdl", 0) * (ln_age * ln_hdl)
        + (c.get("ln_sbp_treated", 0) * ln_sbp if on_bp_treatment else c.get("ln_sbp_untreated", 0) * ln_sbp)
        + c.get("ln_age_sbp", 0) * (ln_age * ln_sbp) * (1 if not on_bp_treatment else 0)
        + c.get("smoker", 0) * (1 if is_smoker else 0)
        + c.get("ln_age_smoker", 0) * (ln_age * (1 if is_smoker else 0))
        + c.get("diabetes", 0) * (1 if has_diabetes else 0)
    )

    risk_pct = (1 - c["baseline_survival"] ** math.exp(s - c["mean_coeff_val"])) * 100
    risk_pct = round(max(0, min(100, risk_pct)), 1)

    if risk_pct < 5:
        category = "Low"
    elif risk_pct < 7.5:
        category = "Borderline"
    elif risk_pct < 20:
        category = "Intermediate"
    else:
        category = "High"

    return {
        "tool": "ASCVD Risk Calculator (ACC/AHA Pooled Cohort Equations)",
        "10_year_risk_pct": risk_pct,
        "risk_category": category,
        "recommendation": (
            "Statin therapy discussion recommended." if risk_pct >= 7.5
            else "Lifestyle modification focus; re-evaluate in 4-6 years."
        ),
    }


@tool
def wells_dvt_score(
    active_cancer: bool = False,
    paralysis_or_immobilization: bool = False,
    bedridden_3_days_or_surgery_12wk: bool = False,
    localized_tenderness: bool = False,
    entire_leg_swollen: bool = False,
    calf_swelling_3cm_greater: bool = False,
    pitting_oedema: bool = False,
    collateral_superficial_veins: bool = False,
    previous_dvt: bool = False,
    alternative_diagnosis_as_likely: bool = False,
) -> dict[str, Any]:
    """
    Calculate the Wells Score for Deep Vein Thrombosis (DVT) probability.
    Returns a score and probability category.

    Each boolean criterion adds 1 point (alternative_diagnosis subtracts 2).
    All fields default to False (criterion absent).
    """
    score = sum([
        active_cancer,
        paralysis_or_immobilization,
        bedridden_3_days_or_surgery_12wk,
        localized_tenderness,
        entire_leg_swollen,
        calf_swelling_3cm_greater,
        pitting_oedema,
        collateral_superficial_veins,
        previous_dvt,
        -2 if alternative_diagnosis_as_likely else 0,
    ])

    if score <= 0:
        probability = "Low"
        dvt_likelihood = "~5%"
        recommendation = "D-dimer test recommended. If negative, DVT ruled out."
    elif score in (1, 2):
        probability = "Moderate"
        dvt_likelihood = "~17%"
        recommendation = "D-dimer test. If positive or unavailable, proceed to ultrasound."
    else:
        probability = "High"
        dvt_likelihood = "~53%"
        recommendation = "Proximal leg ultrasound recommended immediately."

    return {
        "tool": "Wells Score for DVT",
        "score": score,
        "dvt_probability": probability,
        "approximate_dvt_likelihood": dvt_likelihood,
        "recommendation": recommendation,
    }


@tool
def cha2ds2_vasc_score(
    congestive_heart_failure: bool = False,
    hypertension: bool = False,
    age_75_or_over: bool = False,
    diabetes: bool = False,
    stroke_or_tia_history: bool = False,
    vascular_disease: bool = False,
    age_65_to_74: bool = False,
    female_sex: bool = False,
) -> dict[str, Any]:
    """
    Calculate CHA₂DS₂-VASc score for stroke risk in atrial fibrillation.
    Used to guide anticoagulation decisions.
    All fields default to False (criterion absent).
    """
    score = sum([
        congestive_heart_failure,
        hypertension,
        2 if age_75_or_over else 0,
        diabetes,
        2 if stroke_or_tia_history else 0,
        vascular_disease,
        age_65_to_74,
        female_sex,
    ])

    if score == 0:
        annual_stroke_risk = "0%"
        recommendation = "No anticoagulation recommended."
    elif score == 1:
        annual_stroke_risk = "~1.3%"
        recommendation = "Consider anticoagulation based on clinical context."
    elif score == 2:
        annual_stroke_risk = "~2.2%"
        recommendation = "Oral anticoagulation recommended."
    else:
        annual_stroke_risk = f"~{score * 1.5:.1f}%+ (score={score})"
        recommendation = "Oral anticoagulation strongly recommended."

    return {
        "tool": "CHA₂DS₂-VASc Score",
        "score": score,
        "annual_stroke_risk_estimate": annual_stroke_risk,
        "recommendation": recommendation,
    }


# Registry for the graph to reference by name
CALCULATOR_TOOLS = [ascvd_risk_calculator, wells_dvt_score, cha2ds2_vasc_score]
TOOL_MAP = {t.name: t for t in CALCULATOR_TOOLS}
