import os
import json
import logging
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Import enhanced utilities
from src.utils.retry_enhanced import enhanced_retry_openai, JSONTruncationError
from src.bank_parsers.factory import parse_with_bank_factory

logger = logging.getLogger(__name__)


class ReceiptParsingError(Exception):
    """Custom exception for receipt parsing errors."""
    pass


def _get_llm_runtime_config() -> Dict[str, Any]:
    """
    Resolve runtime LLM config.

    Priority:
    1) Explicit LLM_PROVIDER
    2) Default to local OpenAI-compatible runtime
    """
    provider = os.getenv("LLM_PROVIDER", "local").strip().lower()

    # Local OpenAI-compatible runtime (requested branch default)
    if provider in {"local", "openai-completions"}:
        base_url = os.getenv("LOCAL_BASE_URL", "http://0.0.0.0:30000/v1").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        model = os.getenv("LOCAL_MODEL", "qwen3.5-9b")
        api_key = os.getenv("LOCAL_API_KEY", "not-needed")

        return {
            "provider": "local",
            "enabled": True,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "supports_response_format": False,
        }

    # Optional backward-compatible Ollama path
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        model = os.getenv("OLLAMA_MODEL", "lukey03/qwen3.5-9b-abliterated-vision")
        api_key = os.getenv("OLLAMA_API_KEY", "ollama-local")

        return {
            "provider": "ollama",
            "enabled": True,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "supports_response_format": False,
        }

    # OpenAI cloud path
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None

    enabled = bool(api_key and api_key != "your_openai_api_key_here")
    return {
        "provider": "openai",
        "enabled": enabled,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "supports_response_format": True,
    }


def _extract_json_payload(response_text: str) -> str:
    """Try to recover JSON from raw model text (including fenced markdown)."""
    text = (response_text or "").strip()
    if not text:
        return text

    # Remove markdown fence wrappers if present
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    if text.startswith('{') or text.startswith('['):
        return text

    # Fallback: locate first JSON object/array region
    first_obj = text.find('{')
    first_arr = text.find('[')
    candidates = [idx for idx in (first_obj, first_arr) if idx != -1]
    if not candidates:
        return text

    start = min(candidates)
    return text[start:].strip()


def _safe_env_int(name: str, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        val = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, val))


