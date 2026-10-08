import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

from src.parsing.banks.factory import parse_with_bank_factory
from src.parsing.llm import chunking, json_repair

logger = logging.getLogger(__name__)


class ReceiptParsingError(Exception):
    """Custom exception for receipt parsing errors."""
    pass


class JSONTruncationError(ReceiptParsingError):
    """LLM output hit max_tokens or could not be decoded."""


_SOURCE_BY_TAG = (
    ('hsbc', 'HSBC Bank'),
    ('fubon', 'Fubon Bank'),
    ('esunbank', 'Esun Bank'),
    ('apple', 'Apple'),
    ('uber', 'Uber'),
    ('amazon', 'Amazon'),
)


def _source_from_tag(source_info: Dict[str, Any]) -> str:
    sender_tag = source_info.get('sender_tag', 'unknown')
    return next((label for tag, label in _SOURCE_BY_TAG if tag in sender_tag), "unknown")


def _get_llm_runtime_config() -> Dict[str, Any]:
    """
    Resolve runtime LLM config.

    Priority:
    1) Explicit LLM_PROVIDER
    2) Default to local OpenAI-compatible runtime
    """
    provider = os.getenv("LLM_PROVIDER", "local").strip().lower()

    # Local OpenAI-compatible runtime: the default for anything but "openai"
    if provider != "openai":
        base_url = os.getenv("LOCAL_BASE_URL", "http://0.0.0.0:30000/v1").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        if provider not in {"local", "openai-completions"}:
            logger.warning(f"Unknown LLM_PROVIDER={provider!r}; using local OpenAI-compatible runtime at {base_url}")

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
    bank_result = parse_with_bank_factory(text, source_info)
    if bank_result.matched:
        if bank_result.transactions:
            logger.info(
                f"Deterministic parser matched: {bank_result.parser_name}, "
                f"transactions={len(bank_result.transactions)}"
            )
            return bank_result.transactions

        # A matched bank statement with no rows is an empty month (carry-forward only,
        # notice/advice document); never hand it to the LLM.
        logger.warning(
            f"Deterministic parser matched ({bank_result.parser_name}) but extracted 0 transactions; "
            f"treating as an empty statement"
        )
        return []

    # 2) LLM path for non-bank text
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
        logger.warning(f"LLM parsing failed for {filename}: {e}, trying heuristic fallback")
        return _parse_with_heuristics(text, source_info)


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
    user_prompt_template = "Extract transactions from {source} text:\n{text}"
    filename = source_info.get('filename') or source_info.get('filepath') or '<unknown>'

    if chunking.should_enable_chunking(text, source_info, force=force_chunking):
        max_chunk_size = (
            max(500, min(chunking.MAX_CHUNK_SIZE, len(text)) // 2) if force_chunking else chunking.MAX_CHUNK_SIZE
        )
        chunks = chunking.chunk_text_by_transactions(
            text,
            max_chunk_size=max_chunk_size,
            min_transactions_per_chunk=chunking.MIN_TRANSACTIONS_PER_CHUNK,
        )
        logger.info(f"Split text into {len(chunks)} chunks for {filename}")

        all_transactions = []
        for i, (chunk_text, _) in enumerate(chunks):
            user_prompt = user_prompt_template.format(text=chunk_text, source=source_label)
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunks)} for {filename}")
                result_text = call_llm(user_prompt, chunking.calculate_max_tokens(len(chunk_text)))
                json_payload = json_repair.extract_json_payload(result_text)
                fixed_json = json_repair.fix_truncated_json_enhanced(json_payload, {'expected_keys': ['transactions']})
                parsed = json.loads(fixed_json or json_payload)
                all_transactions.append(
                    _extract_and_validate_transactions(parsed, source_info, chunk_text, model_name, provider_name)
                )
            except JSONTruncationError as e:
                if not force_chunking:
                    raise
                logger.error(f"Chunk {i+1} truncated for {filename}: {e}")
            except Exception as e:
                logger.error(f"Chunk {i+1} failed for {filename}: {e}")

        if not all_transactions:
            raise ReceiptParsingError("All chunks failed to parse")

        return chunking.merge_transaction_results(all_transactions)

    user_prompt = user_prompt_template.format(text=text, source=source_label)
    result_text = call_llm(user_prompt, 4000)
    json_payload = json_repair.extract_json_payload(result_text)
    fixed_json = json_repair.fix_truncated_json_enhanced(json_payload, {'expected_keys': ['transactions']})

    try:
        parsed = json.loads(fixed_json or json_payload)
    except json.JSONDecodeError as je:
        raise JSONTruncationError(f"Final JSON decode error: {je}")

    return _extract_and_validate_transactions(parsed, source_info, text, model_name, provider_name)


def _parse_with_openai_enhanced(
    text: str,
    source_info: Dict[str, Any],
    llm_config: Optional[Dict[str, Any]] = None,
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

    client = OpenAI(max_retries=3, **client_kwargs)
    model_name = cfg.get("model", "gpt-4o-mini")
    provider_name = cfg.get("provider", "openai")
    supports_response_format = bool(cfg.get("supports_response_format", False))

    system_prompt = (
        "You are a financial data extraction expert. "
        "Extract ALL transactions and return JSON only. "
        "Return exactly this shape: {\"transactions\":[{" 
        "\"date\":\"YYYY-MM-DD\",\"amount\":123.45,\"currency\":\"TWD\"," 
        "\"expense_name\":\"...\",\"expense_type\":\"Other\",\"source\":\"...\",\"confidence\":0.9}]}."
    )

    def call_llm(prompt_text: str, max_tokens: int) -> str:
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
        if response.choices[0].finish_reason == 'length':
            raise JSONTruncationError("LLM response hit max_tokens")
        return response.choices[0].message.content or ""

    filename = source_info.get('filename') or source_info.get('filepath') or '<unknown>'
    for force_chunking in (False, True):
        try:
            return _parse_with_adaptive_strategy(
                text=text,
                source_info=source_info,
                source_label=_source_from_tag(source_info),
                model_name=model_name,
                provider_name=provider_name,
                call_llm=call_llm,
                force_chunking=force_chunking,
            )
        except JSONTruncationError:
            if force_chunking:
                raise
            logger.warning(f"JSON response truncated for {filename}; retrying with forced chunking")


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
        single = _extract_single_transaction_heuristic(text, source_info)
        # No amount anywhere in the text means there is nothing to export.
        transactions = [single] if single.get('amount') is not None else []
    return [_validate_and_normalize_transaction(tx, source_info) for tx in transactions]


def _extract_multiple_transactions_heuristic(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract multiple via regex."""
    source = _source_from_tag(source_info)
    
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
    source = _source_from_tag(source_info)
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


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(parse_receipt_text("2024-12-25 Uber NT$350.00", {'sender_tag': 'hsbc'}), indent=2))
