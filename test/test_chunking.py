#!/usr/bin/env python3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.llm.parse_receipt import _should_enable_chunking, _chunk_text_by_transactions

# Test 1: Should enable chunking for large HSBC text
text = 'HSBC' * 2000
source_info = {'sender_tag': 'hsbc'}
print(f'Test 1 - Large HSBC text: {_should_enable_chunking(text, source_info)}')

# Test 2: Should not enable chunking for small text
text = 'Small text'
print(f'Test 2 - Small text: {_should_enable_chunking(text, source_info)}')

# Test 3: Test chunking
text = '\n'.join([f'2024-01-{i:02d} NT${i*100}.00 Transaction {i}' for i in range(1, 31)])
chunks = _chunk_text_by_transactions(text, max_chunk_size=500)
print(f'Test 3 - Chunks created: {len(chunks)}')
for i, (chunk_text, indices) in enumerate(chunks):
    print(f'  Chunk {i+1}: {len(chunk_text)} chars, {len(indices)} transactions')