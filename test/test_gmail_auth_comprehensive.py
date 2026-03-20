"""Comprehensive tests for src/auth/gmail_auth.py."""

import json
from unittest.mock import Mock, mock_open, patch

import pytest

import src.integrations.gmail.auth as gmail_auth

@pytest.fixture(autouse=True)
def disable_retry_sleep(monkeypatch):
    # Avoid waiting when retry wrappers are active.
    monkeypatch.setattr("src.support.retry.time.sleep", lambda *_: None)

def _wrapped_get_gmail_service():
    # get_gmail_service is decorated; test core logic directly.
    return gmail_auth.get_gmail_service.__wrapped__

def test_is_json_token_path_and_atomic_writes(tmp_path):
    assert gmail_auth._is_json_token_path("token.json") is True
    assert gmail_auth._is_json_token_path("token.pickle") is False

    json_path = tmp_path / "token.json"
    bin_path = tmp_path / "token.bin"
    gmail_auth._atomic_write_text(str(json_path), '{"ok": true}')
    gmail_auth._atomic_write_bytes(str(bin_path), b"ok")

    assert json_path.read_text(encoding="utf-8") == '{"ok": true}'
    assert bin_path.read_bytes() == b"ok"

def test_load_credentials_from_token_file_json_and_pickle_paths():
    fake_creds = Mock()

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_file", return_value=fake_creds):
        assert gmail_auth._load_credentials_from_token_file("token.json") is fake_creds

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_file", side_effect=ValueError("bad json")), \
         patch("builtins.open", mock_open(read_data=b"x")), \
         patch("src.integrations.gmail.auth.pickle.load", return_value=fake_creds):
        assert gmail_auth._load_credentials_from_token_file("token.json") is fake_creds

def test_load_credentials_corrupted_token_quarantine():
    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_file", side_effect=ValueError("bad json")), \
         patch("builtins.open", mock_open(read_data=b"x")), \
         patch("src.integrations.gmail.auth.pickle.load", side_effect=Exception("bad pickle")), \
         patch("src.integrations.gmail.auth.os.replace") as mock_replace, \
         patch("src.integrations.gmail.auth.os.remove"):
        out = gmail_auth._load_credentials_from_token_file("token.json")

    assert out is None
    assert mock_replace.called

def test_save_credentials_to_token_file_json_and_pickle():
    json_creds = Mock()
    json_creds.to_json.return_value = '{"token":"x"}'
    pickle_creds = {"token": "x"}

    with patch("src.integrations.gmail.auth._atomic_write_text") as mock_text, \
         patch("src.integrations.gmail.auth._atomic_write_bytes") as mock_bytes:
        gmail_auth._save_credentials_to_token_file(json_creds, "token.json")
        gmail_auth._save_credentials_to_token_file(pickle_creds, "token.pickle")

    mock_text.assert_called_once()
    mock_bytes.assert_called_once()

def test_get_oauth2_client_id_secret_env_file_and_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    assert gmail_auth._get_oauth2_client_id_secret() == ("cid", "sec")

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    payload = {"web": {"client-id": "file-cid", "client-secret": "file-secret"}}
    with patch("src.integrations.gmail.auth.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(payload))):
        assert gmail_auth._get_oauth2_client_id_secret() == ("file-cid", "file-secret")

    with patch("src.integrations.gmail.auth.os.path.exists", return_value=False):
        with pytest.raises(ValueError):
            gmail_auth._get_oauth2_client_id_secret()

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

def test_get_gmail_service_new_authentication_oob_flow(monkeypatch):
    """Fix for failure #3: fully mock OOB stdin/stdout path."""
    fn = _wrapped_get_gmail_service()

    flow = Mock()
    flow.authorization_url.return_value = "https://auth.example.com"
    flow.credentials = Mock(valid=True)
    service = Mock()

    # client secrets exists; token missing -> trigger auth flow
    def exists_side_effect(path):
        return path == "client_secrets.json"

    with patch("src.integrations.gmail.auth.os.path.exists", side_effect=exists_side_effect), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=None), \
         patch("src.integrations.gmail.auth._get_oauth2_client_id_secret", return_value=("cid", "sec")), \
         patch("src.integrations.gmail.auth.Flow.from_client_config", return_value=flow), \
         patch("builtins.input", return_value="auth-code"), \
         patch("src.integrations.gmail.auth._save_credentials_to_token_file") as mock_save, \
         patch("src.integrations.gmail.auth.build", return_value=service):
        out = fn(
            client_secrets_path="client_secrets.json",
            token_path="token.json",
            port=8080,
            oob_callback=True,
        )

    flow.fetch_token.assert_called_once()
    mock_save.assert_called_once()
    assert out is service

