"""
Progress indicator for long-running operations.
Provides visual feedback and estimated completion time.
"""
import time
import sys
import threading
from typing import Optional, Callable, Any, List, Dict
from datetime import datetime, timedelta
from enum import Enum


class ProgressStyle(Enum):
    """Progress display styles."""
    BAR = "bar"
    PERCENTAGE = "percentage"
    SPINNER = "spinner"
    COUNTER = "counter"
    SILENT = "silent"


class ProgressIndicator:
    """
    Progress indicator for tracking operation progress.
    
    Features:
    - Multiple display styles
    - Estimated time remaining
    - Thread-safe updates
    - Custom formatting
    """
    
    def __init__(
        self,
        total: int = 100,
        description: str = "Processing",
        style: ProgressStyle = ProgressStyle.BAR,
        update_interval: float = 0.1,
        show_eta: bool = True,
        show_percentage: bool = True,
        bar_width: int = 40
    ):
        """
        Initialize progress indicator.
        
        Args:
            total: Total number of steps
            description: Description of the operation
            style: Display style
            update_interval: Minimum time between updates (seconds)
            show_eta: Whether to show estimated time remaining
            show_percentage: Whether to show percentage
            bar_width: Width of progress bar in characters
        """
        self.total = total
        self.description = description
        self.style = style
        self.update_interval = update_interval
        self.show_eta = show_eta
        self.show_percentage = show_percentage
        self.bar_width = bar_width
        
        self.current = 0
        self.start_time = None
        self.last_update_time = 0
        self.completed = False
        self._lock = threading.Lock()
        
        # For spinner
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_index = 0
    
    def start(self):
        """Start the progress indicator."""
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.current = 0
        self.completed = False
        
        if self.style != ProgressStyle.SILENT:
            self._print_progress()
    
    def update(self, increment: int = 1, description: Optional[str] = None):
        """
        Update progress.
        
        Args:
            increment: Number of steps to increment
            description: Optional new description
        """
        with self._lock:
            if description:
                self.description = description
            
            self.current += increment
            
            # Ensure we don't exceed total
            if self.current > self.total:
                self.current = self.total
            
            # Check if we should update display
            current_time = time.time()
            if (current_time - self.last_update_time >= self.update_interval or 
                self.current >= self.total):
                self.last_update_time = current_time
                self._print_progress()
    
    def finish(self, message: Optional[str] = None):
        """
        Mark progress as complete.
        
        Args:
            message: Optional completion message
        """
        with self._lock:
            self.current = self.total
            self.completed = True
            
            if self.style != ProgressStyle.SILENT:
                self._print_progress()
                
                if message:
                    print(f"\n{message}")
                else:
                    elapsed = time.time() - self.start_time
                    print(f"\n✓ {self.description} completed in {elapsed:.1f}s")
    
    def _print_progress(self):
        """Print progress based on selected style."""
        if self.style == ProgressStyle.SILENT:
            return
        
        # Calculate progress metrics
        progress = min(self.current / self.total, 1.0) if self.total > 0 else 0
        percentage = progress * 100
        
        # Calculate ETA
        eta_str = ""
        if self.show_eta and self.start_time and progress > 0:
            elapsed = time.time() - self.start_time
            if progress > 0:
                total_time = elapsed / progress
                remaining = total_time - elapsed
                eta_str = f" ETA: {self._format_time(remaining)}"
        
        # Build progress string based on style
        if self.style == ProgressStyle.BAR:
            self._print_bar(progress, percentage, eta_str)
        elif self.style == ProgressStyle.PERCENTAGE:
            self._print_percentage(progress, percentage, eta_str)
        elif self.style == ProgressStyle.SPINNER:
            self._print_spinner(progress, percentage, eta_str)
        elif self.style == ProgressStyle.COUNTER:
            self._print_counter(progress, percentage, eta_str)
    
    def _print_bar(self, progress: float, percentage: float, eta_str: str):
        """Print progress bar."""
        filled_width = int(self.bar_width * progress)
        bar = '█' * filled_width + '░' * (self.bar_width - filled_width)
        
        percentage_str = f"{percentage:.1f}%" if self.show_percentage else ""
        
        # Clear line and print
        sys.stdout.write('\r')
        sys.stdout.write(f"{self.description}: [{bar}] {percentage_str}{eta_str}")
        sys.stdout.flush()
    
    def _print_percentage(self, progress: float, percentage: float, eta_str: str):
        """Print percentage only."""
        percentage_str = f"{percentage:.1f}%" if self.show_percentage else f"{self.current}/{self.total}"
        
        sys.stdout.write('\r')
        sys.stdout.write(f"{self.description}: {percentage_str}{eta_str}")
        sys.stdout.flush()
    
    def _print_spinner(self, progress: float, percentage: float, eta_str: str):
        """Print spinner animation."""
        spinner = self.spinner_chars[self.spinner_index % len(self.spinner_chars)]
        self.spinner_index += 1
        
        percentage_str = f" {percentage:.1f}%" if self.show_percentage else ""
        
        sys.stdout.write('\r')
        sys.stdout.write(f"{spinner} {self.description}:{percentage_str}{eta_str}")
        sys.stdout.flush()
    
    def _print_counter(self, progress: float, percentage: float, eta_str: str):
        """Print counter."""
        counter_str = f"{self.current}/{self.total}"
        percentage_str = f" ({percentage:.1f}%)" if self.show_percentage else ""
        
        sys.stdout.write('\r')
        sys.stdout.write(f"{self.description}: {counter_str}{percentage_str}{eta_str}")
        sys.stdout.flush()
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format time in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            self.finish()
        else:
            # Error occurred, clear progress line
            if self.style != ProgressStyle.SILENT:
                sys.stdout.write('\r' + ' ' * 80 + '\r')
                sys.stdout.flush()


