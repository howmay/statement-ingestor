"""
Configuration validator for gmail-expense-parser.
Validates .env file and configuration at startup.
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv, dotenv_values

# Required environment variables
REQUIRED_ENV_VARS = [
    'TARGET_SENDERS',
    'TARGET_KEYWORDS'
]

# Optional but recommended environment variables
RECOMMENDED_ENV_VARS = [
    'OPENAI_API_KEY',
    'BANK_PASSWORDS'
]

# Environment variable validation rules
ENV_VALIDATION_RULES = {
    'TARGET_SENDERS': {
        'type': 'comma_separated',
        'min_items': 1,
        'description': 'Comma-separated list of sender email addresses'
    },
    'TARGET_KEYWORDS': {
        'type': 'comma_separated',
        'min_items': 1,
        'description': 'Comma-separated list of keywords to search for'
    },
    'OPENAI_API_KEY': {
        'type': 'string',
        'min_length': 20,
        'description': 'OpenAI API key for LLM parsing'
    },
    'BANK_PASSWORDS': {
        'type': 'comma_separated',
        'description': 'Comma-separated list of passwords for encrypted PDFs'
    },
    'OAUTH_PORT': {
        'type': 'integer',
        'min_value': 1024,
        'max_value': 65535,
        'default': '8080',
        'description': 'Port for OAuth2 local server'
    }
}

# Required files
REQUIRED_FILES = [
    'config/client_secrets.json'
]

# Optional files
OPTIONAL_FILES = [
    'config/token.json'
]


class ConfigValidationError(Exception):
    """Exception raised for configuration validation errors."""
    pass


class ConfigValidator:
    """Configuration validator for the application."""
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize config validator.
        
        Args:
            project_root: Path to project root directory
        """
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.project_root = Path(project_root)
        
        # Load environment variables
        self.env_file = self.project_root / '.env'
        self.env_values = {}
        
    def load_environment(self) -> Dict[str, str]:
        """
        Load environment variables from .env file.
        
        Returns:
            Dictionary of environment variables
        
        Raises:
            ConfigValidationError: If .env file is missing or invalid
        """
        if not self.env_file.exists():
            # Try .env.example
            env_example = self.project_root / '.env.example'
            if env_example.exists():
                raise ConfigValidationError(
                    f".env file not found. Please copy .env.example to .env and configure it.\n"
                    f"  cp {env_example} {self.env_file}"
                )
            else:
                raise ConfigValidationError(
                    f".env file not found at {self.env_file}. "
                    f"Please create it with required configuration."
                )
        
        # Load .env file
        load_dotenv(self.env_file)
        self.env_values = dotenv_values(self.env_file)
        
        # Also load from actual environment (overrides .env)
        for key in os.environ:
            self.env_values[key] = os.environ[key]
        
        return self.env_values.copy()
    
    def validate_environment(self) -> List[Tuple[str, str, str]]:
        """
        Validate environment variables.
        
        Returns:
            List of validation results as (variable, status, message) tuples
        
        Raises:
            ConfigValidationError: If required variables are missing
        """
        results = []
        
        # Check required variables
        for var in REQUIRED_ENV_VARS:
            value = self.env_values.get(var)
            
            if not value:
                results.append((var, 'ERROR', f'Required variable is missing'))
                continue
            
            # Apply validation rules if defined
            if var in ENV_VALIDATION_RULES:
                rule = ENV_VALIDATION_RULES[var]
                validation_result = self._validate_value(var, value, rule)
                results.append((var, validation_result[0], validation_result[1]))
            else:
                results.append((var, 'OK', f'Present: {self._mask_sensitive(var, value)}'))
        
        # Check recommended variables
        for var in RECOMMENDED_ENV_VARS:
            value = self.env_values.get(var)
            
            if not value:
                results.append((var, 'WARNING', 'Recommended variable is missing'))
                continue
            
            # Apply validation rules if defined
            if var in ENV_VALIDATION_RULES:
                rule = ENV_VALIDATION_RULES[var]
                validation_result = self._validate_value(var, value, rule)
                results.append((var, validation_result[0], validation_result[1]))
            else:
                results.append((var, 'OK', f'Present: {self._mask_sensitive(var, value)}'))
        
        # Note: We don't raise exceptions here; we return results with ERROR status
        # The caller (validate_all) will decide if overall validation fails.
        return results
    
    def validate_files(self) -> List[Tuple[str, str, str]]:
        """
        Validate required and optional files.
        
        Returns:
            List of validation results as (file, status, message) tuples
        """
        results = []
        
        # Check required files
        for file_path in REQUIRED_FILES:
            full_path = self.project_root / file_path
            
            if not full_path.exists():
                results.append((file_path, 'ERROR', f'Required file not found'))
            elif not os.access(full_path, os.R_OK):
                results.append((file_path, 'ERROR', f'File exists but is not readable'))
            else:
                # Additional validation for specific files
                if file_path == 'config/client_secrets.json':
                    file_status, file_message = self._validate_client_secrets(full_path)
                    results.append((file_path, file_status, file_message))
                else:
                    results.append((file_path, 'OK', 'File exists and is readable'))
        
        # Check optional files
        for file_path in OPTIONAL_FILES:
            full_path = self.project_root / file_path
            
            if not full_path.exists():
                results.append((file_path, 'INFO', 'Optional file not found (will be created)'))
            elif not os.access(full_path, os.R_OK):
                results.append((file_path, 'WARNING', 'File exists but is not readable'))
            else:
                results.append((file_path, 'OK', 'File exists and is readable'))
        
        return results
    
    def _validate_value(self, var: str, value: str, rule: Dict[str, Any]) -> Tuple[str, str]:
        """
        Validate a single value against rules.
        
        Args:
            var: Variable name
            value: Variable value
            rule: Validation rule dictionary
        
        Returns:
            Tuple of (status, message)
        """
        value_type = rule.get('type', 'string')
        
        if value_type == 'comma_separated':
            items = [item.strip() for item in value.split(',') if item.strip()]
            
            # Check minimum items
            min_items = rule.get('min_items')
            if min_items and len(items) < min_items:
                return ('ERROR', f'Should have at least {min_items} items, found {len(items)}')
            
            return ('OK', f'Contains {len(items)} item(s): {", ".join(items[:3])}' + 
                   ('...' if len(items) > 3 else ''))
        
        elif value_type == 'integer':
            try:
                int_value = int(value)
                
                # Check min/max
                min_val = rule.get('min_value')
                max_val = rule.get('max_value')
                
                if min_val is not None and int_value < min_val:
                    return ('ERROR', f'Should be >= {min_val}, got {int_value}')
                if max_val is not None and int_value > max_val:
                    return ('ERROR', f'Should be <= {max_val}, got {int_value}')
                
                return ('OK', f'Valid integer: {int_value}')
            except ValueError:
                return ('ERROR', f'Should be an integer, got "{value}"')
        
        elif value_type == 'string':
            min_length = rule.get('min_length')
            
            if min_length and len(value) < min_length:
                return ('WARNING' if var in RECOMMENDED_ENV_VARS else 'ERROR',
                       f'Should be at least {min_length} characters, got {len(value)}')
            
            return ('OK', f'Present: {self._mask_sensitive(var, value)}')
        
        return ('OK', f'Present: {self._mask_sensitive(var, value)}')
    
    def _validate_client_secrets(self, file_path: Path) -> Tuple[str, str]:
        """
        Validate client_secrets.json file.
        
        Args:
            file_path: Path to client_secrets.json
        
        Returns:
            Tuple of (status, message)
        """
        try:
            with open(file_path, 'r') as f:
                content = json.load(f)
            
            # Check structure
            if 'installed' not in content and 'web' not in content:
                return ('ERROR', 'Invalid format: missing "installed" or "web" section')
            
            # Check for required fields
            client_info = content.get('installed') or content.get('web')
            required_fields = ['client_id', 'client_secret', 'redirect_uris']
            
            for field in required_fields:
                if field not in client_info:
                    return ('ERROR', f'Missing required field: {field}')
            
            return ('OK', 'Valid Google OAuth2 client configuration')
            
        except json.JSONDecodeError:
            return ('ERROR', 'Invalid JSON format')
        except Exception as e:
            return ('ERROR', f'Validation error: {str(e)}')
    
    def _mask_sensitive(self, var: str, value: str) -> str:
        """
        Mask sensitive values in output.
        
        Args:
            var: Variable name
            value: Variable value
        
        Returns:
            Masked value string
        """
        sensitive_vars = ['OPENAI_API_KEY', 'BANK_PASSWORDS', 'client_secret']
        
        if any(sensitive in var for sensitive in sensitive_vars):
            if len(value) > 8:
                return value[:4] + '...' + value[-4:]
            else:
                return '***'
        
        # For comma-separated sensitive values
        if var == 'BANK_PASSWORDS':
            items = [item.strip() for item in value.split(',') if item.strip()]
            masked_items = []
            for item in items:
                if len(item) > 4:
                    masked_items.append(item[:2] + '...' + item[-2:])
                else:
                    masked_items.append('***')
            return ', '.join(masked_items)
        
        # Truncate long values
        if len(value) > 50:
            return value[:47] + '...'
        
        return value
    
    def generate_config_report(self) -> str:
        """
        Generate a comprehensive configuration report.
        
        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 60)
        report.append("Configuration Validation Report")
        report.append("=" * 60)
        
        # Environment variables
        report.append("\n📋 Environment Variables:")
        report.append("-" * 40)
        
        env_results = self.validate_environment()
        for var, status, msg in env_results:
            status_icon = {
                'OK': '✅',
                'WARNING': '⚠️',
                'ERROR': '❌',
                'INFO': 'ℹ️'
            }.get(status, '❓')
            report.append(f"{status_icon} {var}: {msg}")
        
        # Files
        report.append("\n📁 Files:")
        report.append("-" * 40)
        
        file_results = self.validate_files()
        for file_path, status, msg in file_results:
            status_icon = {
                'OK': '✅',
                'WARNING': '⚠️',
                'ERROR': '❌',
                'INFO': 'ℹ️'
            }.get(status, '❓')
            report.append(f"{status_icon} {file_path}: {msg}")
        
        # Summary
        report.append("\n📊 Summary:")
        report.append("-" * 40)
        
        env_ok = sum(1 for r in env_results if r[1] == 'OK')
        env_warn = sum(1 for r in env_results if r[1] == 'WARNING')
        env_error = sum(1 for r in env_results if r[1] == 'ERROR')
        
        file_ok = sum(1 for r in file_results if r[1] == 'OK')
        file_warn = sum(1 for r in file_results if r[1] == 'WARNING')
        file_error = sum(1 for r in file_results if r[1] == 'ERROR')
        
        report.append(f"Environment: {env_ok} OK, {env_warn} Warnings, {env_error} Errors")
        report.append(f"Files: {file_ok} OK, {file_warn} Warnings, {file_error} Errors")
        
        if env_error == 0 and file_error == 0:
            report.append("\n🎉 All checks passed! Configuration is valid.")
        else:
            report.append(f"\n⚠️  Found {env_error + file_error} error(s). Please fix before proceeding.")
        
        report.append("=" * 60)
        
        return '\n'.join(report)
    
    def validate_all(self) -> bool:
        """
        Validate all configuration and print report.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            # Load environment
            self.load_environment()
            
            # Generate and print report
            report = self.generate_config_report()
            print(report)
            
            # Check for errors
            env_results = self.validate_environment()
            file_results = self.validate_files()
            
            env_errors = sum(1 for r in env_results if r[1] == 'ERROR')
            file_errors = sum(1 for r in file_results if r[1] == 'ERROR')
            
            return env_errors == 0 and file_errors == 0
            
        except ConfigValidationError as e:
            print(f"\n❌ Configuration validation failed:\n{e}")
            return False
        except Exception as e:
            print(f"\n❌ Unexpected error during validation: {e}")
            return False


# Convenience function
def validate_configuration(project_root: Optional[str] = None) -> bool:
    """
    Validate configuration and return status.
    
    Args:
        project_root: Path to project root directory
    
    Returns:
        True if configuration is valid, False otherwise
    """
    validator = ConfigValidator(project_root)
    return validator.validate_all()


if __name__ == '__main__':
    # Test the validator
    print("Testing configuration validator...\n")
    
    # Use current directory as project root
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    is_valid = validate_configuration(current_dir)
    
    sys.exit(0 if is_valid else 1)