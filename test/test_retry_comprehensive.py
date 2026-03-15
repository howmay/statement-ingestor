"""
Comprehensive tests for retry.py to improve coverage to 85%.
Focuses on edge cases and uncovered lines.
"""
import time
import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.support.retry import (
    RetryConfig,
    APIRetry,
    retry_on_exception,
    retry_on_status_code,
    retry_gmail
)


class TestRetryConfigComprehensive:
    """Comprehensive tests for RetryConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.jitter is True
        assert config.retry_on_exceptions == (Exception,)
        assert config.retry_on_status_codes == []
        assert config.exponential_base == 2.0
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=60.0,
            jitter=0.2,
            retry_exceptions=(ValueError, TypeError),
            retry_status_codes={400, 401, 403},
            backoff_factor=1.5
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.jitter == 0.2
        assert config.retry_exceptions == (ValueError, TypeError)
        assert config.retry_status_codes == {400, 401, 403}
        assert config.backoff_factor == 1.5
    
    def test_calculate_delay_no_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(jitter=0.0)
        
        # First attempt (attempt=0)
        delay = config.calculate_delay(0)
        assert delay == config.base_delay
        
        # Second attempt (attempt=1)
        delay = config.calculate_delay(1)
        assert delay == config.base_delay * config.backoff_factor
        
        # Third attempt (attempt=2)
        delay = config.calculate_delay(2)
        expected = config.base_delay * (config.backoff_factor ** 2)
        assert delay == expected
    
    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(jitter=0.1)
        
        with patch('random.uniform') as mock_uniform:
            mock_uniform.return_value = 1.05  # 5% increase
            
            delay = config.calculate_delay(0)
            
            # Should apply jitter: base_delay * 1.05
            expected = config.base_delay * 1.05
            assert delay == expected
            mock_uniform.assert_called_with(0.9, 1.1)  # 1.0 ± 10%
    
    def test_calculate_delay_capped_at_max(self):
        """Test delay calculation capped at max_delay."""
        config = RetryConfig(base_delay=10.0, max_delay=15.0, backoff_factor=2.0, jitter=False)
        
        # First attempt: 10.0 < 15.0
        delay = config.calculate_delay(0)
        assert delay == 10.0
        
        # Second attempt: 20.0 > 15.0, should be capped
        delay = config.calculate_delay(1)
        assert delay == 15.0
        
        # Third attempt: also capped
        delay = config.calculate_delay(2)
        assert delay == 15.0
    
    def test_should_retry_exception_type(self):
        """Test should_retry for exception types."""
        config = RetryConfig(retry_exceptions=(ValueError, TypeError))
        
        # Should retry ValueError
        assert config.should_retry(ValueError("test")) is True
        
        # Should retry TypeError
        assert config.should_retry(TypeError("test")) is True
        
        # Should not retry other exceptions
        assert config.should_retry(KeyError("test")) is False
        
        # Should retry Exception when using default config
        default_config = RetryConfig()
        assert default_config.should_retry(Exception("test")) is True
    
    def test_should_retry_status_code(self):
        """Test should_retry for status codes."""
        config = RetryConfig(retry_status_codes={429, 500})
        
        # Mock HTTPError with status code
        class MockHTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
        
        # Should retry 429
        assert config.should_retry(MockHTTPError(429)) is True
        
        # Should retry 500
        assert config.should_retry(MockHTTPError(500)) is True
        
        # Should not retry 404
        assert config.should_retry(MockHTTPError(404)) is False
        
        # Exception without status_code attribute
        assert config.should_retry(ValueError("test")) is True  # Falls back to exception type check
    
    def test_should_retry_with_response_object(self):
        """Test should_retry with response object."""
        config = RetryConfig(retry_status_codes={429, 500})
        
        # Mock response object
        class MockResponse:
            def __init__(self, status_code):
                self.status_code = status_code
        
        # Should retry 429
        assert config.should_retry(MockResponse(429)) is True
        
        # Should retry 500
        assert config.should_retry(MockResponse(500)) is True
        
        # Should not retry 200
        assert config.should_retry(MockResponse(200)) is False


class TestAPIRetryComprehensive:
    """Comprehensive tests for APIRetry."""
    
    def test_successful_call(self):
        """Test successful API call without retries."""
        retry = APIRetry()
        
        mock_func = Mock(return_value="success")
        
        result = retry.execute(mock_func)
        
        assert result == "success"
        mock_func.assert_called_once()
    
    def test_retry_on_exception_success(self):
        """Test retry on exception that eventually succeeds."""
        retry = APIRetry(max_attempts=3)
        
        # Function fails twice then succeeds
        mock_func = Mock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])
        
        with patch('time.sleep') as mock_sleep:
            result = retry.execute(mock_func)
            
            assert result == "success"
            assert mock_func.call_count == 3
            assert mock_sleep.call_count == 2  # Sleep before 2nd and 3rd attempts
    
    def test_no_retry_on_non_retryable_exception(self):
        """Test no retry on non-retryable exception."""
        retry = APIRetry(retry_exceptions=(ValueError,))
        
        # Function raises non-retryable exception
        mock_func = Mock(side_effect=KeyError("not retryable"))
        
        with pytest.raises(KeyError, match="not retryable"):
            retry.execute(mock_func)
        
        # Should not retry
        mock_func.assert_called_once()
    
    def test_retry_gives_up_after_max_attempts(self):
        """Test retry gives up after max attempts."""
        retry = APIRetry(max_attempts=2)
        
        # Function always fails
        mock_func = Mock(side_effect=ValueError("always fails"))
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(ValueError, match="always fails"):
                retry.execute(mock_func)
            
            # Should have tried max_attempts times
            assert mock_func.call_count == 2
            assert mock_sleep.call_count == 1  # Sleep before 2nd attempt
    
    def test_http_status_code_retry(self):
        """Test retry on HTTP status codes."""
        retry = APIRetry(retry_status_codes={429, 500})
        
        # Mock HTTPError
        class MockHTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
        
        # Function returns error with retryable status code, then succeeds
        mock_func = Mock(side_effect=[MockHTTPError(429), "success"])
        
        with patch('time.sleep') as mock_sleep:
            result = retry.execute(mock_func)
            
            assert result == "success"
            assert mock_func.call_count == 2
            mock_sleep.assert_called_once()
    
    def test_retry_with_custom_config(self):
        """Test retry with custom configuration."""
        config = RetryConfig(
            max_attempts=2,
            base_delay=0.1,
            retry_exceptions=(RuntimeError,),
            jitter=False,
        )
        retry = APIRetry(config=config)
        
        # Function fails once then succeeds
        mock_func = Mock(side_effect=[RuntimeError("fail"), "success"])
        
        with patch('time.sleep') as mock_sleep:
            result = retry.execute(mock_func)
            
            assert result == "success"
            assert mock_func.call_count == 2
            # Should sleep with custom base_delay
            mock_sleep.assert_called_with(0.1)
    
    def test_retry_with_function_args(self):
        """Test retry with function arguments."""
        retry = APIRetry()
        
        mock_func = Mock(side_effect=[ValueError("fail"), "success"])
        
        with patch('time.sleep'):
            result = retry.execute(mock_func, "arg1", "arg2", kwarg1="value1")
            
            assert result == "success"
            # Should pass arguments to function
            mock_func.assert_has_calls([
                call("arg1", "arg2", kwarg1="value1"),
                call("arg1", "arg2", kwarg1="value1")
            ])
    
    def test_retry_logging(self):
        """Test retry logging."""
        retry = APIRetry(max_attempts=2)
        
        mock_func = Mock(side_effect=[ValueError("fail"), "success"])
        
        with patch('time.sleep'):
            with patch('logging.getLogger') as mock_get_logger:
                mock_logger = Mock()
                mock_get_logger.return_value = mock_logger
                
                result = retry.execute(mock_func)
                
                # Should log retry attempts
                assert mock_logger.warning.call_count >= 1
    
    def test_convenience_decorators(self):
        """Test convenience decorators."""
        # Test retry_on_exception decorator
        @retry_on_exception(max_attempts=2)
        def failing_func():
            raise ValueError("test")
        
        with patch('time.sleep'):
            with pytest.raises(ValueError):
                failing_func()
        
        # Test retry_on_status_code decorator
        @retry_on_status_code(max_attempts=2)
        def http_error_func():
            class MockHTTPError(Exception):
                def __init__(self):
                    self.status_code = 429
            raise MockHTTPError()
        
        with patch('time.sleep'):
            with pytest.raises(Exception):
                http_error_func()
    
    def test_retry_decorator_with_custom_config(self):
        """Test retry decorator with custom config."""
        config = RetryConfig(max_attempts=1, jitter=False)
        
        @retry_on_exception(config=config)
        def func():
            raise ValueError("test")
        
        # With max_attempts=1, should not retry
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(ValueError):
                func()
            
            # Should not sleep (no retry)
            mock_sleep.assert_not_called()
    
    def test_retry_gmail_decorator(self):
        """Test retry_gmail decorator."""
        @retry_gmail
        def gmail_func():
            return "gmail success"
        
        result = gmail_func()
        assert result == "gmail success"
        
        # Test with failure
        call_count = 0
        
        @retry_gmail
        def failing_gmail_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("gmail error")
            return "success"
        
        with patch('time.sleep'):
            result = failing_gmail_func()
            assert result == "success"
            assert call_count == 2
    
    def test_execute_with_none_return(self):
        """Test execute with function that returns None."""
        retry = APIRetry()
        
        mock_func = Mock(return_value=None)
        
        result = retry.execute(mock_func)
        
        assert result is None
        mock_func.assert_called_once()
    
    def test_execute_with_complex_return_value(self):
        """Test execute with complex return value."""
        retry = APIRetry()
        
        complex_result = {"data": [1, 2, 3], "status": "ok"}
        mock_func = Mock(return_value=complex_result)
        
        result = retry.execute(mock_func)
        
        assert result == complex_result
        mock_func.assert_called_once()
    
    def test_should_retry_with_mixed_exception_types(self):
        """Test should_retry with mixed exception inheritance."""
        class CustomError(ValueError):
            pass
        
        config = RetryConfig(retry_exceptions=(ValueError,))
        
        # CustomError inherits from ValueError, should be retryable
        assert config.should_retry(CustomError("test")) is True
        
        class OtherError(Exception):
            pass
        
        # OtherError doesn't inherit from ValueError, should not be retryable
        assert config.should_retry(OtherError("test")) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
