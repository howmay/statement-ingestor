"""
PDF extraction cache for performance optimization.
"""
import os
import hashlib
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PDFCache:
    """
    Cache for PDF extraction results to avoid redundant processing.
    """
    
    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: int = 24):
        """
        Initialize PDF cache.
        
        Args:
            cache_dir: Directory for cache files. Defaults to ~/.cache/gmail-expense-parser/pdf_cache.
            ttl_hours: Time-to-live for cache entries in hours.
        """
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.cache/gmail-expense-parser/pdf_cache")
        
        self.cache_dir = cache_dir
        self.ttl_hours = ttl_hours
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_key(self, pdf_path: str, password: Optional[str] = None) -> str:
        """
        Generate cache key from PDF file and password.
        
        Args:
            pdf_path: Path to PDF file.
            password: Optional password.
        
        Returns:
            Cache key string.
        """
        # Get file metadata
        stat = os.stat(pdf_path)
        file_info = f"{pdf_path}:{stat.st_size}:{stat.st_mtime}"
        
        if password:
            file_info += f":{password}"
        
        # Create hash
        return hashlib.md5(file_info.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> str:
        """
        Get cache file path for a key.
        
        Args:
            cache_key: Cache key.
        
        Returns:
            Path to cache file.
        """
        return os.path.join(self.cache_dir, f"{cache_key}.json")
    
    def get(self, pdf_path: str, password: Optional[str] = None) -> Optional[str]:
        """
        Get cached extraction result.
        
        Args:
            pdf_path: Path to PDF file.
            password: Optional password.
        
        Returns:
            Cached text if available and not expired, None otherwise.
        """
        if not os.path.exists(pdf_path):
            return None
        
        cache_key = self._get_cache_key(pdf_path, password)
        cache_path = self._get_cache_path(cache_key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check TTL
            cached_time = datetime.fromisoformat(cache_data['timestamp'])
            if datetime.now() - cached_time > timedelta(hours=self.ttl_hours):
                logger.debug(f"Cache entry expired for {pdf_path}")
                os.remove(cache_path)  # Clean up expired cache
                return None
            
            # Verify file hasn't changed
            stat = os.stat(pdf_path)
            if cache_data['file_size'] != stat.st_size or cache_data['file_mtime'] != stat.st_mtime:
                logger.debug(f"File changed, cache invalid for {pdf_path}")
                return None
            
            logger.debug(f"Cache hit for {pdf_path}")
            return cache_data['text']
        
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning(f"Cache corrupted for {pdf_path}: {e}")
            # Clean up corrupted cache
            try:
                os.remove(cache_path)
            except OSError:
                pass
            return None
    
    def set(self, pdf_path: str, text: str, password: Optional[str] = None):
        """
        Cache extraction result.
        
        Args:
            pdf_path: Path to PDF file.
            text: Extracted text.
            password: Optional password.
        """
        if not os.path.exists(pdf_path):
            return
        
        cache_key = self._get_cache_key(pdf_path, password)
        cache_path = self._get_cache_path(cache_key)
        
        try:
            stat = os.stat(pdf_path)
            cache_data = {
                'text': text,
                'file_size': stat.st_size,
                'file_mtime': stat.st_mtime,
                'timestamp': datetime.now().isoformat(),
                'pdf_path': pdf_path,
                'has_password': password is not None
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Cached extraction for {pdf_path}")
        
        except (IOError, OSError) as e:
            logger.warning(f"Failed to cache extraction for {pdf_path}: {e}")
    
    def clear_expired(self):
        """
        Clear expired cache entries.
        """
        expired_count = 0
        now = datetime.now()
        
        for filename in os.listdir(self.cache_dir):
            if not filename.endswith('.json'):
                continue
            
            cache_path = os.path.join(self.cache_dir, filename)
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cached_time = datetime.fromisoformat(cache_data['timestamp'])
                if now - cached_time > timedelta(hours=self.ttl_hours):
                    os.remove(cache_path)
                    expired_count += 1
            
            except (json.JSONDecodeError, KeyError, IOError):
                # Remove corrupted cache files
                try:
                    os.remove(cache_path)
                    expired_count += 1
                except OSError:
                    pass
        
        if expired_count > 0:
            logger.info(f"Cleared {expired_count} expired cache entries")
    
    def clear_all(self):
        """
        Clear all cache entries.
        """
        count = 0
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                cache_path = os.path.join(self.cache_dir, filename)
                try:
                    os.remove(cache_path)
                    count += 1
                except OSError:
                    pass
        
        logger.info(f"Cleared all {count} cache entries")


# Global cache instance
_global_cache: Optional[PDFCache] = None


def get_pdf_cache() -> PDFCache:
    """
    Get global PDF cache instance.
    
    Returns:
        Global PDFCache instance.
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = PDFCache()
    return _global_cache


def clear_pdf_cache():
    """
    Clear global PDF cache.
    """
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear_all()