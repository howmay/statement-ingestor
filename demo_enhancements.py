#!/usr/bin/env python3
"""
Demo script showing the enhancements from Issue #23.
"""
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logging, get_logger
from src.utils.config_validator import ConfigValidator
from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
from src.utils.retry import APIRetry, RetryConfig


def demo_logging():
    """Demonstrate structured logging."""
    print("\n" + "="*60)
    print("DEMO 1: Structured Logging")
    print("="*60)
    
    # Setup logging
    setup_logging(
        log_level='DEBUG',
        log_to_file=False,
        log_to_console=True
    )
    
    logger = get_logger(__name__)
    
    # Show different log levels with context
    logger.info("Application started", version="1.0.0", user="demo_user")
    logger.debug("Debug information", component="parser", state="initializing")
    logger.warning("Low disk space", available_gb=2, required_gb=5)
    
    # Simulate an error with context
    try:
        result = 10 / 0
    except ZeroDivisionError:
        logger.error("Division by zero", exc_info=True, operation="calculate_total")
    
    print("\n✅ Structured logging demo complete")


def demo_config_validation():
    """Demonstrate configuration validation."""
    print("\n" + "="*60)
    print("DEMO 2: Configuration Validation")
    print("="*60)
    
    validator = ConfigValidator()
    
    # Generate a configuration report
    report = validator.generate_config_report()
    print(report)
    
    print("\n✅ Configuration validation demo complete")


def demo_progress_indicators():
    """Demonstrate progress indicators."""
    print("\n" + "="*60)
    print("DEMO 3: Progress Indicators")
    print("="*60)
    
    print("\n1. Simple progress bar:")
    with ProgressIndicator(
        total=20,
        description="Processing files",
        style=ProgressStyle.BAR,
        show_eta=True
    ) as progress:
        for i in range(20):
            time.sleep(0.05)
            progress.update(1)
    
    print("\n2. Spinner for indeterminate operations:")
    with ProgressIndicator(
        total=100,
        description="Downloading",
        style=ProgressStyle.SPINNER,
        show_eta=False
    ) as progress:
        for i in range(100):
            time.sleep(0.01)
            progress.update(1)
    
    print("\n3. Using track_progress helper:")
    items = ["file1.pdf", "file2.pdf", "file3.pdf", "file4.pdf", "file5.pdf"]
    for item in track_progress(items, description="Extracting text"):
        time.sleep(0.1)
    
    print("\n✅ Progress indicators demo complete")


def demo_retry_mechanism():
    """Demonstrate retry mechanism."""
    print("\n" + "="*60)
    print("DEMO 4: Retry Mechanism")
    print("="*60)
    
    # Create a retry configuration
    config = RetryConfig(
        max_retries=3,
        base_delay=0.5,
        max_delay=2.0,
        exponential_base=2.0,
        jitter=True
    )
    
    retry_handler = APIRetry(config)
    
    # Simulate an API call that fails twice then succeeds
    call_count = 0
    
    def simulate_api_call():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError(f"API connection failed (attempt {call_count})")
        return f"API call successful on attempt {call_count}"
    
    print("\nSimulating API call with retry...")
    try:
        result = retry_handler.execute(simulate_api_call)
        print(f"Result: {result}")
        print(f"Total attempts: {call_count}")
    except Exception as e:
        print(f"Failed after all retries: {e}")
    
    print("\n✅ Retry mechanism demo complete")


def demo_integration():
    """Demonstrate integrated enhancements."""
    print("\n" + "="*60)
    print("DEMO 5: Integrated Enhancements")
    print("="*60)
    
    # Setup logging
    setup_logging(
        log_level='INFO',
        log_to_file=False,
        log_to_console=True
    )
    
    logger = get_logger(__name__)
    
    # Simulate a complete workflow
    logger.info("Starting enhanced workflow demo")
    
    # Step 1: Validate configuration
    logger.info("Step 1: Validating configuration")
    validator = ConfigValidator()
    try:
        validator.load_environment()
        logger.info("Configuration validation passed")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        return
    
    # Step 2: Process items with progress
    logger.info("Step 2: Processing items")
    items = list(range(10))
    
    with ProgressIndicator(
        total=len(items),
        description="Processing workflow",
        style=ProgressStyle.BAR,
        show_eta=True
    ) as progress:
        
        for i, item in enumerate(items):
            # Simulate work with occasional errors
            if i == 3:
                logger.warning(f"Minor issue with item {i}", item_id=i)
            
            # Simulate processing time
            time.sleep(0.1)
            
            # Update progress
            progress.update(1, description=f"Processing item {i+1}/{len(items)}")
    
    # Step 3: Summary
    logger.info("Workflow completed successfully", 
                items_processed=len(items),
                errors=0,
                warnings=1)
    
    print("\n✅ Integrated enhancements demo complete")


def main():
    """Run all demos."""
    print("="*60)
    print("Issue #23 Enhancements Demo")
    print("="*60)
    print("\nThis demo showcases the comprehensive error handling")
    print("and logging improvements implemented for Issue #23.")
    
    demos = [
        ("Structured Logging", demo_logging),
        ("Configuration Validation", demo_config_validation),
        ("Progress Indicators", demo_progress_indicators),
        ("Retry Mechanism", demo_retry_mechanism),
        ("Integrated Enhancements", demo_integration),
    ]
    
    for demo_name, demo_func in demos:
        input(f"\nPress Enter to run: {demo_name}...")
        try:
            demo_func()
        except KeyboardInterrupt:
            print("\n⚠️  Demo interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Demo failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("All demos completed!")
    print("="*60)
    print("\nSummary of enhancements implemented:")
    print("1. ✅ Structured logging with context")
    print("2. ✅ Configuration validation at startup")
    print("3. ✅ Progress indicators for long operations")
    print("4. ✅ Retry mechanism for API calls")
    print("5. ✅ Integrated error handling and reporting")
    print("\nThese improvements provide:")
    print("• Better reliability with automatic retries")
    print("• Improved debugging with structured logs")
    print("• Enhanced user experience with progress feedback")
    print("• Operational safety with configuration validation")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user")