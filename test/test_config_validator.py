import json

from src.support import config_validator


def _check(monkeypatch, tmp_path, content):
    path = tmp_path / "client_secrets.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(config_validator, "OAUTH_CLIENT_SECRETS_PATH", str(path))
    return config_validator.validate_configuration()


def test_missing_file(monkeypatch, tmp_path):
    assert _check(monkeypatch, tmp_path, None) is False


def test_invalid_json(monkeypatch, tmp_path):
    assert _check(monkeypatch, tmp_path, "{not json") is False


def test_non_dict_root(monkeypatch, tmp_path):
    assert _check(monkeypatch, tmp_path, json.dumps([1, 2])) is False


def test_valid_installed(monkeypatch, tmp_path):
    assert _check(monkeypatch, tmp_path, json.dumps({"installed": {"client_id": "x"}})) is True
