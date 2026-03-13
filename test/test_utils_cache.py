from pathlib import Path
from unittest.mock import patch

import src.utils.cache as cache_mod


def test_result_cache_set_get_and_key(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path))

    key1 = cache._get_cache_key("abc", "x")
    key2 = cache._get_cache_key("abc", "x")
    assert key1 == key2

    payload = {"transactions": [{"amount": 100}]}
    cache.set("abc", payload, extra="x")
    out = cache.get("abc", extra="x")
    assert out == payload


def test_result_cache_get_handles_broken_json(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path))
    key = cache._get_cache_key("abc", "x")
    (Path(tmp_path) / f"{key}.json").write_text("{bad json", encoding="utf-8")

    out = cache.get("abc", extra="x")
    assert out is None


def test_result_cache_set_handles_write_error(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path))

    with patch("builtins.open", side_effect=OSError("no space")):
        # Should swallow and not raise
        cache.set("abc", {"k": 1}, extra="x")


def test_get_file_md5(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path))

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    md5 = cache.get_file_md5(str(f))
    assert isinstance(md5, str)
    assert len(md5) == 32

    assert cache.get_file_md5(str(tmp_path / "missing.txt")) is None
