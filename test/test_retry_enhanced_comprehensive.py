"""
Comprehensive tests for retry_enhanced.py to improve coverage to 85%.
Focuses on edge cases and uncovered lines.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.support.retry_enhanced import (
    EnhancedRetryConfig,
    EnhancedAPIRetry,
    retry_with_json_truncation,
    is_truncated_json
)


class TestEnhancedRetryConfigComprehensive:
    """Comprehensive tests for EnhancedRetryConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = EnhancedRetryConfig()
        
        # Inherited from RetryConfig
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        
        # Enhanced specific
        assert config.json_truncation_delay_multiplier == 0.5
        assert config.max_json_retries == 2
        assert config.chunk_size_reduction_factor == 0.7
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = EnhancedRetryConfig(
            max_attempts=5,
            base_delay=2.0,
            json_truncation_delay_multiplier=0.3,
            max_json_retries=3,
            chunk_size_reduction_factor=0.5
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.json_truncation_delay_multiplier == 0.3
        assert config.max_json_retries == 3
        assert config.chunk_size_reduction_factor == 0.5
    
    def test_calculate_delay_json_truncation(self):
        """Test delay calculation for JSON truncation retries."""
        config = EnhancedRetryConfig(base_delay=1.0, json_truncation_delay_multiplier=0.5)
        
        # JSON truncation retry should use reduced delay
        delay = config.calculate_delay(0, is_json_truncation=True)
        expected = 1.0 * 0.5  # base_delay * multiplier
        assert delay == expected
        
        # With jitter disabled for test
        config.jitter = 0.0
        delay = config.calculate_delay(1, is_json_truncation=True)
        expected = 1.0 * 2.0 * 0.5  # (base_delay * backoff^attempt) * multiplier
        assert delay == expected
    
    def test_calculate_delay_normal_vs_json(self):
        """Test delay calculation difference between normal and JSON truncation retries."""
        config = EnhancedRetryConfig(base_delay=2.0, json_truncation_delay_multiplier=0.5)
        config.jitter = 0.0  # Disable jitter for predictable test
        
        # Normal retry
        normal_delay = config.calculate_delay(0, is_json_truncation=False)
        
        # JSON truncation retry
        json_delay = config.calculate_delay(0, is_json_truncation=True)
        
        # JSON delay should be half of normal delay
        assert json_delay == normal_delay * 0.5


class TestIsTruncatedJsonComprehensive:
    """Comprehensive tests for is_truncated_json helper."""
    
    def test_is_truncated_json_by_message(self):
        """Test detection by error message."""
        # Messages that indicate truncation
        truncation_messages = [
            "unexpected end of data",
            "truncated",
            "incomplete",
            "unexpected EOF",
            "premature end",
            "JSON parsing error"
        ]
        
        for msg in truncation_messages:
            error = ValueError(msg)
            assert is_truncated_json(error) is True
    
    def test_is_truncated_json_by_response(self):
        """Test detection by response content."""
        # Truncated JSON in response
        truncated_responses = [
            '{"data": [1, 2, 3',  # Missing closing brackets
            '{"key": "value"',  # Missing closing brace
            '[1, 2, 3',  # Missing closing bracket
            '{"nested": {"inner": "value"}',  # Missing outer brace
        ]
        
        for response in truncated_responses:
            error = ValueError("Some error")
            error.response = Mock(text=response)
            assert is_truncated_json(error) is True
    
    def test_is_truncated_json_by_context(self):
        """Test detection by context."""
        error = ValueError("Some error")
        context = {"json_truncated": True}
        
        assert is_truncated_json(error, context) is True
    
    def test_is_truncated_json_false(self):
        """Test cases where JSON is not truncated."""
        # Non-truncation error
        error = ValueError("Authentication failed")
        assert is_truncated_json(error) is False
        
        # Complete JSON in response
        error = ValueError("Some error")
        error.response = Mock(text='{"complete": "json"}')
        assert is_truncated_json(error) is False
        
        # Context indicates not truncated
        error = ValueError("Some error")
        context = {"json_truncated": False}
        assert is_truncated_json(error, context) is False
    
    def test_is_truncated_json_invalid_json(self):
        """Test with invalid JSON that's not truncated."""
        # Invalid but complete JSON-like strings
        invalid_responses = [
            '{"key": value}',  # Missing quotes around value
            '{key: "value"}',  # Missing quotes around key
            'not json at all',
            '',
            '   ',
        ]
        
        for response in invalid_responses:
            error = ValueError("JSON decode error")
            error.response = Mock(text=response)
            # Should return False for invalid but not truncated JSON
            assert is_truncated_json(error) is False


class TestEnhancedAPIRetryComprehensive:
    """Comprehensive tests for EnhancedAPIRetry."""
    
    def test_successful_call(self):
        """Test successful API call without retries."""
        retry = EnhancedAPIRetry()
        
        mock_func = Mock(return_value="success")
        
        result = retry.execute(mock_func)
        
        assert result == "success"
        mock_func.assert_called_once()
    
    def test_retry_on_json_truncation(self):
        """Test retry on JSON truncation with context."""
        retry = EnhancedAPIRetry(max_json_retries=2)
        
        # Track calls to see if context is passed
        call_args_list = []
        
        def mock_func(**kwargs):
            call_args_list.append(kwargs)
            if len(call_args_list) == 1:
                # First call: simulate JSON truncation
                error = ValueError("truncated JSON")
                error.response = Mock(text='{"data": [1, 2, 3')
                raise error
            return {"data": "complete"}
        
        with patch('time.sleep'):
            result = retry.execute(mock_func)
            
            assert result == {"data": "complete"}
            assert len(call_args_list) == 2
            
            # Second call should have context about JSON truncation
            assert "context" in call_args_list[1]
            assert call_args_list[1]["context"].get("json_truncated") is True
    
    def test_json_truncation_reduce_text_strategy(self):
        """Test JSON truncation with text reduction strategy."""
        retry = EnhancedAPIRetry(max_json_retries=2)
        
        call_args_list = []
        
        def mock_func(text=None, **kwargs):
            call_args_list.append((text, kwargs))
            if len(call_args_list) == 1:
                # First call with full text
                error = ValueError("truncated")
                raise error
            # Second call should have reduced text
            return {"data": "success"}
        
        with patch('time.sleep'):
            # Call with text parameter
            result = retry.execute(mock_func, text="A" * 1000)
            
            assert result == {"data": "success"}
            assert len(call_args_list) == 2
            
            # Second call should have reduced text length
            second_text = call_args_list[1][0]
            assert len(second_text) < 1000
    
    def test_json_truncation_chunk_and_retry(self):
        """Test JSON truncation with chunking strategy."""
        retry = EnhancedAPIRetry(max_json_retries=2)
        
        call_args_list = []
        
        def mock_func(chunks=None, **kwargs):
            call_args_list.append((chunks, kwargs))
            if len(call_args_list) == 1:
                # First call
                error = ValueError("truncated")
                raise error
            # Second call
            return [{"data": "chunk1"}, {"data": "chunk2"}]
        
        with patch('time.sleep'):
            # Call with chunks parameter
            result = retry.execute(mock_func, chunks=["chunk1", "chunk2", "chunk3"])
            
            assert result == [{"data": "chunk1"}, {"data": "chunk2"}]
            assert len(call_args_list) == 2
            
            # Context should indicate chunking strategy
            context = call_args_list[1][1].get("context", {})
            assert context.get("chunking_strategy") == "reduce_size"
    
    def test_exhaust_json_retries(self):
        """Test exhausting JSON-specific retries."""
        retry = EnhancedAPIRetry(max_json_retries=2)
        
        mock_func = Mock(side_effect=ValueError("truncated JSON"))
        
        with patch('time.sleep'):
            with pytest.raises(ValueError, match="truncated JSON"):
                retry.execute(mock_func)
            
            # Should try max_json_retries + 1 times (initial + retries)
            assert mock_func.call_count == 3  # max_json_retries=2 means 3 total attempts
    
    def test_mixed_retry_types(self):
        """Test mixed normal and JSON truncation retries."""
        retry = EnhancedAPIRetry(max_attempts=5, max_json_retries=2)
        
        call_count = 0
        
        def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("normal error")
            elif call_count == 2:
                error = ValueError("truncated JSON")
                error.response = Mock(text='{"incomplete":')
                raise error
            elif call_count == 3:
                error = ValueError("truncated JSON")
                error.response = Mock(text='{"incomplete":')
                raise error
            return "success"
        
        with patch('time.sleep'):
            result = retry.execute(mock_func)
            
            assert result == "success"
            assert call_count == 4  # 1 normal + 2 JSON + 1 success
    
    def test_non_retryable_exception(self):
        """Test non-retryable exception."""
        retry = EnhancedAPIRetry(retry_exceptions=(ValueError,))
        
        mock_func = Mock(side_effect=KeyError("not retryable"))
        
        with pytest.raises(KeyError, match="not retryable"):
            retry.execute(mock_func)
        
        mock_func.assert_called_once()
    
    def test_execute_with_context_parameter(self):
        """Test execute with context parameter."""
        retry = EnhancedAPIRetry()
        
        def mock_func(context=None):
            if context and context.get("test_flag"):
                return "with context"
            return "without context"
        
        # Call without context
        result = retry.execute(mock_func)
        assert result == "without context"
        
        # Call with context
        result = retry.execute(mock_func, context={"test_flag": True})
        assert result == "with context"
    
    def test_should_retry_json_truncation(self):
        """Test should_retry for JSON truncation cases."""
        retry = EnhancedAPIRetry()
        
        # JSON truncation error
        error = ValueError("truncated JSON")
        error.response = Mock(text='{"incomplete":')
        
        assert retry.config.should_retry(error) is True
        
        # JSON truncation with context
        context = {"json_truncated": True}
        assert retry.config.should_retry(error, context) is True
    
    def test_decorator_variants(self):
        """Test decorator variants."""
        # Test retry_with_json_truncation decorator
        @retry_with_json_truncation(max_attempts=2)
        def decorated_func():
            return "success"
        
        result = decorated_func()
        assert result == "success"
        
        # Test with failure
        call_count = 0
        
        @retry_with_json_truncation(max_json_retries=1)
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error = ValueError("truncated")
                error.response = Mock(text='{"incomplete":')
                raise error
            return "success"
        
        with patch('time.sleep'):
            result = failing_func()
            assert result == "success"
            assert call_count == 2
    
    def test_chunk_size_reduction(self):
        """Test chunk size reduction on JSON truncation."""
        retry = EnhancedAPIRetry(chunk_size_reduction_factor=0.5)
        
        original_chunks = ["chunk1", "chunk2", "chunk3", "chunk4"]
        
        # Simulate JSON truncation context
        context = {
            "json_truncated": True,
            "json_retry_count": 1,
            "original_chunks": original_chunks
        }
        
        reduced = retry._reduce_chunk_size_for_retry(context)
        
        # Should reduce number of chunks
        assert len(reduced) < len(original_chunks)
        # Should be approximately half (0.5 factor)
        assert len(reduced) == 2  # 4 * 0.5 = 2
    
    def test_text_reduction(self):
        """Test text size reduction on JSON truncation."""
        retry = EnhancedAPIRetry(chunk_size_reduction_factor=0.5)
        
        original_text = "A" * 1000
        
        # Simulate JSON truncation context
        context = {
            "json_truncated": True,
            "json_retry_count": 1,
            "original_text": original_text
        }
        
        reduced = retry._reduce_text_for_retry(context)
        
        # Should reduce text length
        assert len(reduced) < len(original_text)
        # Should be approximately half (0.5 factor)
        assert len(reduced) == 500  # 1000 * 0.5 = 500
    
    def test_execute_with_text_and_chunks(self):
        """Test execute with both text and chunks parameters."""
        retry = EnhancedAPIRetry()
        
        def mock_func(text=None, chunks=None):
            if text:
                return f"text: {len(text)}"
            if chunks:
                return f"chunks: {len(chunks)}"
            return "none"
        
        # With text
        result = retry.execute(mock_func, text="test")
        assert result == "text: 4"
        
        # With chunks
        result = retry.execute(mock_func, chunks=["a", "b"])
        assert result == "chunks: 2"
        
        # With both (text should take precedence)
        result = retry.execute(mock_func, text="test", chunks=["a", "b"])
        assert result == "text: 4"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])