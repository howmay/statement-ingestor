"""
Comprehensive tests for the current config_validator.py API.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from src.support import config_validator as cv
from src.support.config_validator import ConfigValidationError, ConfigValidator


class TestConfigValidatorComprehensive:
    def setup_method(self):
        self.environ_patcher = patch.dict("os.environ", {}, clear=True)
        self.environ_patcher.start()

        self.temp_dir = TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        (self.project_root / "config").mkdir(parents=True, exist_ok=True)
        self.validator = ConfigValidator(project_root=str(self.project_root))

    def teardown_method(self):
        self.temp_dir.cleanup()
        self.environ_patcher.stop()

    def test_init_without_project_root_uses_module_root(self):
        validator = ConfigValidator()
        expected = Path(cv.__file__).resolve().parents[2]
        assert validator.project_root == expected

    def test_load_environment_raises_with_env_example_hint(self):
        (self.project_root / ".env.example").write_text("TARGET_SENDERS=a@example.com\n")

        with pytest.raises(ConfigValidationError) as excinfo:
            self.validator.load_environment()

        assert "copy .env.example to .env" in str(excinfo.value)

    def test_load_environment_merges_file_and_environment(self):
        (self.project_root / ".env").write_text(
            "TARGET_SENDERS=file@example.com\nTARGET_KEYWORDS=statement\nOPENAI_API_KEY=file-key-123456789012345\n"
        )
        os.environ["TARGET_SENDERS"] = "env@example.com"
        os.environ["EXTRA_FLAG"] = "1"

        env_vars = self.validator.load_environment()

        assert env_vars["TARGET_SENDERS"] == "env@example.com"
        assert env_vars["TARGET_KEYWORDS"] == "statement"
        assert env_vars["EXTRA_FLAG"] == "1"

    def test_validate_value_comma_separated_and_integer_rules(self):
        status, _ = self.validator._validate_value(
            "TARGET_SENDERS",
            "a@example.com,b@example.com",
            cv.ENV_VALIDATION_RULES["TARGET_SENDERS"],
        )
        assert status == "OK"

        status, _ = self.validator._validate_value(
            "TARGET_SENDERS",
            "",
            cv.ENV_VALIDATION_RULES["TARGET_SENDERS"],
        )
        assert status == "ERROR"

        status, _ = self.validator._validate_value(
            "OAUTH_PORT",
            "8080",
            cv.ENV_VALIDATION_RULES["OAUTH_PORT"],
        )
        assert status == "OK"

        status, msg = self.validator._validate_value(
            "OAUTH_PORT",
            "80",
            cv.ENV_VALIDATION_RULES["OAUTH_PORT"],
        )
        assert status == "ERROR"
        assert ">=" in msg

    def test_validate_value_string_rule_uses_warning_for_recommended_var(self):
        status, msg = self.validator._validate_value(
            "OPENAI_API_KEY",
            "short",
            cv.ENV_VALIDATION_RULES["OPENAI_API_KEY"],
        )

        assert status == "WARNING"
        assert "at least 20 characters" in msg

    def test_mask_sensitive_masks_known_secret_fields(self):
        assert self.validator._mask_sensitive("OPENAI_API_KEY", "sk-1234567890abcdef") == "sk-1...cdef"
        assert self.validator._mask_sensitive("BANK_PASSWORDS", "abcd1234") == "***"
        assert self.validator._mask_sensitive("TARGET_SENDERS", "user@example.com") == "user@example.com"

    def test_validate_files_reports_required_and_optional_states(self):
        results = self.validator.validate_files()

        assert ("config/client_secrets.json", "ERROR", "Required file not found") in results
        assert ("config/token.json", "INFO", "Optional file not found (will be created)") in results

    def test_validate_files_validates_client_secrets_structure(self):
        client_secrets = self.project_root / "config" / "client_secrets.json"
        client_secrets.write_text(json.dumps({"installed": {"client_id": "id"}}))

        results = self.validator.validate_files()
        status = next(result for result in results if result[0] == "config/client_secrets.json")

        assert status[1] == "ERROR"
        assert "Missing required field" in status[2]

    def test_generate_config_report_includes_summary(self):
        self.validator.env_values = {
            "TARGET_SENDERS": "user@example.com",
            "TARGET_KEYWORDS": "statement",
            "OPENAI_API_KEY": "sk-12345678901234567890",
        }
        (self.project_root / "config" / "client_secrets.json").write_text(
            json.dumps(
                {
                    "installed": {
                        "client_id": "id",
                        "client_secret": "secret",
                        "redirect_uris": ["http://localhost"],
                    }
                }
            )
        )

        report = self.validator.generate_config_report()

        assert "Configuration Validation Report" in report
        assert "Environment:" in report
        assert "Files:" in report
        assert "Summary:" in report

    def test_validate_all_returns_true_for_complete_valid_setup(self):
        (self.project_root / ".env").write_text(
            "\n".join(
                [
                    "TARGET_SENDERS=user@example.com",
                    "TARGET_KEYWORDS=statement,invoice",
                    "OPENAI_API_KEY=sk-1234567890123456789012345",
                    "OAUTH_PORT=8080",
                ]
            )
        )
        (self.project_root / "config" / "client_secrets.json").write_text(
            json.dumps(
                {
                    "installed": {
                        "client_id": "id",
                        "client_secret": "secret",
                        "redirect_uris": ["http://localhost"],
                    }
                }
            )
        )

        assert self.validator.validate_all() is True

    def test_validate_all_returns_false_when_environment_load_fails(self):
        with patch.object(self.validator, "load_environment", side_effect=ConfigValidationError("bad env")):
            assert self.validator.validate_all() is False
