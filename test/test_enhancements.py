#!/usr/bin/env python3
"""
Test script for Issue #23 enhancements.
Tests the comprehensive error handling and logging improvements.
"""
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logging, get_logger, StructuredLogger
from src.utils.config_validator import ConfigValidator, validate_configuration
from src.utils.retry import APIRetry, RetryConfig, retry_gmail, retry_openai
from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress, MultiProgress


def test_logger():
    """Test structured logging."""
    print("🧪 Testing structured logger...")
    
    # Setup logging for test
    setup_logging(
        log_level='DEBUG',
        log_to_file=False,
        log_to_console=True
    )
    
    logger = get_logger(__name__)
    
    # Test different log levels with context
    logger.info("Starting logger test")
    logger.debug("Debug message", user="test_user", action="login")
    logger.warning("Warning message", count=5, threshold=10)
    logger.error("Error message", exc_info=False, error_code=404)
    
    # Test exception logging
    try:
        raise ValueError("Test exception for logging")
    except ValueError:
        logger.exception("Exception occurred", context="test")
    
    print("✅ Logger test completed\n")
    return True


def test_config_validator():
    """Test configuration validator."""
    print("🧪 Testing configuration validator...")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test .env file
        env_content = """TARGET_SENDERS=test1@example.com,test2@example.com
TARGET_KEYWORDS=receipt,invoice
OPENAI_API_KEY=sk-test1234567890abcdef
BANK_PASSWORDS=pass1,pass2
OAUTH_PORT=8081
"""
        env_file = tmpdir / '.env'
        env_file.write_text(env_content)
        
        # Create test client_secrets.json
        client_secrets = {
            "installed": {
                "client_id": "test-client-id.apps.googleusercontent.com",
                "client_secret": "test-client-secret",
                "redirect_uris": ["http://localhost:8081"]
            }
        }
        config_dir = tmpdir / 'config'
        config_dir.mkdir()
        (config_dir / 'client_secrets.json').write_text(json.dumps(client_secrets))
        
        # Test validator
        validator = ConfigValidator(str(tmpdir))
        
        try:
            # Load environment
            env_values = validator.load_environment()
            print(f"  Loaded {len(env_values)} environment variables")
            
            # Validate environment
            env_results = validator.validate_environment()
            print(f"  Environment validation: {len(env_results)} checks")
            for var, status, msg in env_results:
                print(f"    {status}: {var} - {msg}")
            
            # Validate files
            file_results = validator.validate_files()
            print(f"  File validation: {len(file_results)} checks")
            for file_path, status, msg in file_results:
                print(f"    {status}: {file_path} - {msg}")
            
            # Generate report
            report = validator.generate_config_report()
            print(f"  Report generated ({len(report.splitlines())} lines)")
            
        except Exception as e:
            print(f"❌ Config validator test failed: {e}")
            return False
    
    print("✅ Config validator test completed\n")
    return True


def test_retry_mechanism():
    """Test retry mechanism."""
    print("🧪 Testing retry mechanism...")
    
    # Test configuration
    config = RetryConfig(
        max_retries=3,
        base_delay=0.1,  # Short delay for testing
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False  # Disable jitter for predictable testing
    )
    
    retry_handler = APIRetry(config)
    
    # Test with a failing function
    call_count = 0
    
    def failing_function(success_on_attempt=3):
        nonlocal call_count
        call_count += 1
        if call_count < success_on_attempt:
            raise Exception(f"Simulated failure {call_count}")
        return f"Success on attempt {call_count}"
    
    try:
        print(f"  Testing retry with success on 3rd attempt...")
        result = retry_handler.execute(failing_function, success_on_attempt=3)
        print(f"  Result: {result}")
        print(f"  Total calls: {call_count}")
        
        if call_count != 3:
            print(f"❌ Expected 3 calls, got {call_count}")
            return False
        
    except Exception as e:
        print(f"❌ Retry test failed: {e}")
        return False
    
    # Test decorator
    call_count = 0
    
    @retry_gmail
    def decorated_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise Exception("Simulated failure")
        return "Success"
    
    try:
        print(f"  Testing decorator...")
        result = decorated_function()
        print(f"  Result: {result}")
        print(f"  Total calls: {call_count}")
        
    except Exception as e:
        print(f"❌ Decorator test failed: {e}")
        return False
    
    print("✅ Retry mechanism test completed\n")
    return True


def test_progress_indicator():
    """Test progress indicator."""
    print("🧪 Testing progress indicator...")
    
    import time
    
    # Test different styles
    styles = [
        (ProgressStyle.BAR, "Progress bar"),
        (ProgressStyle.PERCENTAGE, "Percentage"),
        (ProgressStyle.SPINNER, "Spinner"),
        (ProgressStyle.COUNTER, "Counter"),
    ]
    
    for style, description in styles:
        print(f"  Testing {description}...")
        with ProgressIndicator(
            total=10,
            description=description,
            style=style,
            update_interval=0.05
        ) as progress:
            for i in range(10):
                time.sleep(0.05)
                progress.update(1)
    
    # Test track_progress
    print(f"  Testing track_progress...")
    items = list(range(5))
    for item in track_progress(items, description="Processing items"):
        time.sleep(0.05)
    
    # Test MultiProgress
    print(f"  Testing MultiProgress...")
    multi = MultiProgress()
    
    def simulate_work(name, steps):
        progress = multi.add(name, steps, f"Task {name}", ProgressStyle.SPINNER)
        progress.start()
        for i in range(steps):
            time.sleep(0.02)
            progress.update(1)
        progress.finish()
    
    # Simulate multiple tasks
    simulate_work("A", 5)
    simulate_work("B", 3)
    
    print("✅ Progress indicator test completed\n")
    return True


def test_integration():
    """Test integration of all enhancements."""
    print("🧪 Testing integration...")
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Setup logging
        setup_logging(
            log_level='INFO',
            log_dir=str(tmpdir / 'logs'),
            log_to_file=True,
            log_to_console=False
        )
        
        logger = get_logger(__name__)
        
        # Log test messages
        logger.info("Integration test started", test="enhancements")
        logger.debug("Debug message", component="logger")
        logger.warning("Warning message", issue="test")
        
        # Check log file was created
        log_files = list((tmpdir / 'logs').glob('*.log'))
        if log_files:
            print(f"  Log file created: {log_files[0].name}")
            # Read first few lines
            with open(log_files[0], 'r') as f:
                lines = f.readlines()[:5]
                print(f"  Sample log entries: {len(lines)} lines")
        else:
            print("❌ No log file created")
            return False
    
    print("✅ Integration test completed\n")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Issue #23 Enhancements")
    print("=" * 60)
    
    tests = [
        ("Structured Logger", test_logger),
        ("Config Validator", test_config_validator),
        ("Retry Mechanism", test_retry_mechanism),
        ("Progress Indicator", test_progress_indicator),
        ("Integration", test_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())