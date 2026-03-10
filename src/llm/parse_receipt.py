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


def _parse_with_openai(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
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
    
    If the text contains multiple transactions (like a bank statement), extract ALL transactions.
    Each transaction should have the following fields:
    1. date: Transaction date in YYYY-MM-DD format.
    2. amount: Transaction amount as a float number.
    3. currency: Currency code (TWD, USD, SGD, HKD, etc.).
    4. expense_name: Short description of the expense (e.g., "Uber ride", "Amazon purchase", "Credit card payment").
    5. expense_type: Category from: Food, Transportation, Shopping, Bills, Entertainment, Healthcare, Education, Travel, Other.
    6. source: Merchant or bank name.
    7. confidence: Your confidence in this extraction (0.0 to 1.0).
    
    Return a JSON array of transaction objects. Each object must have these exact field names.
    If there is only one transaction, return an array with one object.
    If a field cannot be determined for a transaction, use null for that field.
    """
    
    # Build user prompt
    user_prompt = f"""Extract financial data from this {source} transaction text:

Text content:
{truncated_text}

Additional context:
- Sender: {sender}
- Source tag: {sender_tag}
- Original filename: {source_info.get('filename', 'unknown')}

Return a JSON array of transaction objects with fields: date, amount, currency, expense_name, expense_type, source, confidence.
If there are multiple transactions, include all of them. If only one, return an array with one object."""
    
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
        
        # Handle both single transaction object and array of transactions
        transactions = []
        if isinstance(parsed, list):
            # LLM returned an array of transactions
            for i, tx in enumerate(parsed):
                if not isinstance(tx, dict):
                    logger.warning(f"Transaction {i} is not a dictionary, skipping")
                    continue
                # Validate required fields
                required_fields = ['date', 'amount', 'currency', 'expense_name', 'expense_type', 'source', 'confidence']
                for field in required_fields:
                    if field not in tx:
                        tx[field] = None
                # Validate and normalize each transaction
                validated_tx = _validate_and_normalize_transaction(tx, source_info)
                # Add metadata
                validated_tx['raw_text_snippet'] = text[:200]
                validated_tx['parsed_at'] = datetime.now().isoformat()
                validated_tx['llm_model'] = 'gpt-4o-mini'
                validated_tx['parsing_method'] = 'openai'
                transactions.append(validated_tx)
        elif isinstance(parsed, dict):
            # LLM returned a single transaction object (old format)
            # Validate required fields
            required_fields = ['date', 'amount', 'currency', 'expense_name', 'expense_type', 'source', 'confidence']
            for field in required_fields:
                if field not in parsed:
                    parsed[field] = None
            # Validate and normalize
            validated_tx = _validate_and_normalize_transaction(parsed, source_info)
            # Add metadata
            validated_tx['raw_text_snippet'] = text[:200]
            validated_tx['parsed_at'] = datetime.now().isoformat()
            validated_tx['llm_model'] = 'gpt-4o-mini'
            validated_tx['parsing_method'] = 'openai'
            transactions.append(validated_tx)
        else:
            raise ReceiptParsingError(f"Unexpected JSON response type: {type(parsed)}")
        
        if not transactions:
            raise ReceiptParsingError("No valid transactions extracted from text")
        
        logger.info(f"Successfully parsed {len(transactions)} transaction(s)")
        return transactions
        
    except Exception as e:
        raise ReceiptParsingError(f"OpenAI API error: {e}")


def _parse_with_heuristics(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fallback heuristic parsing when LLM is unavailable.
    
    Args:
        text: Text content.
        source_info: Source metadata.
    
    Returns:
        List of parsed structured data (multiple transactions if possible).
    """
    logger.info("Using heuristic fallback parsing")
    
    # First attempt to extract multiple transactions
    transactions = _extract_multiple_transactions_heuristic(text, source_info)
    if transactions:
        logger.info(f"Heuristic multi-transaction extraction found {len(transactions)} transaction(s)")
        # Validate and normalize each transaction
        validated_transactions = []
        for tx in transactions:
            validated = _validate_and_normalize_transaction(tx, source_info)
            validated_transactions.append(validated)
        return validated_transactions
    
    # Fallback to single transaction extraction
    logger.info("No multiple transactions found, falling back to single transaction extraction")
    single_tx = _extract_single_transaction_heuristic(text, source_info)
    validated = _validate_and_normalize_transaction(single_tx, source_info)
    logger.info(f"Heuristic parsing result: {validated.get('expense_name')} - {validated.get('amount')}")
    return [validated]


def _extract_multiple_transactions_heuristic(text: str, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Attempt to extract multiple transactions from text using heuristic patterns.
    Returns empty list if no transaction patterns found.
    """
    # Determine source
    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag:
        source = "HSBC Bank"
    elif 'fubon' in sender_tag:
        source = "Fubon Bank"
    elif 'esunbank' in sender_tag:
        source = "Esun Bank"
    
    # Common date patterns (simplified)
    date_patterns = [
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',  # YYYY-MM-DD, YYYY/MM/DD
        r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',  # DD-MM-YYYY, DD/MM/YYYY
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',     # Chinese date format
        r'(\d{1,2})[/](\d{1,2})',               # MM/DD or DD/MM (ambiguous)
    ]
    
    # Amount patterns with currency
    amount_patterns = [
        r'[NT$US$S$HK$¥€£]?\s*([0-9,]+\.?[0-9]*)\s*[元美元新幣港幣]?',
        r'([0-9,]+\.?[0-9]*)\s*(NTD|USD|SGD|HKD|TWD)',
        r'金額[：:]\s*([0-9,]+\.?[0-9]*)',
        r'Amount[：:]\s*([0-9,]+\.?[0-9]*)',
    ]
    
    # Split text into lines
    lines = text.split('\n')
    transactions = []
    
    for line_num, line in enumerate(lines):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        
        # Skip lines that are obviously headers/footers
        if any(keyword in line.lower() for keyword in ['statement', 'total', 'summary', 'balance', 'page', 'date', 'description', 'amount']):
            continue
        
        # Look for date and amount in the same line
        date_match = None
        date_str = None
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                date_match = match
                # Try to format date
                try:
                    if '年' in pattern:
                        year, month, day = match.groups()
                    elif len(match.group(1)) == 4:
                        year, month, day = match.groups()
                    elif len(match.group(1)) <= 2 and len(match.group(2)) <= 2:
                        # MM/DD or DD/MM, assume current year? Use first two groups as month/day
                        month, day = match.groups()[:2]
                        year = str(datetime.now().year)
                    else:
                        continue
                    date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                    break
                except (ValueError, IndexError):
                    continue
        
        amount_match = None
        amount_val = None
        currency = None
        for pattern in amount_patterns:
            matches = re.findall(pattern, line)
            if matches:
                # Take the first amount that looks reasonable
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    clean = match.replace(',', '')
                    if clean.replace('.', '', 1).isdigit():
                        amount_val = float(clean)
                        # Determine currency
                        if 'NT$' in line or 'TWD' in line:
                            currency = 'TWD'
                        elif 'US$' in line or 'USD' in line:
                            currency = 'USD'
                        elif 'S$' in line or 'SGD' in line:
                            currency = 'SGD'
                        elif 'HK$' in line or 'HKD' in line:
                            currency = 'HKD'
                        else:
                            # Default based on source
                            if 'sg' in sender_tag:
                                currency = 'SGD'
                            elif 'tw' in sender_tag:
                                currency = 'TWD'
                            elif 'hk' in sender_tag:
                                currency = 'HKD'
                            else:
                                currency = 'USD'
                        break
                if amount_val:
                    break
        
        # If we found both date and amount, consider it a transaction
        if date_str and amount_val:
            # Extract description: the line itself, maybe remove date and amount parts
            desc = line
            # Optional: clean up date and amount patterns from desc
            # For now keep as is
            
            # Determine expense type based on keywords
            expense_type = 'Other'
            text_lower = line.lower()
            expense_keywords = {
                'Food': ['food', 'restaurant', 'meal', '咖啡', '餐廳', '小吃', '早餐', '午餐', '晚餐'],
                'Transportation': ['transport', 'uber', 'taxi', 'metro', 'mrt', 'bus', 'gas', 'fuel', '加油', '交通'],
                'Shopping': ['shopping', 'store', 'market', 'purchase', 'buy', 'amazon', 'shop', '購物', '商城'],
                'Bills': ['bill', 'payment', 'utility', 'electric', 'water', 'phone', 'internet', '信用卡', '帳單', '繳費'],
                'Entertainment': ['movie', 'cinema', 'concert', 'game', 'netflix', 'spotify', '娛樂', '電影', '音樂'],
                'Healthcare': ['medical', 'hospital', 'clinic', 'pharmacy', 'doctor', 'health', '醫療', '醫院', '藥局'],
                'Travel': ['travel', 'flight', 'hotel', 'airbnb', 'vacation', 'trip', '旅遊', '飯店', '機票'],
            }
            for cat, keywords in expense_keywords.items():
                if any(keyword in text_lower for keyword in keywords):
                    expense_type = cat
                    break
            
            transaction = {
                'date': date_str,
                'amount': amount_val,
                'currency': currency,
                'expense_name': desc[:100],  # truncate
                'expense_type': expense_type,
                'source': source,
                'confidence': 0.5,  # moderate confidence for heuristic multi
                'raw_text_snippet': line[:200],
                'parsed_at': datetime.now().isoformat(),
                'llm_model': None,
                'parsing_method': 'heuristic'
            }
            transactions.append(transaction)
    
    return transactions


def _extract_single_transaction_heuristic(text: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Original single transaction heuristic extraction.
    Returns a single transaction dict (not list).
    """
    sender_tag = source_info.get('sender_tag', 'unknown')
    source = "unknown"
    if 'hsbc' in sender_tag:
        source = "HSBC Bank"
    elif 'fubon' in sender_tag:
        source = "Fubon Bank"
    elif 'esunbank' in sender_tag:
        source = "Esun Bank"
    
    result = {
        'date': None,
        'amount': None,
        'currency': None,
        'expense_name': 'Bank Statement Transaction',
        'expense_type': 'Bills',
        'source': source,
        'confidence': 0.3,
        'raw_text_snippet': text[:200],
        'parsed_at': datetime.now().isoformat(),
        'llm_model': None,
        'parsing_method': 'heuristic'
    }
    
    # Date extraction (simplified)
    date_patterns = [
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
        r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text[:1000])
        if match:
            try:
                if '年' in pattern:
                    year, month, day = match.groups()
                elif len(match.group(1)) == 4:
                    year, month, day = match.groups()
                else:
                    day, month, year = match.groups()
                result['date'] = f"{year}-{int(month):02d}-{int(day):02d}"
                result['confidence'] = min(result['confidence'] + 0.2, 0.8)
                break
            except (ValueError, IndexError):
                continue
    
    # Amount extraction (simplified)
    amount_patterns = [
        r'[NT$US$S$HK$¥€£]?\s*([0-9,]+\.?[0-9]*)\s*[元美元新幣港幣]?',
        r'([0-9,]+\.?[0-9]*)\s*[NTD|USD|SGD|HKD|TWD]',
    ]
    for pattern in amount_patterns:
        matches = re.findall(pattern, text[:2000])
        if matches:
            try:
                amounts = []
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    clean = match.replace(',', '')
                    if clean.replace('.', '', 1).isdigit():
                        amounts.append(float(clean))
                if amounts:
                    result['amount'] = max(amounts)
                    result['confidence'] = min(result['confidence'] + 0.2, 0.8)
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
    
    if result['amount'] is None:
        decimal_pattern = r'\b([0-9,]+\.?[0-9]{2})\b'
        matches = re.findall(decimal_pattern, text[:1500])
        if matches:
            try:
                amounts = []
                for match in matches:
                    clean = match.replace(',', '')
                    if clean.replace('.', '', 1).isdigit():
                        amount = float(clean)
                        if 10 <= amount <= 100000:
                            amounts.append(amount)
                if amounts:
                    result['amount'] = max(amounts)
                    result['confidence'] = min(result['confidence'] + 0.1, 0.7)
                    result['currency'] = 'TWD'
            except (ValueError, TypeError):
                pass
    
    # Expense type
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
    
    return result


def _validate_and_normalize_transaction(parsed: Dict[str, Any], source_info: Dict[str, Any]) -> Dict[str, Any]:
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
        List of parsed transactions (flattened from all texts).
    """
    if source_infos is None:
        source_infos = [{} for _ in range(len(texts))]
    
    if len(texts) != len(source_infos):
        raise ValueError("Number of texts must match number of source_infos")
    
    all_transactions = []
    for i, (text, source_info) in enumerate(zip(texts, source_infos)):
        try:
            transactions = parse_receipt_text(text, source_info)
            all_transactions.extend(transactions)
            logger.info(f"Parsed {i+1}/{len(texts)} receipts ({len(transactions)} transactions)")
        except ReceiptParsingError as e:
            logger.error(f"Failed to parse receipt {i+1}: {e}")
            # Add error entry as a transaction-like object with error flag
            all_transactions.append({
                'error': str(e),
                'text_index': i,
                'parsed_at': datetime.now().isoformat(),
                'expense_name': f'Error parsing receipt {i+1}',
                'expense_type': 'Other',
                'confidence': 0.0
            })
    
    return all_transactions


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