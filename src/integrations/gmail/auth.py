import os
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging
from src.core.config import OAUTH_CLIENT_SECRETS_PATH, OAUTH_TOKEN_PATH, OAUTH_PORT

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Default paths (imported from config)
DEFAULT_CLIENT_SECRETS_FILE = OAUTH_CLIENT_SECRETS_PATH
DEFAULT_TOKEN_FILE = OAUTH_TOKEN_PATH

def _atomic_write_text(filepath: str, content: str) -> None:
    """Atomically write UTF-8 text file to avoid partial token corruption."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=os.path.dirname(filepath) or '.') as tf:
            temp_path = tf.name
            tf.write(content)
        os.replace(temp_path, filepath)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise

def _load_credentials_from_token_file(token_path: str):
    """Load credentials from a JSON token file; quarantine it as .corrupted if unreadable."""
    if not os.path.exists(token_path):
        return None

    logger.info(f"Loading credentials from {token_path}")

    try:
        return Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception as e:
        logger.warning(f"Failed to parse JSON token: {e}")

    try:
        corrupted_path = f"{token_path}.corrupted"
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)
        os.replace(token_path, corrupted_path)
        logger.warning(f"Token file appears corrupted. Moved to {corrupted_path}.")
    except Exception:
        pass

    return None

def _save_credentials_to_token_file(creds, token_path: str) -> None:
    """Save credentials to token file in JSON format only."""
    logger.info(f"Saving credentials to {token_path}")
    try:
        _atomic_write_text(token_path, creds.to_json())
    except Exception as e:
        logger.warning(f"Failed to save token: {e}")

def _test_token_usable(creds):
    """
    Test if the given credentials can actually access the Gmail API.
    
    Args:
        creds: google.oauth2.credentials.Credentials object.
    
    Returns:
        bool: True if token works, False otherwise.
    """
    try:
        service = build('gmail', 'v1', credentials=creds)
        service.users().getProfile(userId='me').execute(num_retries=5)
        return True
    except Exception as e:
        logger.warning(f"Token usability test failed: {e}")
        return False

def get_gmail_service(client_secrets_path=None, token_path=None, port=None):
    """
    Authenticate and return a Gmail API service object using OAuth2.
    
    Args:
        client_secrets_path (str): Path to client_secrets.json file.
                                   Defaults to 'config/client_secrets.json'.
        token_path (str): Path to store/load the token file.
                          Defaults to 'config/token.json'.
        port (int): Port for the local OAuth2 server.
                    Defaults to OAUTH_PORT from config (8080).
    
    Returns:
        googleapiclient.discovery.Resource: Authenticated Gmail API service object.
    
    Raises:
        FileNotFoundError: If client_secrets.json is not found.
        ValueError: If authentication fails.
    """
    if client_secrets_path is None:
        client_secrets_path = DEFAULT_CLIENT_SECRETS_FILE
    if token_path is None:
        token_path = DEFAULT_TOKEN_FILE
    if port is None:
        port = OAUTH_PORT
    
    # Check if client secrets file exists
    if not os.path.exists(client_secrets_path):
        raise FileNotFoundError(
            f"Client secrets file not found at '{client_secrets_path}'. "
            "Please follow the instructions in config/README.md to create it."
        )
    
    creds = None
    
    # Load existing token if available
    creds = _load_credentials_from_token_file(token_path)
    
    # Test cached token usability (even if it appears valid)
    if creds and creds.valid:
        if not _test_token_usable(creds):
            logger.warning("Cached token appears valid but API test failed. Will re-authenticate.")
            creds = None
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            try:
                creds.refresh(Request())
                # Test if refreshed token actually works
                if not _test_token_usable(creds):
                    logger.warning("Refreshed token failed API test. Will re-authenticate.")
                    creds = None
            except Exception as e:
                logger.warning(f"Failed to refresh token: {e}")
                creds = None
        
        # If still no valid credentials, start OAuth2 flow
        if not creds or not creds.valid:
            logger.info(f"Starting OAuth2 flow with {client_secrets_path} on port {port}")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_path, SCOPES
                )
                # Try to run local server
                creds = flow.run_local_server(port=port)
            except Exception as e:
                raise ValueError(f"OAuth2 flow failed on port {port}: {e}. "
                               f"Try setting OAUTH_PORT environment variable to a different port (e.g., 8081).")
            
            # Save the credentials for the next run
            try:
                _save_credentials_to_token_file(creds, token_path)
            except Exception as e:
                logger.warning(f"Failed to save token: {e}")

    # Build the Gmail API service
    try:
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail API service created successfully")
        return service
    except Exception as e:
        raise ValueError(f"Failed to build Gmail service: {e}")
