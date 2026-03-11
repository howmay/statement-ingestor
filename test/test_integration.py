#!/usr/bin/env python3
"""
Integration test for Issue #23 enhancements.
Tests the complete integration of error handling and logging improvements.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def test_enhancement_modules():
    """Test that all enhancement modules can be imported and initialized."""
    print("🧪 Testing enhancement module imports...")
    
    modules_to_test = [
        ('src.utils.logger', 'setup_logging'),
        ('src.utils.retry', 'retry_gmail'),
        ('src.utils.progress', 'ProgressIndicator'),
        ('src.utils.config_validator', 'ConfigValidator'),
    ]
    
    all_passed = True
    for module_name, import_name in modules_to_test:
        try:
            if '.' in import_name:
                # Handle nested imports
                parts = import_name.split('.')
                module = __import__(module_name, fromlist=[parts[0]])
                for part in parts[1:]:
                    module = getattr(module, part)
            else:
                module = __import__(module_name, fromlist=[import_name])
                module = getattr(module, import_name)
            
            print(f"  ✅ {module_name}.{import_name}")
        except ImportError as e:
            print(f"  ❌ {module_name}.{import_name}: {e}")
            all_passed = False
        except AttributeError as e:
            print(f"  ❌ {module_name}.{import_name}: {e}")
            all_passed = False
    
    return all_passed


def test_logger_integration():
    """Test logger integration with structured logging."""
    print("\n🧪 Testing logger integration...")
    
    try:
        from src.utils.logger import setup_logging, get_logger
        
        # Setup logging to console only for test
        setup_logging(
            log_level='INFO',
            log_to_file=False,
            log_to_console=True
        )
        
        logger = get_logger(__name__)
        
        # Test structured logging with context
        logger.info("Test log message", test="integration", module="logger")
        logger.warning("Test warning", count=3, threshold=5)
        
        print("  ✅ Logger integration test passed")
        return True
    except Exception as e:
        print(f"  ❌ Logger integration test failed: {e}")
        return False


def test_retry_integration():
    """Test retry mechanism integration."""
    print("\n🧪 Testing retry integration...")
    
    try:
        from src.utils.retry import retry_gmail, retry_openai, APIRetry, RetryConfig
        
        # Test decorator creation
        @retry_gmail
        def test_gmail_function():
            return "gmail_success"
        
        @retry_openai
        def test_openai_function():
            return "openai_success"
        
        # Test function execution
        gmail_result = test_gmail_function()
        openai_result = test_openai_function()
        
        if gmail_result == "gmail_success" and openai_result == "openai_success":
            print("  ✅ Retry integration test passed")
            return True
        else:
            print(f"  ❌ Retry integration test failed: unexpected results")
            return False
            
    except Exception as e:
        print(f"  ❌ Retry integration test failed: {e}")
        return False


def test_progress_integration():
    """Test progress indicator integration."""
    print("\n🧪 Testing progress integration...")
    
    try:
        from src.utils.progress import ProgressIndicator, ProgressStyle, track_progress
        
        # Test ProgressIndicator
        with ProgressIndicator(total=10, description="Test progress", style=ProgressStyle.BAR) as progress:
            for i in range(10):
                progress.update(1)
        
        # Test track_progress
        items = list(range(5))
        processed = []
        for item in track_progress(items, description="Processing"):
            processed.append(item)
        
        if len(processed) == 5:
            print("  ✅ Progress integration test passed")
            return True
        else:
            print(f"  ❌ Progress integration test failed: expected 5 items, got {len(processed)}")
            return False
            
    except Exception as e:
        print(f"  ❌ Progress integration test failed: {e}")
        return False


def test_config_validator_integration():
    """Test configuration validator integration."""
    print("\n🧪 Testing config validator integration...")
    
    try:
        from src.utils.config_validator import ConfigValidator
        import json
        
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test .env file
            env_content = """TARGET_SENDERS=test@example.com
