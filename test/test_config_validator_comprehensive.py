"""
Comprehensive tests for config_validator.py to improve coverage to 85%.
Focuses on edge cases and uncovered lines.
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.utils.config_validator import (
    ConfigValidator,
    ConfigValidationError,
    REQUIRED_ENV_VARS,
    RECOMMENDED_ENV_VARS,
    ENV_VALIDATION_RULES,
    REQUIRED_FILES,
    OPTIONAL_FILES
)


class TestConfigValidatorComprehensive:
    """Comprehensive tests for ConfigValidator covering all edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock os.environ to avoid interference from real environment
        self.patcher = patch.dict('os.environ', {}, clear=True)
        self.patcher.start()
        
        self.temp_dir = TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        
        # Create minimal project structure
        (self.project_root / 'config').mkdir(parents=True, exist_ok=True)
        
        self.validator = ConfigValidator(project_root=str(self.project_root))
    
    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
        self.patcher.stop()
    
    def test_init_with_custom_project_root(self):
        """Test initialization with custom project root."""
        validator = ConfigValidator(project_root="/custom/path")
        assert validator.project_root == Path("/custom/path")
    
    def test_init_without_project_root(self):
        """Test initialization without project root (uses current directory)."""
        with patch('pathlib.Path.cwd', return_value=Path("/current/dir")):
            validator = ConfigValidator()
            assert validator.project_root == Path("/current/dir")
    
    def test_load_environment_with_os_environ(self):
        """Test loading environment from os.environ when .env file doesn't exist."""
        # Set environment variables
        os.environ['TARGET_SENDERS'] = 'test@example.com'
        os.environ['TARGET_KEYWORDS'] = 'statement'
        
        # .env file doesn't exist
        env_file = self.project_root / '.env'
        if env_file.exists():
            env_file.unlink()
        
        env_vars = self.validator.load_environment()
        
        # Should load from os.environ
        assert 'TARGET_SENDERS' in env_vars
        assert env_vars['TARGET_SENDERS'] == 'test@example.com'
        assert 'TARGET_KEYWORDS' in env_vars
        assert env_vars['TARGET_KEYWORDS'] == 'statement'
    
    def test_load_environment_empty_file(self):
        """Test loading environment from empty .env file."""
        env_file = self.project_root / '.env'
        env_file.write_text("")  # Empty file
        
        env_vars = self.validator.load_environment()
        
        # Should return empty dict
        assert env_vars == {}
    
    def test_load_environment_with_comments_and_whitespace(self):
        """Test loading environment from .env file with comments and whitespace."""
        env_content = """
# This is a comment
TARGET_SENDERS = bank1@example.com, bank2@example.com

TARGET_KEYWORDS=statement,invoice  # inline comment

# Empty line above
OPENAI_API_KEY=sk-test1234567890
"""
        env_file = self.project_root / '.env'
        env_file.write_text(env_content)
        
        env_vars = self.validator.load_environment()
        
        # Should parse correctly
        assert 'TARGET_SENDERS' in env_vars
        assert env_vars['TARGET_SENDERS'] == 'bank1@example.com, bank2@example.com'
        assert 'TARGET_KEYWORDS' in env_vars
        assert env_vars['TARGET_KEYWORDS'] == 'statement,invoice'
        assert 'OPENAI_API_KEY' in env_vars
        assert env_vars['OPENAI_API_KEY'] == 'sk-test1234567890'
    
    def test_load_environment_with_invalid_lines(self):
        """Test loading environment with invalid lines in .env file."""
        env_content = """
VALID_LINE=value1
INVALID LINE WITHOUT EQUALS
ANOTHER_VALID=value2
=EMPTY_KEY
KEY_WITHOUT_VALUE=
"""
        env_file = self.project_root / '.env'
        env_file.write_text(env_content)
        
        env_vars = self.validator.load_environment()
        
        # Should only parse valid lines
        assert 'VALID_LINE' in env_vars
        assert env_vars['VALID_LINE'] == 'value1'
        assert 'ANOTHER_VALID' in env_vars
        assert env_vars['ANOTHER_VALID'] == 'value2'
        # Invalid lines should be skipped
    
    def test_validate_value_boolean(self):
        """Test boolean validation."""
        # Create a boolean validation rule
        boolean_rule = {
            'type': 'boolean',
            'description': 'Test boolean rule'
        }
        
        # Valid boolean values
        status, msg = self.validator._validate_value(
            'TEST_BOOLEAN',
            'true',
            boolean_rule
        )
        assert status == 'OK'
        
        status, msg = self.validator._validate_value(
            'TEST_BOOLEAN',
            'false',
            boolean_rule
        )
        assert status == 'OK'
        
        status, msg = self.validator._validate_value(
            'TEST_BOOLEAN',
            'TRUE',
            boolean_rule
        )
        assert status == 'OK'
        
        status, msg = self.validator._validate_value(
            'TEST_BOOLEAN',
            'FALSE',
            boolean_rule
        )
        assert status == 'OK'
        
        # Invalid boolean
        status, msg = self.validator._validate_value(
            'TEST_BOOLEAN',
            'notaboolean',
            boolean_rule
        )
        assert status == 'ERROR'
    
    def test_validate_value_email_list(self):
        """Test email list validation."""
        # Valid email list
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            'user@example.com,another@test.com',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'OK'
        
        # Invalid email in list
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            'valid@example.com,invalid-email',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'WARNING'  # Should be warning, not error
    
    def test_validate_value_with_custom_regex(self):
        """Test validation with custom regex pattern."""
        # Test BANK_PASSWORDS with simple list format
        status, msg = self.validator._validate_value(
            'BANK_PASSWORDS',
            'password1,password2,password3',
            ENV_VALIDATION_RULES['BANK_PASSWORDS']
        )
        assert status == 'OK'
        
        # Test with JSON format
        status, msg = self.validator._validate_value(
            'BANK_PASSWORDS',
            '{"bank1": "pass1", "bank2": "pass2"}',
            ENV_VALIDATION_RULES['BANK_PASSWORDS']
        )
        assert status == 'OK'
        
        # Invalid JSON
        status, msg = self.validator._validate_value(
            'BANK_PASSWORDS',
            '{invalid json',
            ENV_VALIDATION_RULES['BANK_PASSWORDS']
        )
        assert status == 'ERROR'
    
    def test_validate_value_with_min_max(self):
        """Test validation with min/max constraints."""
        # Test OAUTH_PORT within range
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            '8080',
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'OK'
        
        # Test below min
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            '80',
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'ERROR'
        
        # Test above max
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            '65536',
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'ERROR'
    
    def test_validate_value_with_allowed_values(self):
        """Test validation with allowed values list."""
        # Test LOG_LEVEL with allowed values
        status, msg = self.validator._validate_value(
            'LOG_LEVEL',
            'INFO',
            ENV_VALIDATION_RULES['LOG_LEVEL']
        )
        assert status == 'OK'
        
        status, msg = self.validator._validate_value(
            'LOG_LEVEL',
            'DEBUG',
            ENV_VALIDATION_RULES['LOG_LEVEL']
        )
        assert status == 'OK'
        
        status, msg = self.validator._validate_value(
            'LOG_LEVEL',
            'INVALID',
            ENV_VALIDATION_RULES['LOG_LEVEL']
        )
        assert status == 'ERROR'
    
    def test_validate_value_with_no_validation_rule(self):
        """Test validation of variable with no validation rule."""
        # Variable not in ENV_VALIDATION_RULES
        status, msg = self.validator._validate_value(
            'UNKNOWN_VAR',
            'some value',
            None
        )
        assert status == 'OK'  # Should pass without validation
    
    def test_validate_value_empty_string(self):
        """Test validation of empty string values."""
        # Empty string for required field
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            '',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'ERROR'
        
        # Empty string for optional field
        status, msg = self.validator._validate_value(
            'LOG_LEVEL',
            '',
            ENV_VALIDATION_RULES['LOG_LEVEL']
        )
        assert status == 'OK'  # Empty is allowed for optional fields
    
    def test_masking_sensitive_values_comprehensive(self):
        """Test comprehensive masking of sensitive values."""
        test_cases = [
            ('OPENAI_API_KEY', 'sk-1234567890abcdef1234567890abcdef', 'sk-1234...cdef'),
            ('OPENAI_API_KEY', 'sk-test', 'sk-****'),  # Too short to mask properly
            ('BANK_PASSWORDS', 'secretpassword', '********'),
            ('BANK_PASSWORDS', 'pass123', '****'),
            ('CLIENT_SECRET', 'very-secret-key', '********'),
            ('NON_SENSITIVE', 'public_value', 'public_value'),  # Should not be masked
        ]
        
        for var_name, value, expected_masked in test_cases:
            masked = self.validator._mask_sensitive_value(var_name, value)
            assert masked == expected_masked, f"Failed for {var_name}: {value}"
    
    def test_validate_files_required_missing(self):
        """Test file validation when required files are missing."""
        # Don't create any files
        results = self.validator.validate_files()
        
        # Should have errors for missing required files
        errors = [r for r in results if r[1] == 'ERROR']
        assert len(errors) > 0
        
        # Check for specific required files
        error_files = [e[0] for e in errors]
        assert 'config/client_secrets.json' in error_files
    
    def test_validate_files_required_exists(self):
        """Test file validation when required files exist."""
        # Create required files
        (self.project_root / 'config' / 'client_secrets.json').write_text(json.dumps({
            "installed": {
                "client_id": "test",
                "client_secret": "test",
                "redirect_uris": ["http://localhost"]
            }
        }))
        
        # Create token file
        (self.project_root / 'config' / 'token.json').write_text(json.dumps({
            "access_token": "test",
            "refresh_token": "test"
        }))
        
        results = self.validator.validate_files()
        
        # Should have no errors
        errors = [r for r in results if r[1] == 'ERROR']
        assert len(errors) == 0
        
        # Required files should be OK
        ok_files = [r[0] for r in results if r[1] == 'OK']
        assert 'config/client_secrets.json' in ok_files
        assert 'config/token.json' in ok_files
    
    def test_validate_files_optional_missing(self):
        """Test file validation when optional files are missing."""
        # Create only required files
        (self.project_root / 'config' / 'client_secrets.json').write_text(json.dumps({
            "installed": {"client_id": "test", "client_secret": "test"}
        }))
        
        results = self.validator.validate_files()
        
        # Optional missing files should be WARNING, not ERROR
        warnings = [r for r in results if r[1] == 'WARNING']
        warning_files = [w[0] for w in warnings]
        
        # config/token.json is optional (WARNING if missing)
        assert 'config/token.json' in warning_files
    
    def test_validate_files_invalid_json(self):
        """Test file validation with invalid JSON files."""
        # Create file with invalid JSON
        (self.project_root / 'config' / 'client_secrets.json').write_text("{invalid json")
        
        results = self.validator.validate_files()
        
        # Should have error for invalid JSON
        errors = [r for r in results if r[1] == 'ERROR']
        error_files = [e[0] for e in errors]
        assert 'config/client_secrets.json' in error_files
    
    def test_validate_all_with_missing_required_env(self):
        """Test validate_all when required environment variables are missing."""
        # Create .env file without required vars
        env_content = """
# Missing TARGET_SENDERS and TARGET_KEYWORDS
OPENAI_API_KEY=sk-test1234567890
"""
        (self.project_root / '.env').write_text(env_content)
        
        # Create required files
        (self.project_root / 'config' / 'client_secrets.json').write_text(json.dumps({
            "installed": {"client_id": "test", "client_secret": "test"}
        }))
        
        self.validator.load_environment()
        is_valid = self.validator.validate_all()
        
        # Should be False due to missing required env vars
        assert not is_valid
    
    def test_validate_all_with_file_errors(self):
        """Test validate_all when files have errors."""
        # Create .env file with all required vars
        env_content = """
TARGET_SENDERS=test@example.com
TARGET_KEYWORDS=statement
OPENAI_API_KEY=sk-test1234567890
"""
        (self.project_root / '.env').write_text(env_content)
        
        # Don't create required files
        
        self.validator.load_environment()
        is_valid = self.validator.validate_all()
        
        # Should be False due to missing files
        assert not is_valid
    
    def test_validate_all_success(self):
        """Test successful validate_all with complete configuration."""
        # Create complete .env file
        env_content = """
TARGET_SENDERS=bank@example.com
TARGET_KEYWORDS=statement,invoice
OPENAI_API_KEY=sk-123456789012345678901234567890
OAUTH_PORT=8080
LOG_LEVEL=INFO
ENABLE_LLM_CHUNKING=true
BANK_PASSWORDS=password1,password2
"""
        (self.project_root / '.env').write_text(env_content)
        
        # Create all required files
        (self.project_root / 'config' / 'client_secrets.json').write_text(json.dumps({
            "installed": {
                "client_id": "test_id",
                "client_secret": "test_secret",
                "redirect_uris": ["http://localhost:8080"]
            }
        }))
        
        (self.project_root / 'config' / 'token.json').write_text(json.dumps({
            "access_token": "test_token",
            "refresh_token": "test_refresh"
        }))
        
        self.validator.load_environment()
        is_valid = self.validator.validate_all()
        
        # Should be True
        assert is_valid
    
    def test_get_validation_summary(self):
        """Test getting validation summary."""
        # Set up some validation results
        self.validator.env_values = {
            'TARGET_SENDERS': 'test@example.com',
            'TARGET_KEYWORDS': 'statement',
            'OPENAI_API_KEY': 'sk-test'
        }
        
        # Mock validate_environment to return specific results
        with patch.object(self.validator, 'validate_environment') as mock_validate:
            mock_validate.return_value = [
                ('TARGET_SENDERS', 'OK', 'test@example.com'),
                ('TARGET_KEYWORDS', 'OK', 'statement'),
                ('OPENAI_API_KEY', 'WARNING', 'sk-**** (masked)'),
                ('MISSING_VAR', 'ERROR', 'Required variable is missing')
            ]
            
            with patch.object(self.validator, 'validate_files') as mock_files:
                mock_files.return_value = [
                    ('config/client_secrets.json', 'OK', 'File exists'),
                    ('config/token.json', 'WARNING', 'Optional file missing')
                ]
                
                summary = self.validator.get_validation_summary()
                
                # Should contain both environment