class MultiProgress:
    """
    Manager for multiple progress indicators.
    Useful for tracking multiple concurrent operations.
    """
    
    def __init__(self):
        self.indicators: Dict[str, ProgressIndicator] = {}
        self._lock = threading.Lock()
    
    def add(
        self,
        name: str,
        total: int = 100,
        description: str = "Processing",
        style: ProgressStyle = ProgressStyle.BAR
    ) -> ProgressIndicator:
        """
        Add a new progress indicator.
        
        Args:
            name: Unique identifier for the indicator
            total: Total number of steps
            description: Description of the operation
            style: Display style
        
        Returns:
            ProgressIndicator instance
        """
        with self._lock:
            if name in self.indicators:
                raise ValueError(f"Progress indicator '{name}' already exists")
            
            indicator = ProgressIndicator(total, description, style)
            self.indicators[name] = indicator
            return indicator
    
    def get(self, name: str) -> Optional[ProgressIndicator]:
        """Get progress indicator by name."""
        with self._lock:
            return self.indicators.get(name)
    
    def remove(self, name: str):
        """Remove progress indicator."""
        with self._lock:
            if name in self.indicators:
                del self.indicators[name]
    
    def clear(self):
        """Clear all progress indicators."""
        with self._lock:
            self.indicators.clear()


# Convenience functions
def track_progress(
    iterable,
    total: Optional[int] = None,
    description: str = "Processing",
    style: ProgressStyle = ProgressStyle.BAR,
    update_interval: float = 0.1
):
    """
    Track progress while iterating.
    
    Args:
        iterable: Iterable to process
        total: Total number of items (if not len(iterable))
        description: Progress description
        style: Display style
        update_interval: Update interval in seconds
    
    Yields:
        Items from iterable
    """
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            total = 100  # Default if length unknown
    
    with ProgressIndicator(total, description, style, update_interval) as progress:
        for item in iterable:
            yield item
            progress.update(1)


def run_with_progress(
    func: Callable,
    total: int = 100,
    description: str = "Processing",
    style: ProgressStyle = ProgressStyle.BAR,
    update_interval: float = 0.1
) -> Callable:
    """
    Decorator to run function with progress tracking.
    
    Args:
        func: Function to decorate
        total: Total number of steps
        description: Progress description
        style: Display style
        update_interval: Update interval in seconds
    
    Returns:
        Decorated function
    """
    def wrapper(*args, **kwargs):
        progress = ProgressIndicator(total, description, style, update_interval)
        progress.start()
        
        # Pass progress object to function if it accepts it
        import inspect
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        if 'progress' in params:
            kwargs['progress'] = progress
        
        try:
            result = func(*args, **kwargs)
            progress.finish()
            return result
        except Exception as e:
            progress.finish(f"✗ {description} failed: {e}")
            raise
    
    return wrapper


# Example usage
if __name__ == '__main__':
    import time
    
    # Example 1: Simple progress bar
    print("Example 1: Simple progress bar")
    with ProgressIndicator(total=50, description="Downloading", style=ProgressStyle.BAR) as progress:
        for i in range(50):
            time.sleep(0.05)
            progress.update(1)
    
    print("\n" + "="*50)
    
    # Example 2: Using track_progress
    print("Example 2: Using track_progress")
    items = list(range(20))
    for item in track_progress(items, description="Processing items"):
        time.sleep(0.1)
    
    print("\n" + "="*50)
    
    # Example 3: MultiProgress
    print("Example 3: MultiProgress")
    multi = MultiProgress()
    
    # Simulate multiple operations
    import threading
    
    def worker(name, count):
        progress = multi.add(name, count, f"Worker {name}", ProgressStyle.SPINNER)
        progress.start()
        for i in range(count):
            time.sleep(0.2)
            progress.update(1)
        progress.finish()
    
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(f"Task{i}", 10))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    print("\nAll tasks completed!")