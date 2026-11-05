"""Resilient Parser & Schema Coercion Engine.

Transforms brittle JSON tool parsing into a bulletproof recovery pipeline:
  - Handles markdown code fences (```json ... ```).
  - Automatically fixes common local 8B syntax quirks: trailing commas, unquoted keys,
    single-quoted JSON, Python dictionary reprs (`{'key': True}`).
  - Coerces argument data types according to tool parameter schemas (e.g. "10" -> 10,
    "true" -> True, comma-separated string -> list).
  - Prevents {"_raw": ...} TypeError crashes during tool execution.
"""

from __future__ import annotations

import json
import re
from typing import Any


def repair_and_parse_json(raw: Any) -> dict[str, Any]:
    """Tolerantly parses JSON or dictionary-like string from LLM tool outputs."""
    if isinstance(raw, dict):
        return dict(raw)
    if raw is None:
        return {}
    if not isinstance(raw, str):
        return {"input": raw}

    cleaned = raw.strip()
    if not cleaned:
        return {}

    # 1. Strip markdown code fences if wrapped
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # 2. Try native standard JSON parsing
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {"input": parsed}
    except Exception:
        pass

    # 3. Clean syntax quirks:
    # Remove trailing commas: `,\s*}` -> `}` and `,\s*]` -> `]`
    repaired = re.sub(r",\s*([\]}])", r"\1", cleaned)

    # Convert single-quoted strings/keys to double quotes if standard JSON failed
    # Python-style True/False/None to true/false/null
    repaired_py = (
        repaired
        .replace(": True", ": true")
        .replace(": False", ": false")
        .replace(": None", ": null")
    )

    try:
        parsed = json.loads(repaired_py)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Try literal_eval for Python dict reprs safely
    try:
        import ast
        val = ast.literal_eval(repaired)
        if isinstance(val, dict):
            return {str(k): v for k, v in val.items()}
    except Exception:
        pass

    # 4. Regex key-value heuristic extraction fallback
    extracted: dict[str, Any] = {}
    pattern = re.compile(
        r'["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']?\s*[:=]\s*('
        r'["\'](?:\\.|[^"\'])*["\']|'
        r'[-+]?\d*\.?\d+|'
        r'true|false|null|'
        r'\[[\s\S]*?\]|\{[\s\S]*?\}'
        r')',
        re.IGNORECASE,
    )

    for m in pattern.finditer(cleaned):
        k, v = m.group(1), m.group(2).strip()
        # Clean quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v_val: Any = v[1:-1]
        elif v.lower() == "true":
            v_val = True
        elif v.lower() == "false":
            v_val = False
        elif v.lower() == "null":
            v_val = None
        else:
            try:
                v_val = int(v) if "." not in v else float(v)
            except ValueError:
                v_val = v
        extracted[k] = v_val

    if extracted:
        return extracted

    # Last resort: return clean string in a standard 'input' or 'query' key instead of broken dict
    return {"query": cleaned}


def coerce_tool_arguments(
    params_schema: dict[str, Any] | None,
    raw_args: dict[str, Any],
) -> dict[str, Any]:
    """Coerces argument types to match the tool's JSON schema properties."""
    if not isinstance(raw_args, dict):
        raw_args = repair_and_parse_json(raw_args)

    if not params_schema or not isinstance(params_schema, dict):
        return raw_args

    properties = params_schema.get("properties") or {}
    if not isinstance(properties, dict):
        return raw_args

    coerced = dict(raw_args)

    for prop_name, prop_spec in properties.items():
        if prop_name not in coerced:
            continue

        val = coerced[prop_name]
        expected_type = str(prop_spec.get("type") or "").lower()

        # Handle Integer coercion
        if expected_type == "integer" and isinstance(val, (str, float)):
            try:
                coerced[prop_name] = int(float(val))
            except (ValueError, TypeError):
                pass

        # Handle Number / Float coercion
        elif expected_type == "number" and isinstance(val, str):
            try:
                coerced[prop_name] = float(val)
            except (ValueError, TypeError):
                pass

        # Handle Boolean coercion
        elif expected_type == "boolean" and isinstance(val, str):
            coerced[prop_name] = val.strip().lower() in ("true", "1", "yes", "t", "y")

        # Handle Array coercion
        elif expected_type == "array" and isinstance(val, str):
            val_str = val.strip()
            if val_str.startswith("[") and val_str.endswith("]"):
                try:
                    coerced[prop_name] = json.loads(val_str)
                except Exception:
                    coerced[prop_name] = [x.strip() for x in val_str[1:-1].split(",") if x.strip()]
            else:
                coerced[prop_name] = [x.strip() for x in val_str.split(",") if x.strip()]

    return coerced
