"""
Unit tests for retry utility.
"""
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from functools import wraps
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.utils.retry import (
    RetryConfig,
    APIRetry,
    retry_decorator,
    retry_gmail,
    retry_openai,
    retry_generic
)


class TestRetryConfig:
    """Test suite for RetryConfig."""
    
    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.retry_on_exceptions == (Exception,)
        assert config.retry_on_status_codes is None or config.retry_on_status_codes == []
        assert config.retry_on_conditions == []
    
    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False,
            retry_on_exceptions=(ValueError, TypeError)
        )
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 3.0
        assert config.jitter is False
        assert config.retry_on_exceptions == (ValueError, TypeError)
    
    def test_calculate_delay(self):
        """Test delay calculation."""
        config = RetryConfig(base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=False)
        
        # First attempt (0): 1.0 * (2^0) = 1.0
        delay0 = config.calculate_delay(0)
        assert delay0 == 1.0
        
        # Second attempt (1): 1.0 * (2^1) = 2.0
        delay1 = config.calculate_delay(1)
        assert delay1 == 2.0
        
        # Third attempt (2): 1.0 * (2^2) = 4.0
        delay2 = config.calculate_delay(2)
        assert delay2 == 4.0
        
        # High attempt should be capped at max_delay
        delay_high = config.calculate_delay(10)
        assert delay_high == 10.0
    
    def test_calculate_delay_with_jitter(self):
        """Test that jitter adds randomness."""
        config = RetryConfig(base_delay=1.0, max_delay=100.0, exponential_base=2.0, jitter=True)
        delays = [config.calculate_delay(0) for _ in range(10)]
        # base_delay=1.0, (0.5 + random()) in [0.5, 1.5)
        # So delays should be in [0.5, 1.5)
        for d in delays:
            assert 0.5 <= d < 1.5
        # Check that there is variance (i.e., not all same)
        assert len(set(delays)) > 1  # At least two distinct values
    
    def test_should_retry_exception_type(self):
        """Test retry decision based on exception type."""
        config = RetryConfig(retry_on_exceptions=(ValueError, TypeError))
        
        # Should retry ValueError
        assert config.should_retry(ValueError("test")) is True
        
        # Should NOT retry RuntimeError
        assert config.should_retry(RuntimeError("test")) is False
        
        # Default (Exception tuple) should retry most exceptions
        default_config = RetryConfig()
        assert default_config.should_retry(Exception("test")) is True
        assert default_config.should_retry(ValueError("test")) is True
    
    def test_should_retry_status_code(self):
        """Test retry decision based on status code."""
        # Create a config that retries on 429, 500
        config = RetryConfig(retry_on_status_codes=[429, 500, 502])
        
        # Mock response with status code
        class MockResponse:
            status_code = 429
        
        # Should retry on 429
        assert config.should_retry(Exception("test"), MockResponse()) is True
        
        # Should NOT retry on 404 (not in list)
        MockResponse.status_code = 404
        assert config.should_retry(Exception("test"), MockResponse()) is False
        
        # Should retry on 500
        MockResponse.status_code = 500
        assert config.should_retry(Exception("test"), MockResponse()) is True


class TestAPIRetry:
    """Test suite for APIRetry."""
    
    def test_successful_call(self):
        """Test a successful API call without retries."""
        retry_handler = APIRetry(api_type='generic')
        
        # Mock function that succeeds
        mock_func = Mock(return_value="success")
        
        result = retry_handler.execute(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_retry_on_exception(self):
        """Test retry on transient exception."""
        retry_handler = APIRetry(api_type='generic')
        
        # Mock function that fails twice then succeeds
        mock_func = Mock(side_effect=[Exception("fail"), Exception("fail"), "success"])
        
        result = retry_handler.execute(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_no_retry_on_non_retryable_exception(self):
        """Test that non-retryable exceptions are raised immediately."""
        retry_handler = APIRetry(
            RetryConfig(retry_on_exceptions=(ValueError,)),
            api_type='generic'
        )
        
        mock_func = Mock(side_effect=RuntimeError("non-retryable"))
        
        with pytest.raises(RuntimeError):
            retry_handler.execute(mock_func)
        
        # Should have been called only once (no retries)
        assert mock_func.call_count == 1
    
    def test_retry_gives_up_after_max_attempts(self):
        """Test that retry eventually gives up."""
        retry_handler = APIRetry(
            RetryConfig(max_retries=3, retry_on_exceptions=(Exception,)),
            api_type='generic'
        )
        
        mock_func = Mock(side_effect=Exception("persistent failure"))
        
        with pytest.raises(Exception):
            retry_handler.execute(mock_func)
        
        assert mock_func.call_count == 3  # 3 attempts total
    
    def test_http_status_code_retry(self):
        """Test retry on HTTP status codes."""
        retry_handler = APIRetry(api_type='generic')
        
        # Create a mock response with 500 status
        class MockResponse:
            status_code = 500
            reason = "Internal Server Error"
        
        # Function that returns a failing response
        mock_func = Mock(return_value=MockResponse())
        
        with pytest.raises(Exception):  # Should eventually raise
            retry_handler.execute(mock_func)
        
        # Should have retried multiple times
        assert mock_func.call_count == 3  # default max_retries for generic
    
    def test_convenience_decorators(self):
        """Test convenience retry decorators."""
        # The decorators should return a function with retry logic
        
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
    
    def test_retry_decorator_with_custom_config(self):
        """Test retry_decorator with custom config."""
        config = RetryConfig(max_retries=2, base_delay=0.1)
        
        @retry_decorator(config=config)
        def quick_retry_func():
            raise Exception("fail")
        
        # Should raise after 2 attempts quickly
        start = time.time()
        with pytest.raises(Exception):
            quick_retry_func()
        elapsed = time.time() - start
        # Should be quick (< 1 second) because delays are short
        assert elapsed < 1.0
