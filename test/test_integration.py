"""Integration-oriented smoke tests for project architecture."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_core_modules_importable():
    modules = [
        'src.support.logger',
        'src.support.retry',
        'src.support.progress',
        'src.support.config_validator',
        'src.runtime.app',
    ]

    for name in modules:
        mod = importlib.import_module(name)
        assert mod is not None



def test_main_entrypoint_exists():
    project_root = Path(__file__).resolve().parent.parent
    content = (project_root / 'main.py').read_text()
    assert 'def main()' in content



def test_refactored_app_class_exists():
    project_root = Path(__file__).resolve().parent.parent
    content = (project_root / 'src' / 'runtime' / 'app.py').read_text()
    assert 'class GmailExpenseParserApp' in content
