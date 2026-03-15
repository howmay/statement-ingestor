"""
Performance monitoring utilities for profiling and optimization.
"""
import time
import logging
import functools
from typing import Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def profile(func: Callable) -> Callable:
    """
    Decorator to measure and log function execution time.
    
    Args:
        func: Function to profile.
    
    Returns:
        Wrapped function with profiling.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            logger.debug(f"Function {func.__name__} took {elapsed:.6f} seconds")
            
            # Log warning for slow functions (> 1 second)
            if elapsed > 1.0:
                logger.warning(f"Slow function detected: {func.__name__} took {elapsed:.2f} seconds")
    
    return wrapper


class PerformanceMonitor:
    """
    Context manager for monitoring performance of code blocks.
    """
    
    def __init__(self, name: str, threshold: float = 1.0):
        """
        Initialize performance monitor.
        
        Args:
            name: Name of the monitored block.
            threshold: Time threshold in seconds for warning.
        """
        self.name = name
        self.threshold = threshold
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        elapsed = self.end_time - self.start_time
        
        logger.debug(f"Block '{self.name}' took {elapsed:.6f} seconds")
        
        if elapsed > self.threshold:
            logger.warning(f"Slow block detected: '{self.name}' took {elapsed:.2f} seconds")
        
        return False  # Don't suppress exceptions


def measure_time(func: Callable) -> Callable:
    """
    Decorator that returns both result and execution time.
    
    Args:
        func: Function to measure.
    
    Returns:
        Wrapped function returning (result, elapsed_time).
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> tuple[Any, float]:
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        return result, elapsed
    
    return wrapper


class PerformanceStats:
    """
    Collect and analyze performance statistics.
    """
    
    def __init__(self):
        self.measurements: dict[str, list[float]] = {}
        self.call_counts: dict[str, int] = {}
    
    def record(self, name: str, elapsed: float):
        """
        Record a measurement.
        
        Args:
            name: Measurement name.
            elapsed: Elapsed time in seconds.
        """
        if name not in self.measurements:
            self.measurements[name] = []
            self.call_counts[name] = 0
        
        self.measurements[name].append(elapsed)
        self.call_counts[name] += 1
    
    def get_stats(self, name: str) -> dict[str, float]:
        """
        Get statistics for a measurement.
        
        Args:
            name: Measurement name.
        
        Returns:
            Dictionary with min, max, avg, median, total, count.
        """
        if name not in self.measurements:
            return {}
        
        values = self.measurements[name]
        if not values:
            return {}
        
        sorted_values = sorted(values)
        n = len(values)
        
        return {
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / n,
            'median': sorted_values[n // 2] if n % 2 == 1 else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2,
            'total': sum(values),
            'count': n,
            'std': (sum((x - (sum(values) / n)) ** 2 for x in values) / n) ** 0.5 if n > 1 else 0
        }
    
    def print_summary(self):
        """
        Print summary of all measurements.
        """
        logger.info("=== Performance Summary ===")
        for name in sorted(self.measurements.keys()):
            stats = self.get_stats(name)
            if stats:
                logger.info(
                    f"{name}: "
                    f"count={stats['count']}, "
                    f"avg={stats['avg']:.6f}s, "
                    f"min={stats['min']:.6f}s, "
                    f"max={stats['max']:.6f}s, "
                    f"total={stats['total']:.3f}s"
                )
        logger.info("==========================")


# Global performance stats instance
global_stats = PerformanceStats()


def record_performance(name: str):
    """
    Decorator to record performance in global stats.
    
    Args:
        name: Name for the measurement.
    
    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                elapsed = end_time - start_time
                global_stats.record(name, elapsed)
        
        return wrapper
    return decorator