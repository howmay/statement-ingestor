"""
Enhanced retry mechanism with specialized handling for JSON truncation errors.
"""
import time
import random
import json
import logging
import inspect
from typing import Callable, Type, Tuple, List, Optional, Any, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class JSONTruncationError(Exception):
    """Exception for truncated JSON responses."""
    pass


class EnhancedRetryConfig:
    """Enhanced configuration for retry behavior with JSON truncation handling."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        retry_on_status_codes: List[int] = None,
        retry_on_conditions: List[Callable[[Any], bool]] = None,
        # JSON-specific settings
        enable_json_truncation_retry: bool = True,
        json_truncation_retry_strategy: str = 'chunk_and_retry',  # 'chunk_and_retry', 'reduce_text', 'fallback'
        max_json_repair_attempts: int = 2,
        max_attempts: Optional[int] = None,
        retry_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
        retry_status_codes: Optional[List[int]] = None,
        backoff_factor: Optional[float] = None,
        json_truncation_delay_multiplier: float = 0.5,
        max_json_retries: Optional[int] = None,
        chunk_size_reduction_factor: float = 0.7,
    ):
        """
        Initialize enhanced retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts (including initial)
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retry_on_exceptions: Tuple of exception types to retry on
            retry_on_status_codes: List of HTTP status codes to retry on
            retry_on_conditions: List of callable conditions for retry
            enable_json_truncation_retry: Whether to enable special handling for JSON truncation
            json_truncation_retry_strategy: Strategy for handling JSON truncation
            max_json_repair_attempts: Maximum attempts to repair JSON before giving up
        """
        if max_attempts is not None:
            max_retries = max_attempts
        if retry_exceptions is not None:
            retry_on_exceptions = retry_exceptions
        if retry_status_codes is not None:
            retry_on_status_codes = retry_status_codes
        if backoff_factor is not None:
            exponential_base = backoff_factor
        if max_json_retries is not None:
            max_json_repair_attempts = max_json_retries

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on_exceptions = retry_on_exceptions
        self.retry_on_status_codes = retry_on_status_codes or []
        self.retry_on_conditions = retry_on_conditions or []
        self.enable_json_truncation_retry = enable_json_truncation_retry
        self.json_truncation_retry_strategy = json_truncation_retry_strategy
        self.max_json_repair_attempts = max_json_repair_attempts
        self.max_attempts = self.max_retries
        self.retry_exceptions = self.retry_on_exceptions
        self.retry_status_codes = set(self.retry_on_status_codes or [429, 500, 502, 503, 504])
        self.backoff_factor = self.exponential_base
        self.json_truncation_delay_multiplier = json_truncation_delay_multiplier
        self.max_json_retries = self.max_json_repair_attempts
        self.chunk_size_reduction_factor = chunk_size_reduction_factor
    
    def should_retry(self, exception: Exception, response: Any = None, context: Dict[str, Any] = None) -> bool:
        """
        Determine if a retry should be attempted.
        
        Args:
            exception: Exception that was raised
            response: Response object (if any)
            context: Additional context for decision making
        
        Returns:
            True if retry should be attempted
        """
        if isinstance(response, dict) and context is None:
            context = response
            response = None

        if not isinstance(exception, Exception):
            response = exception
            exception = Exception(str(exception))

        status_code = getattr(exception, 'status_code', None)
        if isinstance(status_code, int):
            return status_code in self.retry_status_codes

        # Check if exception type should be retried
        if not isinstance(exception, self.retry_on_exceptions):
            return False
        
        # Special handling for JSON truncation
        if self.enable_json_truncation_retry:
            if self._is_json_truncation_error(exception, response, context):
                logger.info("JSON truncation detected, will retry with special handling")
                return True
        
        # Check status codes if response is available
        if response and hasattr(response, 'status_code'):
            if response.status_code in self.retry_status_codes:
                return True
        
        # Check custom conditions
        for condition in self.retry_on_conditions:
            if condition(exception, response):
                return True
        
        return True
    
    def _is_json_truncation_error(self, exception: Exception, response: Any, context: Dict[str, Any] = None) -> bool:
        """
        Detect JSON truncation errors.
        
        Args:
            exception: Exception that was raised
            response: Response object (if any)
            context: Additional context
        
        Returns:
            True if error appears to be JSON truncation
        """
        # Check exception message for JSON decode errors
        error_msg = str(exception).lower()
        json_truncation_indicators = [
            'unexpected end of data',
            'unterminated string',
            'expecting value',
            'json decode error',
            'truncated',
            'incomplete',
            'unexpected eof'
        ]
        
        if any(indicator in error_msg for indicator in json_truncation_indicators):
            return True
        
        # Check if we have response text that might be truncated JSON
        if response and hasattr(response, 'text'):
            response_text = response.text
            if response_text and len(response_text) > 1000:  # Likely a large response
                # Check if it looks like truncated JSON
                if response_text.strip().startswith('{') and not response_text.strip().endswith('}'):
                    return True
                if response_text.strip().startswith('[') and not response_text.strip().endswith(']'):
                    return True
        
        # Check context for text length
        if context and 'text_length' in context:
            if context['text_length'] > 5000:  # Large text more likely to cause truncation
                return True
        
        return False
    
    def calculate_delay(self, attempt: int, is_json_truncation: bool = False) -> float:
        """
        Calculate delay for a retry attempt.
        
        Args:
            attempt: Current attempt number (0-based)
            is_json_truncation: Whether this is a JSON truncation retry
        
        Returns:
            Delay in seconds
        """
        # For JSON truncation, use shorter delays since we're changing strategy
        base_multiplier = self.exponential_base
        
        # Exponential backoff
        delay = self.base_delay * (base_multiplier ** attempt)
        if is_json_truncation:
            delay *= self.json_truncation_delay_multiplier
        
        # Apply maximum delay
        delay = min(delay, self.max_delay)
        
        # Add jitter if enabled
        if isinstance(self.jitter, bool):
            if self.jitter:
                delay = delay * (0.5 + random.random())
        elif self.jitter:
            delay = delay * random.uniform(1.0 - self.jitter, 1.0 + self.jitter)
        
        return delay


class EnhancedAPIRetry:
    """Enhanced API retry handler with JSON truncation support."""
    
    # Default configurations for common APIs
    DEFAULT_CONFIGS = {
        'gmail': EnhancedRetryConfig(
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,),
            retry_on_status_codes=[429, 500, 502, 503, 504]
        ),
        'openai': EnhancedRetryConfig(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,),
            retry_on_status_codes=[429, 500, 502, 503, 504],
            enable_json_truncation_retry=True,
            json_truncation_retry_strategy='chunk_and_retry',
            max_json_repair_attempts=2
        ),
        'generic': EnhancedRetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,)
        )
    }
    
    def __init__(
        self,
        config: Optional[EnhancedRetryConfig] = None,
        api_type: str = 'generic',
        **compat_kwargs,
    ):
        """
        Initialize enhanced API retry handler.
        
        Args:
            config: Custom retry configuration
            api_type: API type for default configuration
        """
        if config is not None:
            self.config = config
        elif compat_kwargs:
            self.config = EnhancedRetryConfig(**compat_kwargs)
        else:
            self.config = self.DEFAULT_CONFIGS.get(api_type, self.DEFAULT_CONFIGS['generic'])
        self.json_repair_attempts = 0
    
    def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with enhanced retry logic.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            Last exception if all retries fail
        """
        local_logger = logging.getLogger(__name__)
        last_exception = None
        response = None
        context = dict(kwargs.get('context', {}) or {})

        # Reset per-execution counter
        self.json_repair_attempts = 0

        try:
            signature = inspect.signature(func)
            accepts_context = ('context' in signature.parameters) or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
            )
        except Exception:
            accepts_context = True

        base_kwargs = dict(kwargs)

        for attempt in range(self.config.max_retries):
            call_kwargs = dict(base_kwargs)
            if accepts_context:
                call_kwargs['context'] = context

            try:
                # Execute the function
                result = func(*args, **call_kwargs)
                response = result

                # Check if result indicates failure
                if hasattr(result, 'status_code') and result.status_code >= 400:
                    error_msg = f"HTTP {result.status_code}: {result.reason if hasattr(result, 'reason') else 'Unknown error'}"
                    http_exception = Exception(error_msg)

                    if self.config.should_retry(http_exception, result, context):
                        local_logger.warning(
                            f"HTTP error {result.status_code} on attempt {attempt + 1}/{self.config.max_retries}. "
                            f"Will retry."
                        )
                        last_exception = http_exception
                        continue
                    return result

                # Check for JSON truncation in successful responses
                if (
                    self.config.enable_json_truncation_retry
                    and hasattr(result, 'text')
                    and self._is_truncated_json(result.text)
                ):
                    local_logger.warning("Response appears to contain truncated JSON")
                    raise JSONTruncationError("JSON response appears truncated")

                if attempt > 0:
                    local_logger.info(f"Operation succeeded on attempt {attempt + 1}")
                return result

            except JSONTruncationError as e:
                last_exception = e
                self._handle_json_retry(e, response, context, base_kwargs, attempt, local_logger)
                continue

            except Exception as e:
                last_exception = e

                if self.config.enable_json_truncation_retry and is_truncated_json(e, context):
                    self._handle_json_retry(e, response, context, base_kwargs, attempt, local_logger)
                    continue

                if not self.config.should_retry(e, response, context):
                    local_logger.error(f"Non-retryable exception: {e}")
                    raise

                local_logger.warning(
                    f"Attempt {attempt + 1}/{self.config.max_retries} failed: {e}. "
                    f"Will retry."
                )

                if attempt < self.config.max_retries - 1:
                    delay = self.config.calculate_delay(attempt)
                    local_logger.info(f"Waiting {delay:.2f} seconds before retry...")
                    time.sleep(delay)

        local_logger.error(f"All {self.config.max_retries} attempts failed. Last error: {last_exception}")
        raise last_exception

    def _handle_json_retry(
        self,
        error: Exception,
        response: Any,
        context: Dict[str, Any],
        base_kwargs: Dict[str, Any],
        attempt: int,
        local_logger: logging.Logger,
    ) -> None:
        self.json_repair_attempts += 1
        context['json_truncated'] = True
        context['json_retry_count'] = self.json_repair_attempts

        if self.json_repair_attempts <= self.config.max_json_repair_attempts:
            strategy = self.config.json_truncation_retry_strategy
            if 'chunks' in base_kwargs:
                strategy = 'chunk_and_retry'
            elif 'text' in base_kwargs:
                strategy = 'reduce_text'

            local_logger.info(f"JSON truncation detected, applying strategy: {strategy}")

            if strategy == 'reduce_text' and 'text' in base_kwargs:
                context['original_text'] = base_kwargs['text']
                base_kwargs['text'] = self._reduce_text_for_retry(context)
                local_logger.info(
                    f"Reduced text from {len(context['original_text'])} to {len(base_kwargs['text'])} characters"
                )

            elif strategy == 'chunk_and_retry':
                context['force_chunking'] = True
                context['chunking_strategy'] = 'reduce_size'
                if 'chunks' in base_kwargs:
                    context['original_chunks'] = base_kwargs['chunks']
                    base_kwargs['chunks'] = self._reduce_chunk_size_for_retry(context)
                local_logger.info("Signaled function to force chunking on next attempt")

        if not self.config.should_retry(error, response, context):
            local_logger.error(f"Non-retryable JSON truncation: {error}")
            raise error

        local_logger.warning(
            f"JSON truncation on attempt {attempt + 1}/{self.config.max_retries}. "
            f"Will retry (repair attempt {self.json_repair_attempts}/{self.config.max_json_repair_attempts})."
        )

        if attempt < self.config.max_retries - 1:
            delay = self.config.calculate_delay(attempt, is_json_truncation=True)
            local_logger.info(f"Waiting {delay:.2f} seconds before JSON truncation retry...")
            time.sleep(delay)

    def _reduce_chunk_size_for_retry(self, context: Dict[str, Any]) -> List[Any]:
        original_chunks = list(context.get("original_chunks") or [])
        if not original_chunks:
            return []
        target_size = max(1, int(len(original_chunks) * self.config.chunk_size_reduction_factor))
        return original_chunks[:target_size]

    def _reduce_text_for_retry(self, context: Dict[str, Any]) -> str:
        original_text = str(context.get("original_text") or "")
        if not original_text:
            return ""
        target_size = max(1, int(len(original_text) * self.config.chunk_size_reduction_factor))
        return original_text[:target_size]
    
    def _is_truncated_json(self, text: str) -> bool:
        """
        Check if text appears to be truncated JSON.
        
        Args:
            text: Text to check
        
        Returns:
            True if text appears to be truncated JSON
        """
        if not text:
            return False
        
        text = text.strip()
        
        # Check for obvious truncation
        if text.startswith('{') and not text.endswith('}'):
            return True
        if text.startswith('[') and not text.endswith(']'):
            return True
        
        # Try to parse as JSON
        try:
            json.loads(text)
            return False  # Valid JSON, not truncated
        except json.JSONDecodeError as e:
            # Check error message for truncation indicators
            error_msg = str(e).lower()
            truncation_indicators = [
                'unexpected end of data',
                'unterminated string',
                'expecting value',
                'unexpected eof'
            ]
            
            if any(indicator in error_msg for indicator in truncation_indicators):
                return True
            
            # Check if error is near the end of a long string
            if len(text) > 1000 and 'line 1 column' in error_msg:
                # Parse the column number from error message
                import re
                match = re.search(r'column (\d+)', error_msg)
                if match:
                    error_column = int(match.group(1))
                    if error_column > len(text) * 0.9:  # Error near the end
                        return True
        
        return False