def test_get_gmail_service_manual_token_flow():
    """Fix for failure #4: use real string token (slice-able), not magic mock token."""
    fn = _wrapped_get_gmail_service()

    creds = Mock(valid=True)
    service = Mock()

    def exists_side_effect(path):
        return path == "client_secrets.json"

    with patch("src.integrations.gmail.auth.os.path.exists", side_effect=exists_side_effect), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=None), \
         patch("src.integrations.gmail.auth.Credentials", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", return_value=service):
        out = fn(
            client_secrets_path="client_secrets.json",
            token_path="token.json",
            port=8080,
            manual_token="test_manual_token_12345",
        )

    assert out is service

def test_get_gmail_service_manual_token_logs_are_masked_string_token():
    fn = _wrapped_get_gmail_service()

    creds = Mock(valid=True)
    service = Mock()
    manual_token = "test_manual_token_12345"

    def exists_side_effect(path):
        return path == "client_secrets.json"

    with patch("src.integrations.gmail.auth.os.path.exists", side_effect=exists_side_effect), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=None), \
         patch("src.integrations.gmail.auth.Credentials", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", return_value=service), \
         patch("src.integrations.gmail.auth.logger.info") as mock_info:
        out = fn(
            client_secrets_path="client_secrets.json",
            token_path="token.json",
            port=8080,
            manual_token=manual_token,
        )

    assert out is service
    logged = "\n".join(str(call.args[0]) for call in mock_info.call_args_list if call.args)
    assert manual_token not in logged
    assert manual_token[:20] not in logged
    assert "manual token" in logged.lower()

def test_get_gmail_service_manual_token_logs_are_masked_dict_token():
    fn = _wrapped_get_gmail_service()

    creds = Mock(valid=True)
    service = Mock()
    manual_token = {"token": "dict_sensitive_token_12345", "refresh_token": "refresh"}

    def exists_side_effect(path):
        return path == "client_secrets.json"

    with patch("src.integrations.gmail.auth.os.path.exists", side_effect=exists_side_effect), \
         patch("src.integrations.gmail.auth._load_credentials_from_token_file", return_value=None), \
         patch("src.integrations.gmail.auth.Credentials.from_authorized_user_info", return_value=creds), \
         patch("src.integrations.gmail.auth._test_token_usable", return_value=True), \
         patch("src.integrations.gmail.auth.build", return_value=service), \
         patch("src.integrations.gmail.auth.logger.info") as mock_info:
        out = fn(
            client_secrets_path="client_secrets.json",
            token_path="token.json",
            port=8080,
            manual_token=manual_token,
        )

    assert out is service
    logged = "\n".join(str(call.args[0]) for call in mock_info.call_args_list if call.args)
    assert manual_token["token"] not in logged
    assert manual_token["token"][:20] not in logged
    assert "manual token" in logged.lower()

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

def test_test_auth_helper_success_and_failure():
    with patch("src.integrations.gmail.auth.get_gmail_service") as mock_get:
        svc = Mock()
        svc.users().getProfile().execute.return_value = {"emailAddress": "x@y.com"}
        mock_get.return_value = svc
        assert gmail_auth.test_auth() is True

    with patch("src.integrations.gmail.auth.get_gmail_service", side_effect=RuntimeError("no auth")):
        assert gmail_auth.test_auth() is False
