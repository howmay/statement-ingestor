"""
Unit tests for config validator utility.
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.support.config_validator import (
    ConfigValidator,
    ConfigValidationError,
    REQUIRED_ENV_VARS,
    RECOMMENDED_ENV_VARS,
    ENV_VALIDATION_RULES,
    REQUIRED_FILES,
    OPTIONAL_FILES
)


class TestConfigValidator:
    """Test suite for ConfigValidator."""
    
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
    
    def test_load_environment_success(self):
        """Test loading environment from .env file."""
        env_content = """
TARGET_SENDERS=bank1@example.com,bank2@example.com
TARGET_KEYWORDS=statement,invoice
OPENAI_API_KEY=sk-test1234567890
BANK_PASSWORDS=password1
"""
        env_file = self.project_root / '.env'
        env_file.write_text(env_content)
        
        env_vars = self.validator.load_environment()
        
        assert 'TARGET_SENDERS' in env_vars
        assert env_vars['TARGET_SENDERS'] == 'bank1@example.com,bank2@example.com'
        assert 'OPENAI_API_KEY' in env_vars
        assert env_vars['OPENAI_API_KEY'] == 'sk-test1234567890'
    
    def test_load_environment_missing_file(self):
        """Test loading environment when .env file doesn't exist."""
        # .env does not exist
        with pytest.raises(ConfigValidationError) as excinfo:
            self.validator.load_environment()
        
        assert "not found" in str(excinfo.value)
    
    def test_validate_environment_all_required_present(self):
        """Test validation when all required variables are present."""
        self.validator.env_values = {
            'TARGET_SENDERS': 'test@example.com',
            'TARGET_KEYWORDS': 'test',
            'OPENAI_API_KEY': 'sk-verylongapikey1234567890',  # 31 chars
        }
        
        results = self.validator.validate_environment()
        
        # Check for no errors
        errors = [r for r in results if r[1] == 'ERROR']
        assert len(errors) == 0
        
        # Check TARGET_SENDERS was validated as OK
        senders_result = next(r for r in results if r[0] == 'TARGET_SENDERS')
        assert senders_result[1] == 'OK'
    
    def test_validate_environment_missing_required(self):
        """Test validation when required variables are missing."""
        self.validator.env_values = {
            'OPENAI_API_KEY': 'sk-test',
        }
        
        results = self.validator.validate_environment()
        
        # Should have errors for missing required vars
        errors = [r for r in results if r[1] == 'ERROR']
        assert len(errors) > 0
        error_vars = [e[0] for e in errors]
        assert 'TARGET_SENDERS' in error_vars or 'TARGET_KEYWORDS' in error_vars
    
    def test_validate_value_comma_separated(self):
        """Test comma-separated validation."""
        # Valid
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            'a@example.com,b@example.com',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'OK'
        
        # Too few items
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            '',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'ERROR'
        assert 'at least 1 items' in msg.lower()
        
        # Too many items without splitting? Actually min_items only, so multiple ok
        status, msg = self.validator._validate_value(
            'TARGET_SENDERS',
            'a@example.com',
            ENV_VALIDATION_RULES['TARGET_SENDERS']
        )
        assert status == 'OK'
    
    def test_validate_value_string(self):
        """Test string validation."""
        status, msg = self.validator._validate_value(
            'OPENAI_API_KEY',
            'sk-123456789012345678901234567890',  # 32 chars
            ENV_VALIDATION_RULES['OPENAI_API_KEY']
        )
        assert status == 'OK'
        
        # Too short
        status, msg = self.validator._validate_value(
            'OPENAI_API_KEY',
            'short',
            ENV_VALIDATION_RULES['OPENAI_API_KEY']
        )
        assert status == 'WARNING'
        assert 'at least 20 characters' in msg.lower()
    
    def test_validate_value_integer(self):
        """Test integer validation."""
        # Valid in range
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            '8080',
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'OK'
        
        # Invalid: not a number
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            'notanumber',
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'ERROR'

    def test_validate_value_statement_search_profiles_json(self):
        value = json.dumps([
            {
                "name": "hsbc-card",
                "senders": ["cards@estatements.hsbc.com.tw"],
                "subject_keywords": ["信用卡帳單", "eStatement"],
                "exclude_keywords": ["OTP"],
                "has_pdf_attachment": True,
            }
        ])

        status, msg = self.validator._validate_value(
            'STATEMENT_SEARCH_PROFILES',
            value,
            ENV_VALIDATION_RULES['STATEMENT_SEARCH_PROFILES']
        )
        assert status == 'OK'

    def test_validate_value_statement_search_profiles_rejects_missing_senders(self):
        value = json.dumps([
            {
                "name": "hsbc-card",
                "subject_keywords": ["信用卡帳單"],
            }
        ])

        status, msg = self.validator._validate_value(
            'STATEMENT_SEARCH_PROFILES',
            value,
            ENV_VALIDATION_RULES['STATEMENT_SEARCH_PROFILES']
        )
        assert status == 'ERROR'
        assert 'senders' in msg.lower()

    def test_validate_value_statement_search_profiles_rejects_bad_json(self):
        status, msg = self.validator._validate_value(
            'STATEMENT_SEARCH_PROFILES',
            '{bad-json',
            ENV_VALIDATION_RULES['STATEMENT_SEARCH_PROFILES']
        )
        assert status == 'ERROR'
        assert 'json' in msg.lower()
        
        # Out of range
        status, msg = self.validator._validate_value(
            'OAUTH_PORT',
            '80',  # too low (< 1024)
            ENV_VALIDATION_RULES['OAUTH_PORT']
        )
        assert status == 'ERROR'
    
    def test_masking_sensitive_values(self):
        """Test that sensitive values are masked in logs."""
        self.validator.env_values = {
            'OPENAI_API_KEY': 'super-secret-key-1234567890',
            'TARGET_SENDERS': 'test@example.com',
        }
        
        results = self.validator.validate_environment()
        api_key_result = next(r for r in results if r[0] == 'OPENAI_API_KEY')
        # The value should be masked (not contain the full secret)
        full_key = 'super-secret-key-1234567890'
        assert full_key not in api_key_result[2]
    
    def test_validate_all_success(self):
        """Test full validation with proper configuration."""
        # Set up a mock .env file
        env_content = """
TARGET_SENDERS=bank1@example.com,bank2@example.com
TARGET_KEYWORDS=invoice,receipt,statement
OPENAI_API_KEY=sk-123456789012345678901234567890
OAUTH_PORT=8080
"""
        (self.project_root / '.env').write_text(env_content)
        
        # Also create client_secrets.json to satisfy file check
        (self.project_root / 'config').mkdir(parents=True, exist_ok=True)
        (self.project_root / 'config' / 'client_secrets.json').write_text(json.dumps({
            "installed": {
                "client_id": "test_id",
                "client_secret": "test_secret",
                "redirect_uris": ["http://localhost"]
            }
        }))
        
        # Load and validate
        self.validator.load_environment()
        is_valid = self.validator.validate_all()
        
        assert is_valid
