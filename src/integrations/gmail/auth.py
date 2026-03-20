import json
import os
import pickle
import sys
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.discovery import build
import logging
from src.core.config import OAUTH_CLIENT_SECRETS_PATH, OAUTH_TOKEN_PATH, OAUTH_PORT
from src.support.retry import retry_gmail

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Default paths (imported from config)
DEFAULT_CLIENT_SECRETS_FILE = OAUTH_CLIENT_SECRETS_PATH
DEFAULT_TOKEN_FILE = OAUTH_TOKEN_PATH

def _is_json_token_path(token_path: str) -> bool:
    return str(token_path).lower().endswith('.json')

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

def _atomic_write_bytes(filepath: str, content: bytes) -> None:
    """Atomically write binary file to avoid partial token corruption."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('wb', delete=False, dir=os.path.dirname(filepath) or '.') as tf:
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
    """Load credentials from token file with JSON-first + pickle fallback."""
    if not os.path.exists(token_path):
        return None

    logger.info(f"Loading credentials from {token_path}")

    json_error = None
    pickle_error = None

    # If path is .json, prefer modern google-auth JSON format
    if _is_json_token_path(token_path):
        try:
            return Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            json_error = e
            logger.warning(f"Failed to parse JSON token, trying pickle fallback: {e}")

    # Legacy pickle fallback
    try:
        with open(token_path, 'rb') as token:
            return pickle.load(token)
    except Exception as e:
        pickle_error = e
        logger.warning(f"Failed to load token: {e}")

    # Both loaders failed; quarantine broken token to avoid repeated warnings.
    try:
        corrupted_path = f"{token_path}.corrupted"
        if os.path.exists(corrupted_path):
            os.remove(corrupted_path)
        os.replace(token_path, corrupted_path)
        logger.warning(
            f"Token file appears corrupted. Moved to {corrupted_path}. "
            f"json_error={json_error}, pickle_error={pickle_error}"
        )
    except Exception:
        pass

    return None

def _save_credentials_to_token_file(creds, token_path: str) -> None:
    """Save credentials to token file, using JSON for *.json path."""
    logger.info(f"Saving credentials to {token_path}")
    try:
        if _is_json_token_path(token_path):
            _atomic_write_text(token_path, creds.to_json())
        else:
            _atomic_write_bytes(token_path, pickle.dumps(creds))
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
        service.users().getProfile(userId='me').execute()
        return True
    except Exception as e:
        logger.warning(f"Token usability test failed: {e}")
        return False

def _describe_manual_token(manual_token) -> str:
    """Return a safe, non-secret description for manual token logging."""
    if isinstance(manual_token, dict):
        token_value = str(manual_token.get('token', '') or '')
        has_refresh = bool(manual_token.get('refresh_token'))
        return (
            "authorized-user info provided "
            f"(token_length={len(token_value)}, refresh_token={'yes' if has_refresh else 'no'})"
        )

    token_value = str(manual_token or '')
    return f"access token provided (token_length={len(token_value)})"

def _get_oauth2_client_id_secret():
    """
    Get OAuth2 Client ID and Secret from environment or file.
    
    Returns:
        tuple: (client_id, client_secret)
    """
    # Try environment variables first
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if client_id and client_secret:
        return client_id, client_secret
    
    # Try to load from client_secrets.json
    if os.path.exists(DEFAULT_CLIENT_SECRETS_FILE):
        import json
        with open(DEFAULT_CLIENT_SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
            web_client = secrets.get('web', {})
            return web_client.get('client-id'), web_client.get('client-secret')
    
    # If nothing found, raise error
    raise ValueError(
        "OAuth2 Client ID and Secret not found. "
        "Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables, "
        "or create a client_secrets.json file."
    )

@retry_gmail
def get_gmail_service(client_secrets_path=None, token_path=None, port=None, 
                      manual_token=None, oob_callback=False):
    """
    Authenticate and return a Gmail API service object using OAuth2 with retry mechanism.
    
    Args:
        client_secrets_path (str): Path to client_secrets.json file.
                                   Defaults to 'config/client_secrets.json'.
        token_path (str): Path to store/load the token file.
                          Defaults to 'config/token.json'.
        port (int): Port for the local OAuth2 server.
                    Defaults to OAUTH_PORT from config (8080).
        manual_token (str): If provided, use this token directly without interactive flow.
                            Useful when local server OAuth fails (e.g., network issues).
                            Format: Access token string from Google Cloud Console.
        oob_callback (bool): Use out-of-band (OOB) flow for direct token copying.
                             Set to True when running on remote server via SSH.
    
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
        # Check if manual token is provided
        if manual_token:
            try:
                if isinstance(manual_token, dict):
                    logger.info(f"Using manual token: {_describe_manual_token(manual_token)}")
                    creds = Credentials.from_authorized_user_info(manual_token, SCOPES)
                elif isinstance(manual_token, str):
                    logger.info(f"Using manual token: {_describe_manual_token(manual_token)}")
                    creds = Credentials(
                        token=manual_token,
                        token_uri='https://oauth2.googleapis.com/token',
                        revoke_url='https://oauth2.googleapis.com/revoke',
                        refresh_url='https://oauth2.googleapis.com/token'
                    )
                else:
                    raise ValueError("manual_token must be a string token or authorized-user dict")

                # Test if the manual token works
                if not _test_token_usable(creds):
                    logger.warning("Manual token failed API test.")
                    raise ValueError("Manual token invalid. Please get a fresh token from Google Cloud Console.")
            except Exception as e:
                raise ValueError(f"Failed to use manual token: {e}. "
                               "Try using the interactive OAuth flow instead.")
        elif oob_callback:
            # Use OOB (Out of Band) flow for direct token copying
            logger.info("Using OOB (Out of Band) OAuth flow...")
            logger.info("=" * 60)
            logger.info("AUTHORIZATION URL:")
            logger.info("=" * 60)
            
            client_id, client_secret = _get_oauth2_client_id_secret()
            
            # Create flow with OOB callback
            flow = Flow.from_client_config(
                {'web': {'client-id': client_id, 'client-secret': client_secret}},
                scopes=SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            # Get authorization URL
            auth_url = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            
            # Print authorization URL
            print(f"\n{auth_url}")
            logger.info("=" * 60)
            logger.info("1. 複製上面的 URL")
            logger.info("2. 開啟瀏覽器，貼上 URL 並按 Enter")
            logger.info("3. 授權後，複製授權碼（authorization code）")
            logger.info("4. 貼到下面的提示：")
            logger.info("=" * 60)
            
            # Wait for user to input the authorization code
            auth_code = input("請輸入授權碼：").strip()
            
            # Exchange authorization code for tokens
            flow.fetch_token(authorization_response=auth_code)
            creds = flow.credentials
            
            logger.info("=" * 60)
            logger.info("Authorization successful!")

            # Save the credentials for the next run
            try:
                _save_credentials_to_token_file(creds, token_path)
            except Exception as e:
                logger.warning(f"Failed to save token: {e}")

        elif creds and creds.expired and creds.refresh_token:
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
                # If local server fails, offer manual token option
                raise ValueError(f"OAuth2 flow failed on port {port}: {e}. "
                               f"Try setting OAUTH_PORT environment variable to a different port (e.g., 8081). "
                               f"Or try using manual token with --manual-token parameter. "
                               f"Or try OOB flow with --oob")
            
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

def test_auth():
    """Simple test function to verify authentication works."""
    try:
        service = get_gmail_service()
        # Call the Gmail API to verify access
        profile = service.users().getProfile(userId='me').execute()
        logger.info(f"Authenticated as: {profile.get('emailAddress')}")
        return True
    except Exception as e:
        logger.error(f"Authentication test failed: {e}")
        return False

if __name__ == '__main__':
    # When run directly, test the authentication
    print("Testing Gmail OAuth2 authentication...")
    if test_auth():
        print("✓ Authentication successful!")
    else:
        print("✗ Authentication failed. Check the logs above.")