def enhanced_retry_decorator(config: Optional[EnhancedRetryConfig] = None, api_type: str = 'generic'):
    """
    Decorator for adding enhanced retry logic to functions.
    
    Args:
        config: Retry configuration
        api_type: API type for default configuration
    
    Returns:
        Decorated function
    """
    retry_handler = EnhancedAPIRetry(config, api_type)
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_handler.execute(func, *args, **kwargs)
        return wrapper
    
    return decorator


# Convenience decorators for common APIs
def enhanced_retry_gmail(func: Callable):
    """Decorator for Gmail API calls with enhanced retry."""
    return enhanced_retry_decorator(api_type='gmail')(func)


def enhanced_retry_openai(func: Callable):
    """Decorator for OpenAI API calls with enhanced retry."""
    return enhanced_retry_decorator(api_type='openai')(func)


def enhanced_retry_generic(func: Callable):
    """Decorator for generic API calls with enhanced retry."""
    return enhanced_retry_decorator(api_type='generic')(func)


def is_truncated_json(error: Exception, context: Optional[Dict[str, Any]] = None) -> bool:
    """Backward-compatible helper used by comprehensive tests."""
    response = getattr(error, 'response', None)
    if context and context.get("json_truncated") is True:
        return True

    if any(marker in str(error).lower() for marker in [
        'unexpected end of data',
        'truncated',
        'incomplete',
        'unexpected eof',
        'premature end',
        'json parsing error',
    ]):
        return True

    text = getattr(response, 'text', None)
    if not text:
        return False

    text = str(text).strip()
    if not text:
        return False
    if text.startswith('{') and not text.endswith('}'):
        return True
    if text.startswith('[') and not text.endswith(']'):
        return True
    if text.count('{') > text.count('}') or text.count('[') > text.count(']'):
        return True
    return False


def retry_with_json_truncation(config: Optional[EnhancedRetryConfig] = None, **compat_kwargs):
    """Backward-compatible decorator factory for JSON truncation aware retries."""
    return enhanced_retry_decorator(config=config or EnhancedRetryConfig(**compat_kwargs))


# Example usage
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Test with JSON truncation
    @enhanced_retry_openai
    def test_api_with_truncated_json():
        """Simulate API returning truncated JSON."""
        class MockResponse:
            text = '{"transactions": [{"date": "2024-01-01", "amount": 100.0, "description": "Unfinished'
            status_code = 200
        
        return MockResponse()
    
    try:
        result = test_api_with_truncated_json()
        print(f"Result: {result.text}")
    except Exception as e:
        print(f"Failed after retries: {e}")
