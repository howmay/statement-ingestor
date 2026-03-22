import os
import json
import hashlib
import logging
import sqlite3
from contextlib import closing
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _is_truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}

class ResultCache:
    """Simple file-based cache for LLM parsing results."""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir
        self.content_cache_enabled = _is_truthy_env("ENABLE_CONTENT_CACHE", "false")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.db_path = os.path.join(self.cache_dir, "performance_index.sqlite3")
        self._init_index_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_index_db(self) -> None:
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_fingerprints (
                        path TEXT PRIMARY KEY,
                        size INTEGER NOT NULL,
                        mtime REAL NOT NULL,
                        md5 TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS downloaded_attachments (
                        message_id TEXT NOT NULL,
                        attachment_id TEXT NOT NULL,
                        original_filename TEXT,
                        downloaded_filepath TEXT NOT NULL,
                        size INTEGER,
                        md5 TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (message_id, attachment_id)
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Error initializing cache index database {self.db_path}: {e}")

    def _get_cached_file_fingerprint(self, filepath: str, size: int, mtime: float) -> Optional[str]:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    """
                    SELECT md5 FROM file_fingerprints
                    WHERE path = ? AND size = ? AND mtime = ?
                    """,
                    (filepath, size, mtime),
                ).fetchone()
        except Exception as e:
            logger.warning(f"Error reading file fingerprint cache for {filepath}: {e}")
            return None

        return str(row[0]) if row else None

    def _store_file_fingerprint(self, filepath: str, size: int, mtime: float, md5: str) -> None:
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO file_fingerprints(path, size, mtime, md5, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(path) DO UPDATE SET
                        size = excluded.size,
                        mtime = excluded.mtime,
                        md5 = excluded.md5,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (filepath, size, mtime, md5),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Error writing file fingerprint cache for {filepath}: {e}")

    def store_file_md5(self, filepath: str, md5: str) -> None:
        """Persist a known file MD5 using the file's current metadata."""
        if not filepath or not md5 or not os.path.exists(filepath):
            return

        try:
            stat_info = os.stat(filepath)
        except OSError:
            return

        self._store_file_fingerprint(filepath, stat_info.st_size, stat_info.st_mtime, md5)

    def get_downloaded_attachment_reference(self, message_id: str, attachment_id: str) -> Optional[Dict[str, Any]]:
        if not message_id or not attachment_id:
            return None

        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    """
                    SELECT original_filename, downloaded_filepath, size, md5, updated_at
                    FROM downloaded_attachments
                    WHERE message_id = ? AND attachment_id = ?
                    """,
                    (message_id, attachment_id),
                ).fetchone()
        except Exception as e:
            logger.warning(
                f"Error reading downloaded attachment reference for {message_id}/{attachment_id}: {e}"
            )
            return None

        if not row:
            return None

        return {
            "message_id": message_id,
            "attachment_id": attachment_id,
            "original_filename": row[0],
            "downloaded_filepath": row[1],
            "size": row[2],
            "md5": row[3],
            "updated_at": row[4],
        }

    def find_downloaded_attachment_reference(
        self,
        message_id: str,
        original_filename: str,
        size: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        if not message_id or not original_filename or size is None:
            return None

        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    """
                    SELECT attachment_id, original_filename, downloaded_filepath, size, md5, updated_at
                    FROM downloaded_attachments
                    WHERE message_id = ? AND original_filename = ? AND size = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (message_id, original_filename, size),
                ).fetchone()
        except Exception as e:
            logger.warning(
                f"Error reading downloaded attachment reference for {message_id}/{original_filename}/{size}: {e}"
            )
            return None

        if not row:
            return None

        return {
            "message_id": message_id,
            "attachment_id": row[0],
            "original_filename": row[1],
            "downloaded_filepath": row[2],
            "size": row[3],
            "md5": row[4],
            "updated_at": row[5],
        }

    def store_downloaded_attachment_reference(
        self,
        message_id: str,
        attachment_id: str,
        original_filename: str,
        downloaded_filepath: str,
        size: int,
        md5: str,
    ) -> None:
        if not message_id or not attachment_id or not downloaded_filepath:
            return

        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO downloaded_attachments(
                        message_id,
                        attachment_id,
                        original_filename,
                        downloaded_filepath,
                        size,
                        md5,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(message_id, attachment_id) DO UPDATE SET
                        original_filename = excluded.original_filename,
                        downloaded_filepath = excluded.downloaded_filepath,
                        size = excluded.size,
                        md5 = excluded.md5,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (message_id, attachment_id, original_filename, downloaded_filepath, size, md5),
                )
                conn.commit()
        except Exception as e:
            logger.warning(
                f"Error writing downloaded attachment reference for {message_id}/{attachment_id}: {e}"
            )

    def delete_downloaded_attachment_reference(self, message_id: str, attachment_id: str) -> None:
        if not message_id or not attachment_id:
            return

        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    DELETE FROM downloaded_attachments
                    WHERE message_id = ? AND attachment_id = ?
                    """,
                    (message_id, attachment_id),
                )
                conn.commit()
        except Exception as e:
            logger.warning(
                f"Error deleting downloaded attachment reference for {message_id}/{attachment_id}: {e}"
            )

    def delete_downloaded_attachment_references_by_message_file(
        self,
        message_id: str,
        original_filename: str,
        size: Optional[int],
    ) -> None:
        if not message_id or not original_filename or size is None:
            return

        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    DELETE FROM downloaded_attachments
                    WHERE message_id = ? AND original_filename = ? AND size = ?
                    """,
                    (message_id, original_filename, size),
                )
                conn.commit()
        except Exception as e:
            logger.warning(
                f"Error deleting downloaded attachment reference for {message_id}/{original_filename}/{size}: {e}"
            )
        
    def _get_cache_key(self, text: str, extra: str = "") -> str:
        """Generate a stable key for the given text and extra metadata."""
        hasher = hashlib.md5()
        hasher.update(text.encode('utf-8'))
        if extra:
            hasher.update(extra.encode('utf-8'))
        return hasher.hexdigest()
        
    def get(self, text: str, extra: str = "") -> Optional[Dict[str, Any]]:
        """Retrieve cached result if available."""
        if not self.content_cache_enabled:
            return None

        key = self._get_cache_key(text, extra)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    logger.debug(f"Cache hit for key {key}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading cache file {cache_path}: {e}")
                
        return None
        
    def set(self, text: str, result: Dict[str, Any], extra: str = ""):
        """Store result in cache."""
        if not self.content_cache_enabled:
            return

        key = self._get_cache_key(text, extra)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.debug(f"Cached result for key {key}")
        except Exception as e:
            logger.warning(f"Error writing cache file {cache_path}: {e}")

    def get_file_md5(self, filepath: str) -> Optional[str]:
        """Compute MD5 of a file."""
        if not os.path.exists(filepath):
            return None

        try:
            stat_info = os.stat(filepath)
        except OSError:
            return None

        cached_md5 = self._get_cached_file_fingerprint(filepath, stat_info.st_size, stat_info.st_mtime)
        if cached_md5:
            return cached_md5

        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        md5 = hasher.hexdigest()
        self._store_file_fingerprint(filepath, stat_info.st_size, stat_info.st_mtime, md5)
        return md5
