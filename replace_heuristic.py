#!/usr/bin/env python3
import re
import sys

with open('src/llm/parse_receipt.py', 'r') as f:
    content = f.read()

# Find the heuristic function using its signature
pattern = r'(def _parse_with_heuristics\(text: str, source_info: Dict\[str, Any\]\) -> List\[Dict\[str, Any\]\]:.*?\n    return \[validated_result\])'
# Since the function is large, we need to match across lines with DOTALL flag
match = re.search(pattern, content, re.DOTALL)
if not match:
    print("ERROR: Could not find heuristic function")
    sys.exit(1)

old_func = match.group(0)
print(f"Found heuristic function ({len(old_func)} chars)")

# Read new function content
with open('/home/zh/.openclaw/workspace-developer/new_heuristic_func.txt', 'r') as f:
    new_func = f.read()

# Replace old with new
new_content = content.replace(old_func, new_func)
print(f"Replaced heuristic function")

# Write back
with open('src/llm/parse_receipt.py', 'w') as f:
    f.write(new_content)

print("Successfully updated parse_receipt.py")