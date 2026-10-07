"""Comprehensive tests for src/auth/gmail_auth.py."""

from unittest.mock import Mock, patch

import pytest

import src.integrations.gmail.auth as gmail_auth

def _wrapped_get_gmail_service():
    return gmail_auth.get_gmail_service

def test_atomic_write_text(tmp_path):
    json_path = tmp_path / "token.json"
    gmail_auth._atomic_write_text(str(json_path), '{"ok": true}')

    assert json_path.read_text(encoding="utf-8") == '{"ok": true}'

def test_load_credentials_from_token_file_json():
    fake_creds = Mock()

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_file", return_value=fake_creds):
        assert gmail_auth._load_credentials_from_token_file("token.json") is fake_creds


def test_load_credentials_corrupted_token_quarantine():
    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_file", side_effect=ValueError("bad json")), \
         patch("src.integrations.gmail.auth.os.replace") as mock_replace, \
         patch("src.integrations.gmail.auth.os.remove"):
        out = gmail_auth._load_credentials_from_token_file("token.json")

    assert out is None
    assert mock_replace.called

def test_save_credentials_to_token_file_json():
    json_creds = Mock()
    json_creds.to_json.return_value = '{"token":"x"}'

    with patch("src.integrations.gmail.auth._atomic_write_text") as mock_text:
        gmail_auth._save_credentials_to_token_file(json_creds, "token.json")

    mock_text.assert_called_once_with("token.json", '{"token":"x"}')

def test_get_gmail_service_with_valid_token():
    """Fix for failure #1: include os.path.exists mock for client secrets check."""
    fn = _wrapped_get_gmail_service()

    creds = Mock(valid=True, expired=False)
    service = Mock()

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", return_value=service):
        out = fn(client_secrets_path="client_secrets.json", token_path="token.json", port=8080)

    assert out is service

def test_get_gmail_service_with_expired_token_refresh_success():
    """Fix for failure #2: include os.path.exists mock and refresh path assertions."""
    fn = _wrapped_get_gmail_service()

    creds = Mock(valid=False, expired=True, refresh_token="refresh")
    creds.refresh.side_effect = lambda *_: setattr(creds, "valid", True)
    service = Mock()

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", return_value=service):
        out = fn(client_secrets_path="client_secrets.json", token_path="token.json", port=8080)

    creds.refresh.assert_called_once()
    assert out is service

def test_get_gmail_service_token_save_failure(monkeypatch):
    """Fix for failure #5: token save helper logs warning instead of crashing."""
    creds = Mock()
    creds.to_json.return_value = '{"token":"x"}'

    with patch("src.integrations.gmail.auth._atomic_write_text", side_effect=OSError("permission denied")), \
         patch("src.integrations.gmail.auth.logger.warning") as mock_warn:
        # Should not raise
        gmail_auth._save_credentials_to_token_file(creds, "token.json")

    assert mock_warn.called

def test_get_gmail_service_missing_client_secrets_and_build_failure():
    fn = _wrapped_get_gmail_service()

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            fn(client_secrets_path="missing.json", token_path="token.json", port=8080)

    creds = Mock(valid=True, expired=False)
    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", side_effect=RuntimeError("build fail")):
        with pytest.raises(ValueError):
            fn(client_secrets_path="client_secrets.json", token_path="token.json", port=8080)
