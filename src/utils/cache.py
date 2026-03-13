import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ResultCache:
    """Simple file-based cache for LLM parsing results."""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def _get_cache_key(self, text: str, extra: str = "") -> str:
        """Generate a stable key for the given text and extra metadata."""
        hasher = hashlib.md5()
        hasher.update(text.encode('utf-8'))
        if extra:
            hasher.update(extra.encode('utf-8'))
        return hasher.hexdigest()
        
    def get(self, text: str, extra: str = "") -> Optional[Dict[str, Any]]:
        """Retrieve cached result if available."""
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
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