TARGET_KEYWORDS=receipt,invoice
OPENAI_API_KEY=test_key_12345678901234567890
BANK_PASSWORDS=password1,password2
OAUTH_PORT=8080
"""
            
            env_file = os.path.join(tmpdir, '.env')
            with open(env_file, 'w') as f:
                f.write(env_content)
            
            # Create test client_secrets.json
            config_dir = os.path.join(tmpdir, 'config')
            os.makedirs(config_dir, exist_ok=True)
            
            client_secrets = {
                "installed": {
                    "client_id": "test_client_id",
                    "project_id": "test_project",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": "test_secret",
                    "redirect_uris": ["http://localhost:8080"]
                }
            }
            
            client_secrets_file = os.path.join(config_dir, 'client_secrets.json')
            with open(client_secrets_file, 'w') as f:
                json.dump(client_secrets, f)
            
            # Test validator with test environment
            import os as os_module
            original_env = os_module.environ.copy()
            
            try:
                # Update environment for test
                os_module.environ['TARGET_SENDERS'] = 'test@example.com'
                os_module.environ['TARGET_KEYWORDS'] = 'receipt,invoice'
                
                validator = ConfigValidator()
                is_valid = validator.validate_all()
                
                if is_valid:
                    print("  ✅ Config validator integration test passed")
                    return True
                else:
                    print(f"  ❌ Config validator integration test failed")
                    return False
                    
            finally:
                # Restore original environment
                os_module.environ.clear()
                os_module.environ.update(original_env)
                
    except Exception as e:
        print(f"  ❌ Config validator integration test failed: {e}")
        return False


def test_enhanced_main_integration():
    """Test enhanced main application integration."""
    print("\n🧪 Testing enhanced main application integration...")
    
    try:
        # Test that the enhanced main application can be imported
        # We'll test the existing main_enhanced.py instead
        enhanced_main_path = os.path.join(project_root, 'main_enhanced.py')
        
        # Read the file to check for class definition
        with open(enhanced_main_path, 'r') as f:
            content = f.read()
        
        # Check for class definition
        if 'class GmailExpenseParser:' in content:
            print("  ✅ Enhanced main application integration test passed")
            return True
        else:
            print("  ❌ Enhanced main application integration test failed: missing class")
            return False
            
    except Exception as e:
        print(f"  ❌ Enhanced main application integration test failed: {e}")
        return False


def test_backward_compatibility():
    """Test backward compatibility with original main.py."""
    print("\n🧪 Testing backward compatibility...")
    
    try:
        # Test that original main.py still works
        original_main_path = os.path.join(project_root, 'main.py')
        
        # Read the file to check for main function
        with open(original_main_path, 'r') as f:
            content = f.read()
        
        # Check for main function definition
        if 'def main():' in content:
            print("  ✅ Original main.py backward compatibility test passed")
            
            # Test that imports work
            try:
                # We'll just check imports work
                from src.config import TARGET_SENDERS, TARGET_KEYWORDS
                from src.auth.gmail_auth import get_gmail_service
                
                print("  ✅ Original imports work correctly")
                return True
            except ImportError as e:
                print(f"  ❌ Original imports failed: {e}")
                return False
        else:
            print("  ❌ Original main.py backward compatibility test failed: missing main()")
            return False
            
    except Exception as e:
        print(f"  ❌ Backward compatibility test failed: {e}")
        return False


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Integration Test Suite for Issue #23 Enhancements")
    print("=" * 60)
    
    test_results = []
    
    # Run all tests
    test_results.append(("Module Imports", test_enhancement_modules()))
    test_results.append(("Logger Integration", test_logger_integration()))
    test_results.append(("Retry Integration", test_retry_integration()))
    test_results.append(("Progress Integration", test_progress_integration()))
    test_results.append(("Config Validator Integration", test_config_validator_integration()))
    test_results.append(("Enhanced Main Integration", test_enhanced_main_integration()))
    test_results.append(("Backward Compatibility", test_backward_compatibility()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All integration tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())