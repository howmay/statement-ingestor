"""
Retry mechanism for API calls with exponential backoff.
Supports Gmail API, OpenAI API, and other external services.
"""
import time
import random
import logging
from typing import Callable, Type, Tuple, List, Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        retry_on_status_codes: List[int] = None,
        retry_on_conditions: List[Callable[[Any], bool]] = None
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts (including initial)
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retry_on_exceptions: Tuple of exception types to retry on
            retry_on_status_codes: List of HTTP status codes to retry on
            retry_on_conditions: List of callable conditions for retry
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on_exceptions = retry_on_exceptions
        self.retry_on_status_codes = retry_on_status_codes or []
        self.retry_on_conditions = retry_on_conditions or []
    
    def should_retry(self, exception: Exception, response: Any = None) -> bool:
        """
        Determine if a retry should be attempted.
        
        Args:
            exception: Exception that was raised
            response: Response object (if any)
        
        Returns:
            True if retry should be attempted
        """
        # Check if exception type should be retried
        if not isinstance(exception, self.retry_on_exceptions):
            return False
        
        # Check status codes if response is available
        status_code = getattr(response, 'status_code', None)
        if isinstance(status_code, int) and status_code >= 400:
            if self.retry_on_status_codes and status_code not in self.retry_on_status_codes:
                return False
        
        # Check custom conditions
        for condition in self.retry_on_conditions:
            try:
                if condition(exception, response):
                    return True
            except Exception:
                pass
        
        return True
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a retry attempt.
        
        Args:
            attempt: Current attempt number (0-based)
        
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = self.base_delay * (self.exponential_base ** attempt)
        
        # Apply maximum delay
        delay = min(delay, self.max_delay)
        
        # Add jitter if enabled
        if self.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay


class APIRetry:
    """API retry handler with configurable strategies."""
    
    # Default configurations for common APIs
    DEFAULT_CONFIGS = {
        'gmail': RetryConfig(
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,),
            retry_on_status_codes=[429, 500, 502, 503, 504]
        ),
        'openai': RetryConfig(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,),
            retry_on_status_codes=[429, 500, 502, 503, 504]
        ),
        'generic': RetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True,
            retry_on_exceptions=(Exception,)
        )
    }
    
    def __init__(self, config: Optional[RetryConfig] = None, api_type: str = 'generic'):
        """
        Initialize API retry handler.
        
        Args:
            config: Custom retry configuration
            api_type: API type for default configuration
        """
        self.config = config or self.DEFAULT_CONFIGS.get(api_type, self.DEFAULT_CONFIGS['generic'])
    
    def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        response = None
        
        for attempt in range(self.config.max_retries):
            try:
                # Execute the function
                result = func(*args, **kwargs)
                response = result
                
                # Check if result indicates failure
                status_code = getattr(result, 'status_code', None)
                if isinstance(status_code, int) and status_code >= 400:
                    # Create a pseudo-exception for HTTP errors
                    error_msg = f"HTTP {result.status_code}: {result.reason if hasattr(result, 'reason') else 'Unknown error'}"
                    http_exception = Exception(error_msg)
                    
                    if self.config.should_retry(http_exception, result):
                        logger.warning(
                            f"HTTP error {result.status_code} on attempt {attempt + 1}/{self.config.max_retries}. "
                            f"Will retry."
                        )
                        last_exception = http_exception
                        if attempt < self.config.max_retries - 1:
                            delay = self.config.calculate_delay(attempt)
                            logger.info(f"Waiting {delay:.2f} seconds before retry...")
                            time.sleep(delay)
                        continue
                    else:
                        # Not a retryable error
                        return result
                
                # Success
                if attempt > 0:
                    logger.info(f"Operation succeeded on attempt {attempt + 1}")
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if not self.config.should_retry(e, response):
                    logger.error(f"Non-retryable exception: {e}")
                    raise
                
                # Log retry attempt
                logger.warning(
                    f"Attempt {attempt + 1}/{self.config.max_retries} failed: {e}. "
                    f"Will retry."
                )
                
                # Calculate and wait for delay (except on last attempt)
                if attempt < self.config.max_retries - 1:
                    delay = self.config.calculate_delay(attempt)
                    logger.info(f"Waiting {delay:.2f} seconds before retry...")
                    time.sleep(delay)
        
        # All retries failed
        logger.error(f"All {self.config.max_retries} attempts failed. Last error: {last_exception}")
        raise last_exception


def retry_decorator(config: Optional[RetryConfig] = None, api_type: str = 'generic'):
    """
    Decorator for adding retry logic to functions.
    
    Args:
        config: Retry configuration
        api_type: API type for default configuration
    
    Returns:
        Decorated function
    """
    retry_handler = APIRetry(config, api_type)
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_handler.execute(func, *args, **kwargs)
        return wrapper
    
    return decorator


# Convenience decorators for common APIs
def retry_gmail(func: Callable):
    """Decorator for Gmail API calls with retry."""
    return retry_decorator(api_type='gmail')(func)


def retry_openai(func: Callable):
    """Decorator for OpenAI API calls with retry."""
    return retry_decorator(api_type='openai')(func)


def retry_generic(func: Callable):
    """Decorator for generic API calls with retry."""
    return retry_decorator(api_type='generic')(func)


# Example usage
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Test with a failing function
    call_count = 0
    
    @retry_gmail
    def test_gmail_api():
        global call_count
        call_count += 1
        if call_count < 3:
            raise Exception(f"Simulated API failure {call_count}")
        return "Success"
    
    try:
        result = test_gmail_api()
        print(f"Result: {result}")
        print(f"Total calls: {call_count}")
    except Exception as e:
        print(f"Failed after all retries: {e}")
