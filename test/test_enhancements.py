"""Focused tests for utility enhancements (Issue #23 legacy coverage)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.support.config_validator import ConfigValidator
from src.support.retry import APIRetry, RetryConfig


def test_config_validator_env_and_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        env_file = root / '.env'
        env_file.write_text(
            'TARGET_SENDERS=test@example.com\n'
            'TARGET_KEYWORDS=receipt\n'
            'OPENAI_API_KEY=test_key_12345678901234567890\n'
            'BANK_PASSWORDS=pass1\n'
            'OAUTH_PORT=8080\n'
        )

        config_dir = root / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)
        client_secrets = {
            'installed': {
                'client_id': 'test-client.apps.googleusercontent.com',
                'client_secret': 'secret',
                'redirect_uris': ['http://localhost:8080'],
            }
        }
        (config_dir / 'client_secrets.json').write_text(json.dumps(client_secrets))

        validator = ConfigValidator(str(root))
        env_values = validator.load_environment()
        # runtime environment may override .env values; verify presence instead of exact value
        assert 'TARGET_SENDERS' in env_values

        env_results = validator.validate_environment()
        assert any(var == 'TARGET_SENDERS' and status == 'OK' for var, status, _ in env_results)

        file_results = validator.validate_files()
        assert any('client_secrets.json' in path and status == 'OK' for path, status, _ in file_results)



def test_retry_executes_until_success():
    cfg = RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.05, jitter=False)
    retry = APIRetry(cfg)

    calls = {'n': 0}

    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise Exception('transient')
        return 'ok'

    result = retry.execute(flaky)
    assert result == 'ok'
    assert calls['n'] == 3