def _get_chunking_config() -> Dict[str, Any]:
    """Read adaptive chunking controls from environment variables."""
    enabled = os.getenv('ENABLE_ADAPTIVE_CHUNKING', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    max_chunk_size = _safe_env_int('MAX_CHUNK_SIZE', 3500, minimum=500, maximum=20000)
    min_tx_per_chunk = _safe_env_int('MIN_TRANSACTIONS_PER_CHUNK', 5, minimum=1, maximum=100)
    force_threshold = _safe_env_int('FORCE_CHUNKING_TEXT_LENGTH', 8000, minimum=1000, maximum=50000)

    return {
        'enabled': enabled,
        'max_chunk_size': max_chunk_size,
        'min_transactions_per_chunk': min_tx_per_chunk,
        'force_threshold': force_threshold,
    }


def parse_receipt_text(text: str, source_info: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Parse receipt/invoice text using LLM to extract structured data.
    
    Args:
        text: Text content extracted from PDF.
        source_info: Optional metadata about the source (sender, filename, etc.).
    
    Returns:
        List of parsed transaction dictionaries.
    """
    if not text or not text.strip():
        raise ReceiptParsingError("Empty text provided for parsing")
    
    if source_info is None:
        source_info = {}
    
    logger.info(f"Parsing receipt text ({len(text)} chars), source: {source_info.get('sender_tag', 'unknown')}")

    # 1) Deterministic bank parser first (accuracy-first path)
    strict_bank_parser = os.getenv('STRICT_BANK_PARSER', 'true').lower() in {'1', 'true', 'yes', 'on'}
    bank_result = parse_with_bank_factory(text, source_info)
    if bank_result.matched:
        if bank_result.transactions:
            logger.info(
                f"Deterministic parser matched: {bank_result.parser_name}, "
                f"transactions={len(bank_result.transactions)}"
            )
            return bank_result.transactions

        msg = f"Deterministic parser matched ({bank_result.parser_name}) but extracted 0 transactions"
        if strict_bank_parser:
            raise ReceiptParsingError(msg)
        logger.warning(msg)

    # 2) LLM path for non-bank or when strict mode disabled
    llm_config = _get_llm_runtime_config()
    if not llm_config.get("enabled"):
        logger.info("No LLM runtime configured, using heuristic parsing")
        return _parse_with_heuristics(text, source_info)

    try:
        logger.info(
            f"Attempting {llm_config.get('provider')} parsing with model: {llm_config.get('model')}"
        )
        return _parse_with_openai_enhanced(text, source_info, llm_config)
    except Exception as e:
        logger.warning(f"LLM parsing failed: {e}, trying heuristic fallback")
        return _parse_with_heuristics(text, source_info)


def _fix_truncated_json(json_str: str) -> Optional[str]:
    """
    Attempt to fix truncated JSON strings using a stack-based approach.
    """
    return _fix_truncated_json_enhanced(json_str)


def _finalize_fixed_json(parsed: Any, fixed_str: str, context: Dict[str, Any] = None) -> str:
    """Helper to apply context and return JSON string."""
    if context and isinstance(parsed, dict):
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


def _fix_truncated_json_enhanced(json_str: str, context: Dict[str, Any] = None) -> Optional[str]:
    """
    Enhanced function to fix truncated JSON strings.
    """
    if not json_str:
        return None
    
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass
    
    json_str = json_str.strip()
    if not json_str.startswith(('{', '[')):
        return None
    
    def try_fix(s):
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
                if stack and stack[-1] == '}': stack.pop()
            elif char == ']':
                if stack and stack[-1] == ']': stack.pop()
        
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
    if parsed:
        return _finalize_fixed_json(parsed, fixed, context)
        
    for i in range(len(json_str) - 1, 0, -1):
        if json_str[i] in ('}', ']', ',', '"', ':'):
            parsed, fixed = try_fix(json_str[:i+1])
            if parsed:
                return _finalize_fixed_json(parsed, fixed, context)
                
    return None


def _chunk_text_by_transactions(text: str, max_chunk_size: int = 3500, 
                               min_transactions_per_chunk: int = 5) -> List[Tuple[str, List[int]]]:
    """
    Split text into chunks based on transaction boundaries.
    """
    if len(text) <= max_chunk_size:
        return [(text, [0])]
    
    lines = text.split('\n')
    transaction_starts = []
    
    date_patterns = [
        r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
        r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',
        r'\d{3}[-/]\d{1,2}[-/]\d{1,2}',
        r'\d{4}年\d{1,2}月\d{1,2}日',
    ]
    
    for i, line in enumerate(lines):
        for pattern in date_patterns:
            if re.search(pattern, line):
                transaction_starts.append(i)
                break
    
    if len(transaction_starts) < 2:
        return [(text[i:i + max_chunk_size], [i]) for i in range(0, len(text), max_chunk_size)]
    
    chunks = []
    current_chunk_lines = []
    current_chunk_indices = []
    current_size = 0
    
    for i, line in enumerate(lines):
        line_size = len(line) + 1
        is_transaction_start = i in transaction_starts
        
        if (current_size + line_size > max_chunk_size and 
            len(current_chunk_indices) >= min_transactions_per_chunk and
            is_transaction_start):
            
            if current_chunk_lines:
                chunks.append(('\n'.join(current_chunk_lines), current_chunk_indices.copy()))
            
            current_chunk_lines = [line]
            current_chunk_indices = [i] if is_transaction_start else []
            current_size = line_size
        else:
            current_chunk_lines.append(line)
            if is_transaction_start:
                current_chunk_indices.append(i)
            current_size += line_size
    
    if current_chunk_lines:
        chunks.append(('\n'.join(current_chunk_lines), current_chunk_indices))
    
    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks


def _should_enable_chunking(text: str, source_info: Dict[str, Any], force: bool = False) -> bool:
    """Determine whether to enable chunking."""
    cfg = _get_chunking_config()
    if not cfg['enabled'] and not force:
        return False

    if force:
        return True

    if len(text) > cfg['force_threshold']:
        return True

    sender_tag = source_info.get('sender_tag', '').lower()
    if 'hsbc' in sender_tag and len(text) > 5000:
        return True

    date_count = len(re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', text))
    if date_count > 25:
        return True

    return False


def _calculate_max_tokens(text_length: int) -> int:
    """Calculate max_tokens."""
    return min(4000, 1000 + (text_length // 2))


def _merge_transaction_results(all_transactions: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Merge and deduplicate results."""
    if not all_transactions:
        return []
    flat_transactions = []
    for chunk_transactions in all_transactions:
        flat_transactions.extend(chunk_transactions)
    seen = set()
    unique_transactions = []
    for tx in flat_transactions:
        key = (tx.get('date'), f"{float(tx.get('amount', 0)):.2f}" if tx.get('amount') is not None else "0.00", tx.get('expense_name', '')[:50])
        if key not in seen:
            seen.add(key)
            unique_transactions.append(tx)
    return unique_transactions


def _parse_with_adaptive_strategy(
    text: str,
    source_info: Dict[str, Any],
    source_label: str,
    model_name: str,
    provider_name: str,
    call_llm,
    force_chunking: bool = False,
) -> List[Dict[str, Any]]:
    """Adaptive parsing strategy for large transaction lists."""
    chunk_cfg = _get_chunking_config()
    user_prompt_template = "Extract transactions from {source} text:\n{text}"

    if _should_enable_chunking(text, source_info, force=force_chunking):
        chunks = _chunk_text_by_transactions(
            text,
            max_chunk_size=chunk_cfg['max_chunk_size'],
            min_transactions_per_chunk=chunk_cfg['min_transactions_per_chunk'],
        )
        logger.info(f"Chunking enabled, processing {len(chunks)} chunks")

        all_transactions = []
        for i, (chunk_text, _) in enumerate(chunks):
            user_prompt = user_prompt_template.format(text=chunk_text, source=source_label)
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                result_text = call_llm(user_prompt, _calculate_max_tokens(len(chunk_text)))
                json_payload = _extract_json_payload(result_text)
                fixed_json = _fix_truncated_json_enhanced(json_payload, {'expected_keys': ['transactions']})
                parsed = json.loads(fixed_json or json_payload)
                all_transactions.append(
                    _extract_and_validate_transactions(parsed, source_info, chunk_text, model_name, provider_name)
                )
            except Exception as e:
                logger.error(f"Chunk {i+1} failed after retries: {e}")

        if not all_transactions:
            raise ReceiptParsingError("All chunks failed to parse")

        return _merge_transaction_results(all_transactions)

    user_prompt = user_prompt_template.format(text=text, source=source_label)
    result_text = call_llm(user_prompt, 4000)
    json_payload = _extract_json_payload(result_text)
    fixed_json = _fix_truncated_json_enhanced(json_payload, {'expected_keys': ['transactions']})

    try:
        parsed = json.loads(fixed_json or json_payload)
    except json.JSONDecodeError as je:
        raise JSONTruncationError(f"Final JSON decode error: {je}")

    return _extract_and_validate_transactions(parsed, source_info, text, model_name, provider_name)


@enhanced_retry_openai
def _parse_with_openai_enhanced(
    text: str,
    source_info: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """LLM parsing via OpenAI-compatible API (OpenAI cloud or local Ollama)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ReceiptParsingError("OpenAI Python package not installed")

    cfg = llm_config or _get_llm_runtime_config()
    if not cfg.get("enabled"):
        raise ReceiptParsingError("No LLM runtime configured")

    client_kwargs = {"api_key": cfg.get("api_key")}
    if cfg.get("base_url"):
        client_kwargs["base_url"] = cfg.get("base_url")

    client = OpenAI(**client_kwargs)
    model_name = cfg.get("model", "gpt-4o-mini")
    provider_name = cfg.get("provider", "openai")
    supports_response_format = bool(cfg.get("supports_response_format", False))

    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag:
        source = "HSBC Bank"
    elif 'fubon' in sender_tag:
        source = "Fubon Bank"
    elif 'esunbank' in sender_tag:
        source = "Esun Bank"
    elif 'apple' in sender_tag:
        source = "Apple"
    elif 'uber' in sender_tag:
        source = "Uber"
    elif 'amazon' in sender_tag:
        source = "Amazon"

    system_prompt = (
        "You are a financial data extraction expert. "
        "Extract ALL transactions and return JSON only. "
        "Return exactly this shape: {\"transactions\":[{" 
        "\"date\":\"YYYY-MM-DD\",\"amount\":123.45,\"currency\":\"TWD\"," 
        "\"expense_name\":\"...\",\"expense_type\":\"Other\",\"source\":\"...\",\"confidence\":0.9}]}."
    )

    @enhanced_retry_openai
    def call_llm_with_retry(prompt_text: str, max_tokens: int) -> str:
        api_kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if supports_response_format:
            api_kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**api_kwargs)
        content = response.choices[0].message.content or ""

        # Check for truncation
        if not content.strip().endswith('}') and not content.strip().endswith(']'):
            try:
                json.loads(content)
            except json.JSONDecodeError:
                logger.warning("Detected potentially truncated JSON response")
                raise JSONTruncationError("JSON response appears truncated")

        return content

    # Check if we should force chunking (e.g. from a retry context)
    force_chunking = kwargs.get('context', {}).get('force_chunking', False)

    return _parse_with_adaptive_strategy(
        text=text,
        source_info=source_info,
        source_label=source,
        model_name=model_name,
        provider_name=provider_name,
        call_llm=call_llm_with_retry,
        force_chunking=force_chunking,
    )


def _extract_and_validate_transactions(
    parsed: Any,
    source_info: Dict[str, Any],
    original_text: str,
    model_name: str,
    provider_name: str,
) -> List[Dict[str, Any]]:
    """Common extraction logic."""
    required_fields = ['date', 'amount', 'currency', 'expense_name', 'expense_type', 'source', 'confidence']
    transactions_raw = []
    if isinstance(parsed, list): transactions_raw = parsed
    elif isinstance(parsed, dict):
        for key in ('transactions', 'items', 'data', 'results'):
            if isinstance(parsed.get(key), list):
                transactions_raw = parsed[key]
                break
        if not transactions_raw and any(f in parsed for f in required_fields): transactions_raw = [parsed]
    
    transactions = []
    for tx in transactions_raw:
        if not isinstance(tx, dict): continue
        for field in required_fields:
            if field not in tx: tx[field] = None
        validated_tx = _validate_and_normalize_transaction(tx, source_info)
        _enrich_expense_name_from_text(validated_tx, original_text)
        validated_tx['raw_text_snippet'] = original_text[:200]
        validated_tx['parsed_at'] = datetime.now().isoformat()
        validated_tx['llm_model'] = model_name
        validated_tx['parsing_method'] = provider_name
        transactions.append(validated_tx)
    if not transactions: raise ReceiptParsingError("No transactions extracted")
    return transactions


def _parse_with_heuristics(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Heuristic fallback."""
    logger.info("Using heuristics")
    transactions = _extract_multiple_transactions_heuristic(text, source_info)
    if not transactions:
        transactions = [_extract_single_transaction_heuristic(text, source_info)]
    return [_validate_and_normalize_transaction(tx, source_info) for tx in transactions]


def _extract_multiple_transactions_heuristic(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract multiple via regex."""
    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag: source = "HSBC Bank"
    elif 'fubon' in sender_tag: source = "Fubon Bank"
    elif 'esunbank' in sender_tag: source = "Esun Bank"
    
    date_patterns = [r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', r'(\d{3})[-/](\d{1,2})[-/](\d{1,2})', r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', r'(\d{4})年(\d{1,2})月(\d{1,2})日']
    amount_patterns = [(r'(?:NT\$|TWD)\s*(-?[0-9,]+(?:\.[0-9]+)?)', 'TWD'), (r'(?:US\$|USD)\s*(-?[0-9,]+(?:\.[0-9]+)?)', 'USD')]
    
    lines = text.split('\n')
    transactions = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10: continue
        if any(kw in line.lower() for kw in ['statement', 'total', 'summary']): continue
        date_str = None
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    if '年' in pattern: y, m, d = match.groups()
                    elif len(match.group(1)) == 4: y, m, d = match.groups()
                    elif len(match.group(1)) == 3: y, m, d = str(int(match.group(1))+1911), match.group(2), match.group(3)
                    else: m, d, y = match.groups()
                    date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                    break
                except: continue
        amount_val, currency = None, None
        for pattern, curr in amount_patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    amount_val = float(match.group(1).replace(',', ''))
                    currency = curr
                    break
                except: continue
        if date_str and amount_val:
            transactions.append({'date': date_str, 'amount': amount_val, 'currency': currency, 'expense_name': line[:100], 'expense_type': 'Other', 'source': source, 'confidence': 0.5})
    return transactions


def _extract_single_transaction_heuristic(text: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """Single transaction regex."""
    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag: source = "HSBC Bank"
    elif 'fubon' in sender_tag: source = "Fubon Bank"
    elif 'esunbank' in sender_tag: source = "Esun Bank"
    result = {'date': None, 'amount': None, 'currency': 'TWD', 'expense_name': 'Bank Transaction', 'expense_type': 'Bills', 'source': source, 'confidence': 0.3}
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text[:1000])
    if match: result['date'] = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r'NT\$?\s*([0-9,]+\.[0-9]{2})', text[:2000])
    if match: result['amount'] = float(match.group(1).replace(',', ''))
    return result


def _enrich_expense_name_from_text(parsed: Dict[str, Any], text: str) -> None:
    """Enrich description."""
    if parsed.get('expense_name') and parsed['expense_name'] != 'Bank Transaction': return
    amount = parsed.get('amount')
    if amount is None: return
    amt_str = f"{abs(float(amount)):,.2f}"
    for line in text.splitlines():
        if amt_str in line:
            parsed['expense_name'] = line.strip()[:100]
            break


def _validate_and_normalize_transaction(parsed: Dict[str, Any], source_info: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data."""
    if parsed.get('date'):
        try: datetime.strptime(str(parsed['date']), '%Y-%m-%d')
        except: parsed['date'] = None
    if parsed.get('amount') is not None:
        try: parsed['amount'] = float(str(parsed['amount']).replace(',', ''))
        except: parsed['amount'] = None
    if not parsed.get('currency'): parsed['currency'] = 'TWD'
    if parsed.get('expense_type') not in ['Food', 'Transportation', 'Shopping', 'Bills', 'Entertainment', 'Healthcare', 'Education', 'Travel', 'Other']:
        parsed['expense_type'] = 'Other'
    parsed['confidence'] = float(parsed.get('confidence', 0.5))
    return parsed


def parse_multiple_receipts(texts: List[str], source_infos: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Parse list."""
    if source_infos is None: source_infos = [{} for _ in range(len(texts))]
    all_results = []
    for t, s in zip(texts, source_infos):
        try: all_results.extend(parse_receipt_text(t, s))
        except Exception as e: logger.error(f"Error: {e}")
    return all_results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(parse_receipt_text("2024-12-25 Uber NT$350.00", {'sender_tag': 'hsbc'}), indent=2))
