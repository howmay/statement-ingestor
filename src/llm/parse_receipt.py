import os
import json
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ReceiptParsingError(Exception):
    """Custom exception for receipt parsing errors."""
    pass


def parse_receipt_text(text: str, source_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Parse receipt/invoice text using LLM to extract structured data.
    
    Args:
        text: Text content extracted from PDF.
        source_info: Optional metadata about the source (sender, filename, etc.).
    
    Returns:
        Dictionary with parsed structured data:
        - 'date': Transaction date (YYYY-MM-DD)
        - 'amount': Transaction amount (float)
        - 'currency': Currency code (e.g., TWD, USD, SGD)
        - 'expense_name': Description of expense
        - 'expense_type': Category (e.g., Food, Transportation, Shopping, Bills)
        - 'source': Source identifier (bank name, merchant, etc.)
        - 'confidence': Confidence score (0.0-1.0)
        - 'raw_text_snippet': First 200 chars of text for reference
        - 'parsed_at': Timestamp of parsing
    
    Raises:
        ReceiptParsingError: If parsing fails or no valid data found.
    """
    if not text or not text.strip():
        raise ReceiptParsingError("Empty text provided for parsing")
    
    if source_info is None:
        source_info = {}
    
    logger.info(f"Parsing receipt text ({len(text)} chars), source: {source_info.get('sender_tag', 'unknown')}")
    
    # Check if OpenAI API key is available
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        logger.info("No OpenAI API key configured, using heuristic parsing")
        return _parse_with_heuristics(text, source_info)
    
    # Try OpenAI first, fallback to heuristic parsing
    try:
        logger.info("Attempting OpenAI API parsing...")
        return _parse_with_openai(text, source_info)
    except Exception as e:
        logger.warning(f"OpenAI parsing failed: {e}, trying heuristic fallback")
        return _parse_with_heuristics(text, source_info)


def _parse_with_openai(text: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse receipt text using OpenAI API.
    
    Args:
        text: Text content.
        source_info: Source metadata.
    
    Returns:
        Parsed structured data.
    
    Raises:
        ReceiptParsingError: If parsing fails.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ReceiptParsingError("OpenAI Python package not installed. Install with: pip install openai")
    
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ReceiptParsingError("OPENAI_API_KEY not configured in .env file")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    logger.info(f"Initialized OpenAI client for receipt parsing (model: gpt-4o-mini)")
    
    # Truncate text to fit token limits (keep first 4000 chars for context)
    truncated_text = text[:4000]
    if len(text) > 4000:
        logger.info(f"Truncated text from {len(text)} to 4000 characters for LLM")
    
    # Get sender tag for context
    sender_tag = source_info.get('sender_tag', 'unknown')
    sender = source_info.get('sender', '')
    
    # Determine likely source based on sender
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
    
    # Build system prompt
    system_prompt = """You are a financial data extraction expert. Extract structured information from receipt/invoice/bank statement text.
    
    Extract the following fields:
    1. date: Transaction date in YYYY-MM-DD format. If multiple dates, use the main transaction date.
    2. amount: Total transaction amount as a float number.
    3. currency: Currency code (TWD, USD, SGD, HKD, etc.).
    4. expense_name: Short description of the expense (e.g., "Uber ride", "Amazon purchase", "Credit card payment").
    5. expense_type: Category from: Food, Transportation, Shopping, Bills, Entertainment, Healthcare, Education, Travel, Other.
    6. source: Merchant or bank name.
    7. confidence: Your confidence in this extraction (0.0 to 1.0).
    
    Return ONLY valid JSON with these exact field names. If a field cannot be determined, use null.
    """
    
    # Build user prompt
    user_prompt = f"""Extract financial data from this {source} transaction text:

Text content:
{truncated_text}

Additional context:
- Sender: {sender}
- Source tag: {sender_tag}
- Original filename: {source_info.get('filename', 'unknown')}

Return JSON with: date, amount, currency, expense_name, expense_type, source, confidence"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use cost-effective model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for consistent output
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        logger.info(f"OpenAI response received ({len(result_text)} chars): {result_text[:200]}...")
        
        # Parse JSON response
        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI JSON response: {e}, response: {result_text}")
            raise ReceiptParsingError(f"Invalid JSON response from OpenAI: {e}")
        
        # Validate required fields
        required_fields = ['date', 'amount', 'currency', 'expense_name', 'expense_type', 'source', 'confidence']
        for field in required_fields:
            if field not in parsed:
                parsed[field] = None
        
        # Validate and normalize data
        parsed = _validate_and_normalize_parsed_data(parsed, source_info)
        
        # Add metadata
        parsed['raw_text_snippet'] = text[:200]
        parsed['parsed_at'] = datetime.now().isoformat()
        parsed['llm_model'] = 'gpt-4o-mini'
        parsed['parsing_method'] = 'openai'
        
        logger.info(f"Successfully parsed receipt: {parsed.get('expense_name')} - {parsed.get('amount')} {parsed.get('currency')}")
        return parsed
        
    except Exception as e:
        raise ReceiptParsingError(f"OpenAI API error: {e}")


def _parse_with_heuristics(text: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback heuristic parsing when LLM is unavailable.
    
    Args:
        text: Text content.
        source_info: Source metadata.
    
    Returns:
        Parsed structured data (basic extraction).
    """
    logger.info("Using heuristic fallback parsing")
    
    # Extract sender tag for source
    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag:
        source = "HSBC Bank"
    elif 'fubon' in sender_tag:
        source = "Fubon Bank"
    elif 'esunbank' in sender_tag:
        source = "Esun Bank"
    
    # Initialize result with defaults
    result = {
        'date': None,
        'amount': None,
        'currency': None,
        'expense_name': 'Bank Statement Transaction',
        'expense_type': 'Bills',
        'source': source,
        'confidence': 0.3,  # Low confidence for heuristic parsing
        'raw_text_snippet': text[:200],
        'parsed_at': datetime.now().isoformat(),
        'llm_model': None,
        'parsing_method': 'heuristic'
    }
    
    # Try to extract date (common formats in bank statements)
    date_patterns = [
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',  # YYYY-MM-DD, YYYY/MM/DD
        r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',  # DD-MM-YYYY, DD/MM/YYYY
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',     # Chinese date format
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text[:1000])  # Search first 1000 chars
        if match:
            try:
                if '年' in pattern:
                    # Chinese date: 2024年12月31日
                    year, month, day = match.groups()
                elif len(match.group(1)) == 4:
                    # YYYY-MM-DD
                    year, month, day = match.groups()
                else:
                    # DD-MM-YYYY
                    day, month, year = match.groups()
                
                # Format as YYYY-MM-DD
                result['date'] = f"{year}-{int(month):02d}-{int(day):02d}"
                result['confidence'] = min(result['confidence'] + 0.2, 0.8)
                break
            except (ValueError, IndexError):
                continue
    
    # Try to extract amount (common in bank statements)
    # Look for currency amounts with symbols
    amount_patterns = [
        r'[NT$US$S$HK$¥€£]?\s*([0-9,]+\.?[0-9]*)\s*[元美元新幣港幣]?',
        r'([0-9,]+\.?[0-9]*)\s*[NTD|USD|SGD|HKD|TWD]',
        r'金額[：:]\s*([0-9,]+\.?[0-9]*)',
        r'Amount[：:]\s*([0-9,]+\.?[0-9]*)',
    ]
    
    for pattern in amount_patterns:
        matches = re.findall(pattern, text[:2000])
        if matches:
            # Get the largest amount (likely the total)
            try:
                amounts = []
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    # Remove commas and convert to float
                    clean_amount = match.replace(',', '')
                    if clean_amount.replace('.', '', 1).isdigit():
                        amounts.append(float(clean_amount))
                
                if amounts:
                    # Use the largest amount (likely total)
                    result['amount'] = max(amounts)
                    result['confidence'] = min(result['confidence'] + 0.2, 0.8)
                    
                    # Try to determine currency
                    if 'NT$' in text or 'TWD' in text:
                        result['currency'] = 'TWD'
                    elif 'US$' in text or 'USD' in text:
                        result['currency'] = 'USD'
                    elif 'S$' in text or 'SGD' in text:
                        result['currency'] = 'SGD'
                    elif 'HK$' in text or 'HKD' in text:
                        result['currency'] = 'HKD'
                    break
            except (ValueError, TypeError):
                continue
    
    # If amount not found, try simple number patterns
    if result['amount'] is None:
        # Look for numbers with 2 decimal places (common for amounts)
        decimal_pattern = r'\b([0-9,]+\.?[0-9]{2})\b'
        matches = re.findall(decimal_pattern, text[:1500])
        if matches:
            try:
                amounts = []
                for match in matches:
                    clean_amount = match.replace(',', '')
                    if clean_amount.replace('.', '', 1).isdigit():
                        amount = float(clean_amount)
                        # Filter out unlikely amounts (too small or too large)
                        if 10 <= amount <= 100000:
                            amounts.append(amount)
                
                if amounts:
                    result['amount'] = max(amounts)
                    result['confidence'] = min(result['confidence'] + 0.1, 0.7)
                    result['currency'] = 'TWD'  # Default to TWD for Taiwan
            except (ValueError, TypeError):
                pass
    
    # Determine expense type based on keywords
    text_lower = text.lower()
    expense_keywords = {
        'Food': ['food', 'restaurant', 'meal', '咖啡', '餐廳', '小吃', '早餐', '午餐', '晚餐'],
        'Transportation': ['transport', 'uber', 'taxi', 'metro', 'mrt', 'bus', 'gas', 'fuel', '加油', '交通'],
        'Shopping': ['shopping', 'store', 'market', 'purchase', 'buy', 'amazon', 'shop', '購物', '商城'],
        'Bills': ['bill', 'payment', 'utility', 'electric', 'water', 'phone', 'internet', '信用卡', '帳單', '繳費'],
        'Entertainment': ['movie', 'cinema', 'concert', 'game', 'netflix', 'spotify', '娛樂', '電影', '音樂'],
        'Healthcare': ['medical', 'hospital', 'clinic', 'pharmacy', 'doctor', 'health', '醫療', '醫院', '藥局'],
        'Travel': ['travel', 'flight', 'hotel', 'airbnb', 'vacation', 'trip', '旅遊', '飯店', '機票'],
    }
    
    for expense_type, keywords in expense_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            result['expense_type'] = expense_type
            result['confidence'] = min(result['confidence'] + 0.1, 0.9)
            break
    
    logger.info(f"Heuristic parsing result: {result.get('expense_name')} - {result.get('amount')}")
    return result


def _validate_and_normalize_parsed_data(parsed: Dict[str, Any], source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize parsed data.
    
    Args:
        parsed: Raw parsed data.
        source_info: Source metadata.
    
    Returns:
        Validated and normalized data.
    """
    # Validate date format
    if parsed.get('date'):
        date_str = str(parsed['date'])
        try:
            # Try to parse and reformat date
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%Y年%m月%d日']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    parsed['date'] = dt.strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue
        except (ValueError, TypeError):
            parsed['date'] = None
            if parsed.get('confidence', 0) > 0:
                parsed['confidence'] = max(parsed['confidence'] - 0.2, 0.1)
    
    # Validate amount
    if parsed.get('amount') is not None:
        try:
            # Convert to float if it's a string
            if isinstance(parsed['amount'], str):
                parsed['amount'] = float(parsed['amount'].replace(',', ''))
            elif not isinstance(parsed['amount'], (int, float)):
                parsed['amount'] = None
        except (ValueError, TypeError):
            parsed['amount'] = None
    
    # Set default currency if missing
    if not parsed.get('currency'):
        # Default based on source
        sender_tag = source_info.get('sender_tag', '')
        if 'sg' in sender_tag:
            parsed['currency'] = 'SGD'
        elif 'tw' in sender_tag:
            parsed['currency'] = 'TWD'
        elif 'hk' in sender_tag:
            parsed['currency'] = 'HKD'
        else:
            parsed['currency'] = 'USD'
    
    # Validate expense name
    if not parsed.get('expense_name') or parsed['expense_name'] == 'null':
        parsed['expense_name'] = 'Transaction'
        if source_info.get('subject'):
            parsed['expense_name'] = f"Transaction: {source_info['subject'][:50]}"
    
    # Validate expense type
    valid_types = ['Food', 'Transportation', 'Shopping', 'Bills', 'Entertainment', 
                   'Healthcare', 'Education', 'Travel', 'Other']
    if parsed.get('expense_type') not in valid_types:
        parsed['expense_type'] = 'Other'
    
    # Validate confidence
    confidence = parsed.get('confidence', 0)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        parsed['confidence'] = 0.5
    
    return parsed


def parse_multiple_receipts(texts: List[str], source_infos: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Parse multiple receipt texts.
    
    Args:
        texts: List of text contents.
        source_infos: Optional list of source metadata.
    
    Returns:
        List of parsed structured data.
    """
    if source_infos is None:
        source_infos = [{} for _ in range(len(texts))]
    
    if len(texts) != len(source_infos):
        raise ValueError("Number of texts must match number of source_infos")
    
    results = []
    for i, (text, source_info) in enumerate(zip(texts, source_infos)):
        try:
            result = parse_receipt_text(text, source_info)
            results.append(result)
            logger.info(f"Parsed {i+1}/{len(texts)} receipts")
        except ReceiptParsingError as e:
            logger.error(f"Failed to parse receipt {i+1}: {e}")
            # Add error entry
            results.append({
                'error': str(e),
                'text_index': i,
                'parsed_at': datetime.now().isoformat()
            })
    
    return results


if __name__ == '__main__':
    # Test with sample text
    import sys
    logging.basicConfig(level=logging.INFO)
    
    test_text = """
    HSBC Credit Card Statement
    Statement Date: 2024-12-31
    Card Number: **** **** **** 1234
    
    Transaction Date: 2024-12-25
    Merchant: Uber Technologies Inc.
    Amount: NT$350.00
    Description: Uber ride from Taipei Main Station to Xinyi District
    
    Transaction Date: 2024-12-24
    Merchant: Amazon.com
    Amount: NT$1,250.00
    Description: Online shopping - Electronics
    
    Total Amount Due: NT$1,600.00
    Due Date: 2025-01-15
    """
    
    test_source = {
        'sender': 'HSBC@mail.hsbc.com.sg',
        'sender_tag': 'hsbc_sg',
        'filename': 'hsbc_statement.pdf',
        'subject': 'Your HSBC Credit Card Statement - December 2024'
    }
    
    try:
        print("Testing receipt parsing...")
        result = parse_receipt_text(test_text, test_source)
        print(f"\nParsed result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)