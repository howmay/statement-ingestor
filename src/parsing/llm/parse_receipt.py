import os
import json
import logging
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Import enhanced utilities
from src.support.retry_enhanced import enhanced_retry_openai, JSONTruncationError
from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.llm.chunking import (
    safe_env_int as _safe_env_int_impl,
    get_chunking_config as _get_chunking_config_impl,
    should_enable_chunking as _should_enable_chunking_impl,
    calculate_max_tokens as _calculate_max_tokens_impl,
    chunk_text_by_transactions as _chunk_text_by_transactions_impl,
    merge_transaction_results as _merge_transaction_results_impl,
)
from src.parsing.llm.json_repair import (
    extract_json_payload as _extract_json_payload_impl,
    fix_truncated_json as _fix_truncated_json_impl,
    finalize_fixed_json as _finalize_fixed_json_impl,
    fix_truncated_json_enhanced as _fix_truncated_json_enhanced_impl,
)

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
    """Backward-compatible wrapper for JSON payload extraction."""
    return _extract_json_payload_impl(response_text)


def _safe_env_int(name: str, default: int, minimum: int = 1, maximum: int = 100000) -> int:
    """Backward-compatible wrapper for env int parsing."""
    return _safe_env_int_impl(name, default, minimum, maximum)


def _get_chunking_config() -> Dict[str, Any]:
    """Backward-compatible wrapper for chunking config."""
    return _get_chunking_config_impl()


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

        msg = f"Deterministic parser matched ({bank_result.parser_name}) but extracted 0 transactions."
        
        # Some banks explicitly warn when no transactions were found on a valid statement
        if any(w in " ".join(bank_result.warnings).lower() for w in ["no transaction", "no consumption"]):
            logger.info(f"{msg} Considered a valid empty statement.")
            return []
            
        # If strict mode, we trust the deterministic parser that matched but found nothing
        if strict_bank_parser:
            logger.info(f"{msg} Raising error to prevent LLM fallback (STRICT_BANK_PARSER=true).")
            raise ReceiptParsingError(msg)
        
        # If non-strict, we allow fallback if we think the deterministic parser might have missed something
        logger.info(f"{msg} Falling back to LLM because STRICT_BANK_PARSER=false.")

    # 2) LLM path for non-bank or when strict mode disabled
    llm_config = _get_llm_runtime_config()
    if not llm_config.get("enabled"):
        logger.info("No LLM runtime configured, using heuristic parsing")
        return _parse_with_heuristics(text, source_info)

    try:
        filename = source_info.get('filename') or source_info.get('filepath') or '<unknown>'
        logger.info(
            f"Attempting {llm_config.get('provider')} parsing for {filename} "
            f"with model: {llm_config.get('model')}"
        )
        return _parse_with_openai_enhanced(text, source_info, llm_config)
    except Exception as e:
        logger.warning(f"LLM parsing failed: {e}, trying heuristic fallback")
        return _parse_with_heuristics(text, source_info)


def _fix_truncated_json(json_str: str) -> Optional[str]:
    """Backward-compatible wrapper for truncated JSON repair."""
    return _fix_truncated_json_impl(json_str)


def _finalize_fixed_json(parsed: Any, fixed_str: str, context: Dict[str, Any] = None) -> str:
    """Backward-compatible wrapper for fixed JSON post-processing."""
    return _finalize_fixed_json_impl(parsed, fixed_str, context)


def _fix_truncated_json_enhanced(json_str: str, context: Dict[str, Any] = None) -> Optional[str]:
    """Backward-compatible wrapper for enhanced JSON repair."""
    return _fix_truncated_json_enhanced_impl(json_str, context)


def _chunk_text_by_transactions(
    text: str,
    max_chunk_size: int = 3500,
    min_transactions_per_chunk: int = 5,
) -> List[Tuple[str, List[int]]]:
    """Backward-compatible wrapper for transaction chunking."""
    chunks = _chunk_text_by_transactions_impl(
        text,
        max_chunk_size=max_chunk_size,
        min_transactions_per_chunk=min_transactions_per_chunk,
    )
    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks


def _should_enable_chunking(text: str, source_info: Dict[str, Any], force: bool = False) -> bool:
    """Backward-compatible wrapper for chunking decision."""
    return _should_enable_chunking_impl(text, source_info, force=force)


def _calculate_max_tokens(text_length: int) -> int:
    """Backward-compatible wrapper for max token calculation."""
    return _calculate_max_tokens_impl(text_length)


def _merge_transaction_results(all_transactions: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper for merging chunked transactions."""
    return _merge_transaction_results_impl(all_transactions)


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
