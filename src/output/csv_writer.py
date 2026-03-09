import csv
import os
import json
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def export_receipts_to_csv(receipts: List[Dict[str, Any]], output_dir: str = "output") -> str:
    """
    Export parsed receipts to CSV file.
    
    Args:
        receipts: List of parsed receipt dictionaries.
        output_dir: Directory to save CSV file.
    
    Returns:
        Path to the created CSV file, or empty string if no data.
    
    Raises:
        OSError: If file cannot be written.
    """
    if not receipts:
        logger.warning("No receipts to export")
        return ""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"expenses_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)
    
    # Define column order and mapping (for display purposes)
    # We'll include all available fields from the receipts
    field_mapping = {
        # Core fields (from specification)
        'date': '日期',
        'amount': '金額',
        'currency': '幣別',
        'expense_name': '消費名目',
        'expense_type': '類型',
        'source': '來源',
        
        # Additional fields from parsing
        'confidence': '信心度',
        'original_file': '原始檔案',
        'sender_tag': '寄件人標籤',
        'parsed_at': '解析時間',
        'llm_model': 'LLM模型',
        'parsing_method': '解析方法',
        'raw_text_snippet': '原始文字片段',
    }
    
    # Determine all fields that exist in the receipts
    all_fields = set()
    for receipt in receipts:
        all_fields.update(receipt.keys())
    
    # Create ordered field list: core fields first, then others
    ordered_fields = []
    field_display_names = []
    
    # Add core fields in order (if they exist in data)
    for field, display_name in field_mapping.items():
        if field in all_fields:
            ordered_fields.append(field)
            field_display_names.append(display_name)
    
    # Add any remaining fields not in mapping
    for field in sorted(all_fields):
        if field not in ordered_fields:
            ordered_fields.append(field)
            # Use field name as display name if not in mapping
            field_display_names.append(field)
    
    # Write CSV file
    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=ordered_fields)
            
            # Write header with display names
            writer.writerow(dict(zip(ordered_fields, field_display_names)))
            
            # Write data rows
            for receipt in receipts:
                # Create row with all fields, using empty string for missing
                row = {}
                for field in ordered_fields:
                    value = receipt.get(field)
                    
                    # Handle special formatting
                    if value is None:
                        row[field] = ''
                    elif isinstance(value, float):
                        # Format float to 2 decimal places
                        row[field] = f"{value:.2f}"
                    elif isinstance(value, dict) or isinstance(value, list):
                        # Convert dict/list to JSON string
                        try:
                            row[field] = json.dumps(value, ensure_ascii=False)
                        except:
                            row[field] = str(value)
                    else:
                        row[field] = str(value)
                
                writer.writerow(row)
        
        logger.info(f"Exported {len(receipts)} receipts to CSV: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        raise


def format_receipt_for_csv(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a receipt dictionary for CSV export.
    
    Args:
        receipt: Parsed receipt dictionary.
    
    Returns:
        Formatted receipt with cleaned values.
    """
    formatted = receipt.copy()
    
    # Format float amounts to 2 decimal places
    if 'amount' in formatted and isinstance(formatted['amount'], (int, float)):
        formatted['amount'] = f"{formatted['amount']:.2f}"
    
    # Format confidence as percentage
    if 'confidence' in formatted and isinstance(formatted['confidence'], (int, float)):
        formatted['confidence'] = f"{formatted['confidence']:.1%}"
    
    # Ensure all values are strings for CSV
    for key, value in formatted.items():
        if value is None:
            formatted[key] = ''
        elif not isinstance(value, str):
            formatted[key] = str(value)
    
    return formatted


if __name__ == "__main__":
    # Test the CSV writer with sample data
    sample_receipts = [
        {
            'date': '2024-12-25',
            'amount': 350.0,
            'currency': 'TWD',
            'expense_name': 'Uber ride',
            'expense_type': 'Transportation',
            'source': 'Uber',
            'confidence': 0.95,
            'original_file': 'uber_receipt.pdf',
            'sender_tag': 'uber',
            'parsed_at': '2024-12-25T12:30:00',
            'parsing_method': 'openai'
        },
        {
            'date': '2024-12-24',
            'amount': 1299.0,
            'currency': 'TWD',
            'expense_name': 'Amazon purchase',
            'expense_type': 'Shopping',
            'source': 'Amazon',
            'confidence': 0.85,
            'original_file': 'amazon_invoice.pdf',
            'sender_tag': 'amazon',
            'parsed_at': '2024-12-24T15:45:00',
            'parsing_method': 'heuristic'
        }
    ]
    
    print("Testing CSV export...")
    try:
        output_path = export_receipts_to_csv(sample_receipts, "test_output")
        print(f"✓ CSV exported to: {output_path}")
        
        # Display first few lines
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            print("\nFirst 3 lines of CSV:")
            for i, line in enumerate(lines[:3]):
                print(f"  {i+1}: {line.strip()}")
                
    except Exception as e:
        print(f"✗ Error: {e}")