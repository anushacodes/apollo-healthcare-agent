"""Input clarification and validation shared by graph execution and review resumption."""
import inspect
import math

from app.agent.tools import TOOL_MAP

LABELS = {
    "is_smoker": "Current smoker", "has_diabetes": "Diabetes present", "on_bp_treatment": "On blood-pressure treatment",
    "systolic_bp": "Systolic blood pressure (mmHg)", "total_cholesterol": "Total cholesterol (mg/dL)",
    "hdl_cholesterol": "HDL cholesterol (mg/dL)", "age": "Age (years)",
    "sex": "Sex used by calculator", "race": "Population group used by calculator",
}


def fields_for(tool: str, params: dict) -> list[dict]:
    if tool not in TOOL_MAP:
        return []
    return [{"name": name, "label": LABELS.get(name, name.replace("_", " ").capitalize()),
             "type": "boolean" if parameter.annotation is bool else
                     "choice" if name in ("sex", "race") else "number",
             "choices": ["male", "female"] if name == "sex" else
                        ["white", "african_american"] if name == "race" else []}
            for name, parameter in inspect.signature(TOOL_MAP[tool]).parameters.items()
            if name not in params or params[name] is None]


def validate_values(tool: str, params: dict) -> dict:
    if tool not in TOOL_MAP:
        raise ValueError("Unknown calculator")
    signature = inspect.signature(TOOL_MAP[tool])
    if set(params) - set(signature.parameters):
        raise ValueError("Unknown calculator input")
    clean = {}
    for name, value in params.items():
        annotation = signature.parameters[name].annotation
        if annotation is bool:
            if type(value) is not bool:
                raise ValueError(f"{name} must be Yes or No")
        elif annotation in (int, float):
            if isinstance(value, bool):
                raise ValueError(f"{name} must be a number")
            try:
                value = float(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{name} must be a number") from exc
            if not math.isfinite(value) or value <= 0 or value > 1000:
                raise ValueError(f"{name} must be positive and no greater than 1000")
            if annotation is int:
                if not value.is_integer() or value > 120:
                    raise ValueError("Age must be a whole number between 1 and 120")
                value = int(value)
        elif name in ("sex", "race"):
            allowed = ["male", "female"] if name == "sex" else ["white", "african_american"]
            if value not in allowed:
                raise ValueError(f"Choose a supported {name} value")
        clean[name] = value
    return clean


def execute_call(tool: str, params: dict) -> dict:
    if tool not in TOOL_MAP:
        return {"tool": tool, "error": "Unknown calculator"}
    try:
        clean = validate_values(tool, params)
    except ValueError as exc:
        return {"tool": tool, "status": "needs_input", "error": str(exc), "inputs": {},
                "rejected_inputs": params, "missing_fields": fields_for(tool, {})}
    missing = fields_for(tool, clean)
    if missing:
        return {"tool": tool, "status": "needs_input", "inputs": clean, "missing_fields": missing}
    try:
        result = TOOL_MAP[tool](**clean)
    except (ArithmeticError, ValueError, TypeError) as exc:
        return {"tool": tool, "status": "needs_input", "error": str(exc), "inputs": {},
                "rejected_inputs": clean, "missing_fields": fields_for(tool, {})}
    return {"tool": tool, "status": "complete", "inputs": clean, "result": result}
