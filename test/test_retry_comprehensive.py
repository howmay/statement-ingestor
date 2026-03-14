"""
Comprehensive tests for the current retry.py public API.
"""
import pytest
from unittest.mock import Mock, patch

from src.support.retry import (
    RetryConfig,
    APIRetry,
    retry_decorator,
    retry_gmail,
    retry_generic,
    retry_openai,
)


class TestRetryConfigComprehensive:
    def test_default_config(self):
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.retry_on_exceptions == (Exception,)
        assert config.retry_on_status_codes == []
        assert config.retry_on_conditions == []

    def test_custom_config(self):
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False,
            retry_on_exceptions=(ValueError, TypeError),
            retry_on_status_codes=[429, 500],
        )

        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 3.0
        assert config.jitter is False
        assert config.retry_on_exceptions == (ValueError, TypeError)
        assert config.retry_on_status_codes == [429, 500]

    def test_calculate_delay_without_jitter(self):
        config = RetryConfig(base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=False)

        assert config.calculate_delay(0) == 1.0
        assert config.calculate_delay(1) == 2.0
        assert config.calculate_delay(2) == 4.0
        assert config.calculate_delay(10) == 10.0

    def test_should_retry_uses_status_code_filter(self):
        class Response:
            status_code = 404

        config = RetryConfig(retry_on_status_codes=[429, 500], retry_on_exceptions=(Exception,))

        assert config.should_retry(Exception("boom"), Response()) is False


class TestAPIRetryComprehensive:
    def test_execute_retries_then_succeeds(self):
        retry = APIRetry(RetryConfig(max_retries=3, jitter=False, retry_on_exceptions=(ValueError,)))
        func = Mock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])

        with patch("time.sleep") as mock_sleep:
            result = retry.execute(func, "arg", kwarg="value")

        assert result == "ok"
        assert func.call_count == 3
        assert func.call_args_list[0].args == ("arg",)
        assert func.call_args_list[0].kwargs == {"kwarg": "value"}
        assert mock_sleep.call_count == 2

    def test_execute_does_not_retry_non_retryable_exception(self):
        retry = APIRetry(RetryConfig(retry_on_exceptions=(ValueError,), jitter=False))
        func = Mock(side_effect=RuntimeError("stop"))

        with pytest.raises(RuntimeError, match="stop"):
            retry.execute(func)

        func.assert_called_once()

    def test_execute_retries_http_error_response_until_exhausted(self):
        retry = APIRetry(RetryConfig(max_retries=3, retry_on_status_codes=[500], jitter=False))

        class Response:
            status_code = 500
            reason = "Internal Server Error"

        func = Mock(return_value=Response())

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(Exception, match="HTTP 500"):
                retry.execute(func)

        assert func.call_count == 3
        assert mock_sleep.call_count == 2

    def test_retry_decorator_uses_supplied_config(self):
        config = RetryConfig(max_retries=2, base_delay=0.1, jitter=False, retry_on_exceptions=(ValueError,))
        call_count = 0

        @retry_decorator(config=config)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("transient")
            return "done"

        with patch("time.sleep") as mock_sleep:
            assert flaky() == "done"

        assert call_count == 2
        mock_sleep.assert_called_once_with(0.1)

    def test_convenience_decorators_return_wrapped_results(self):
        @retry_gmail
        def gmail_func():
            return "gmail"

        @retry_openai
        def openai_func():
            return "openai"

        @retry_generic
        def generic_func():
            return "generic"

        assert gmail_func() == "gmail"
        assert openai_func() == "openai"
        assert generic_func() == "generic"
