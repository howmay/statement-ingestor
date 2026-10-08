import os
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

import src.support.cache as cache_mod


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


def test_get_file_md5_recomputes_when_file_changes(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path / "cache"))
    f = tmp_path / "change.txt"
    f.write_text("hello", encoding="utf-8")

    first_md5 = cache.get_file_md5(str(f))

    f.write_text("hello world", encoding="utf-8")
    stat_info = f.stat()
    f.touch()
    f_mtime = max(stat_info.st_mtime + 1, f.stat().st_mtime)
    os.utime(f, (f_mtime, f_mtime))

    second_md5 = cache.get_file_md5(str(f))

    assert first_md5 == hashlib.md5(b"hello").hexdigest()
    assert second_md5 == hashlib.md5(b"hello world").hexdigest()
    assert second_md5 != first_md5


def test_downloaded_path_index(tmp_path):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path / "cache"))
    f = tmp_path / "a.pdf"
    f.write_bytes(b"pdf")

    assert cache.get_downloaded_path("m1/a.pdf/3") is None
    cache.set_downloaded_path("m1/a.pdf/3", str(f))
    assert cache.get_downloaded_path("m1/a.pdf/3") == str(f)

    f.unlink()
    assert cache.get_downloaded_path("m1/a.pdf/3") is None

    (tmp_path / "cache" / "downloads.json").write_text("{bad", encoding="utf-8")
    assert cache.get_downloaded_path("m1/a.pdf/3") is None
    cache.set_downloaded_path("m1/a.pdf/3", str(f))  # corrupt index is replaced
    assert '"m1/a.pdf/3"' in (tmp_path / "cache" / "downloads.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("content", [b"[]", b'{"m1/a.pdf/3": "/x', b"\xff\xfe"])
def test_downloaded_path_index_tolerates_non_dict_or_truncated(tmp_path, content):
    cache = cache_mod.ResultCache(cache_dir=str(tmp_path / "cache"))
    f = tmp_path / "a.pdf"
    f.write_bytes(b"pdf")
    (tmp_path / "cache" / "downloads.json").write_bytes(content)

    assert cache.get_downloaded_path("m1/a.pdf/3") is None
    cache.set_downloaded_path("m1/a.pdf/3", str(f))
    assert cache.get_downloaded_path("m1/a.pdf/3") == str(f)


def test_download_index_survives_concurrent_writers(tmp_path):
    """Four threads indexing at once must not lose each other's entries."""
    import threading
    from src.support.cache import ResultCache
    cache = ResultCache(cache_dir=str(tmp_path))
    (tmp_path / 'f.pdf').write_bytes(b'x')
    def work(i):
        for j in range(20):
            cache.set_downloaded_path(f'msg{i}/{j}', str(tmp_path / 'f.pdf'))
    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert len(cache._read_index()) == 80
