"""Startup configuration check: fail fast on the one thing we cannot run without."""
import json
import logging
import os

from src.core.config import OAUTH_CLIENT_SECRETS_PATH

logger = logging.getLogger(__name__)


def validate_configuration() -> bool:
    """Return True when the OAuth client secrets file exists and is valid JSON."""
    path = OAUTH_CLIENT_SECRETS_PATH
    if not os.path.isfile(path):
        logger.error(f"OAuth client secrets not found at {path}; see config/README.md")
        return False
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"OAuth client secrets at {path} is not readable JSON: {e}")
        return False
    if not isinstance(data, dict) or not (data.get('installed') or data.get('web')):
        logger.error(f"OAuth client secrets at {path} lacks an 'installed' or 'web' section")
        return False
    return True
