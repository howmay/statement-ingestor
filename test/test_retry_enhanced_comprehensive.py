"""
Comprehensive tests for the current retry_enhanced.py public API.
"""
import pytest
from unittest.mock import Mock, patch

from src.support.retry_enhanced import (
    EnhancedRetryConfig,
    EnhancedAPIRetry,
    JSONTruncationError,
    enhanced_retry_decorator,
    enhanced_retry_openai,
)


class TestEnhancedRetryConfigComprehensive:
    def test_default_config(self):
        config = EnhancedRetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.enable_json_truncation_retry is True
        assert config.json_truncation_retry_strategy == "chunk_and_retry"
        assert config.max_json_repair_attempts == 2

    def test_should_retry_detects_json_truncation(self):
        config = EnhancedRetryConfig()
        error = ValueError("truncated JSON")

        assert config.should_retry(error) is True

    def test_calculate_delay_uses_json_multiplier_path(self):
        config = EnhancedRetryConfig(base_delay=2.0, exponential_base=2.0, jitter=False)

        assert config.calculate_delay(0, is_json_truncation=False) == 2.0
        assert config.calculate_delay(1, is_json_truncation=False) == 4.0
        assert config.calculate_delay(1, is_json_truncation=True) == 3.0


class TestEnhancedAPIRetryComprehensive:
    def test_is_truncated_json_helper(self):
        retry = EnhancedAPIRetry(EnhancedRetryConfig(jitter=False))

        assert retry._is_truncated_json('{"x": 1') is True
        assert retry._is_truncated_json('{"x": 1}') is False
        assert retry._is_truncated_json("") is False

    def test_execute_retries_json_truncation_with_chunking_context(self):
        config = EnhancedRetryConfig(
            max_retries=3,
            jitter=False,
            json_truncation_retry_strategy="chunk_and_retry",
        )
        retry = EnhancedAPIRetry(config=config)
        calls = []

        def func(context=None):
            calls.append(dict(context or {}))
            if len(calls) == 1:
                raise JSONTruncationError("JSON response appears truncated")
            return "ok"

        with patch("time.sleep") as mock_sleep:
            result = retry.execute(func)

        assert result == "ok"
        assert calls[0] == {}
        assert calls[1]["force_chunking"] is True
        mock_sleep.assert_called_once()

    def test_execute_retries_json_truncation_with_reduced_text(self):
        config = EnhancedRetryConfig(
            max_retries=3,
            jitter=False,
            json_truncation_retry_strategy="reduce_text",
        )
        retry = EnhancedAPIRetry(config=config)
        seen_texts = []

        def func(text=None, context=None):
            seen_texts.append(text)
            if len(seen_texts) == 1:
                raise JSONTruncationError("JSON response appears truncated")
            return "ok"

        original_text = "A" * 3000

        with patch("time.sleep"):
            result = retry.execute(func, text=original_text)

        assert result == "ok"
        assert seen_texts[0] == original_text
        assert len(seen_texts[1]) < len(original_text)
        assert seen_texts[1].endswith("[Text truncated for retry]")

    def test_execute_raises_non_retryable_exception_immediately(self):
        config = EnhancedRetryConfig(retry_on_exceptions=(ValueError,), jitter=False)
        retry = EnhancedAPIRetry(config=config)
        func = Mock(side_effect=KeyError("stop"))

        with pytest.raises(KeyError, match="stop"):
            retry.execute(func)

        func.assert_called_once()

    def test_enhanced_retry_decorator_retries_then_succeeds(self):
        config = EnhancedRetryConfig(
            max_retries=2,
            jitter=False,
            retry_on_exceptions=(ValueError,),
        )
        call_count = 0

        @enhanced_retry_decorator(config=config)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("transient")
            return "done"

        with patch("time.sleep") as mock_sleep:
            assert flaky() == "done"

        assert call_count == 2
        mock_sleep.assert_called_once()

    def test_enhanced_retry_openai_decorator_handles_success(self):
        @enhanced_retry_openai
        def func():
            return "openai"

        assert func() == "openai"
