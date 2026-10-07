"""Focused tests for utility enhancements (Issue #23 legacy coverage)."""

from __future__ import annotations

from src.support.retry import APIRetry, RetryConfig


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
