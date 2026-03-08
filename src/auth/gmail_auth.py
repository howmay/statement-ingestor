import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging
from src.config import OAUTH_CLIENT_SECRETS_PATH, OAUTH_TOKEN_PATH

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Default paths (imported from config)
DEFAULT_CLIENT_SECRETS_FILE = OAUTH_CLIENT_SECRETS_PATH
DEFAULT_TOKEN_FILE = OAUTH_TOKEN_PATH


def get_gmail_service(client_secrets_path=None, token_path=None):
    """
    Authenticate and return a Gmail API service object using OAuth2.
    
    Args:
        client_secrets_path (str): Path to client_secrets.json file.
                                   Defaults to 'config/client_secrets.json'.
        token_path (str): Path to store/load the token file.
                          Defaults to 'config/token.json'.
    
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
    
    # Check if client secrets file exists
    if not os.path.exists(client_secrets_path):
        raise FileNotFoundError(
            f"Client secrets file not found at '{client_secrets_path}'. "
            "Please follow the instructions in config/README.md to create it."
        )
    
    creds = None
    
    # Load existing token if available
    if os.path.exists(token_path):
        logger.info(f"Loading credentials from {token_path}")
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            logger.info(f"Starting OAuth2 flow with {client_secrets_path}")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_path, SCOPES
                )
                creds = flow.run_local_server(port=8080)
            except Exception as e:
                raise ValueError(f"OAuth2 flow failed: {e}")
            
            # Save the credentials for the next run
            logger.info(f"Saving credentials to {token_path}")
            try:
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
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