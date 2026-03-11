"""Backward-compatible parser factory wrapper.

This module keeps the old import path (`src.parser_factory.get_parser`) while
routing to the new deterministic bank parser implementations.
"""

from typing import Any, Dict, Optional

from src.bank_parsers.factory import get_bank_parser


class NullParser:
    """Fallback parser object for non-bank sources."""

    def parse(self):
        return []


def get_parser(sender: str, raw_text: str, source_info: Optional[Dict[str, Any]] = None):
    source_info = source_info or {}
    if sender and not source_info.get('sender'):
        source_info['sender'] = sender

    parser = get_bank_parser(raw_text, source_info)
    if parser is None:
        return NullParser()
    return parser
