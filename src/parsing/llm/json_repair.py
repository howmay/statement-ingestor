"""JSON extraction and repair helpers for LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def extract_json_payload(response_text: str) -> str:
    """Try to recover JSON from raw model text (including fenced markdown)."""
    text = (response_text or "").strip()
    if not text:
        return text

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    if text.startswith('{') or text.startswith('['):
        return text

    first_obj = text.find('{')
    first_arr = text.find('[')
    candidates = [idx for idx in (first_obj, first_arr) if idx != -1]
    if not candidates:
        return text

    start = min(candidates)
    return text[start:].strip()


def finalize_fixed_json(parsed: Any, fixed_str: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Apply structural fixes and return serialized JSON string."""
    context = context or {}

    if isinstance(parsed, dict):
        if 'expected_keys' in context:
            for key in context['expected_keys']:
                if key not in parsed:
                    parsed[key] = []

        if 'transactions' in parsed and isinstance(parsed['transactions'], list):
            required_fields = ['date', 'amount', 'currency', 'expense_name', 'expense_type', 'source', 'confidence']
            for tx in parsed['transactions']:
                if isinstance(tx, dict):
                    for field in required_fields:
                        if field not in tx:
                            tx[field] = None
            return json.dumps(parsed, ensure_ascii=False)

    return fixed_str


def fix_truncated_json_enhanced(json_str: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Enhanced function to fix truncated JSON strings."""
    if not json_str:
        return None

    context = context or {}

    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    json_str = json_str.strip()
    if not json_str.startswith(('{', '[')):
        return None

    def try_fix(s: str):
        stack = []
        in_string = False
        escaped = False
        for char in s:
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                stack.append('}')
            elif char == '[':
                stack.append(']')
            elif char == '}':
                if stack and stack[-1] == '}':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == ']':
                    stack.pop()

        fixed = s
        if in_string:
            fixed += '"'

        temp = fixed.strip()
        if temp.endswith(':'):
            fixed += ' null'
        elif temp.endswith(','):
            fixed = temp[:-1]

        while stack:
            fixed += stack.pop()

        try:
            return json.loads(fixed), fixed
        except json.JSONDecodeError:
            return None, None

    parsed, fixed = try_fix(json_str)
    if parsed is not None and fixed is not None:
        return finalize_fixed_json(parsed, fixed, context)

    for i in range(len(json_str) - 1, 0, -1):
        if json_str[i] in ('}', ']', ',', '"', ':'):
            parsed, fixed = try_fix(json_str[: i + 1])
            if parsed is not None and fixed is not None:
                return finalize_fixed_json(parsed, fixed, context)

    return None


def fix_truncated_json(json_str: str) -> Optional[str]:
    """Compatibility wrapper for legacy imports."""
    return fix_truncated_json_enhanced(json_str)
