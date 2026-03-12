"""
Comprehensive unit tests for Gmail authentication module.
This test file aims to increase coverage from 50% to 80%+.
"""
import os
import json
import pickle
import tempfile
from unittest.mock import Mock, patch, mock_open, MagicMock, PropertyMock
import pytest
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.errors import HttpError

# Define a simple picklable class at module level
class SimpleCreds:
    """Simple credentials object for testing."""
    def __init__(self):
        self.valid = True
        self.expired = False
        self.refresh_token = "test_refresh_token"
        self.token = "test_token"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.client_id = "test_client_id"
        self.client_secret = "test_client_secret"
        self.scopes = ['https://www.googleapis.com/auth/gmail.readonly']


from src.auth.gmail_auth import (
    get_gmail_service,
    _test_token_usable,
    _load_credentials_from_token_file,
    _atomic_write_text,
    _atomic_write_bytes,
    _is_json_token_path,
    SCOPES,
    DEFAULT_CLIENT_SECRETS_FILE,
    DEFAULT_TOKEN_FILE
)


class TestGmailAuthComprehensive:
    """Comprehensive test suite for Gmail authentication functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.utils.retry.retry_gmail', side_effect=lambda f: f):
            yield
    
    @pytest.fixture
    def mock_credentials(self):
        """Create mock credentials for testing."""
        creds = Mock(spec=Credentials)
        creds.valid = True
        creds.expired = False
        creds.refresh_token = "refresh_token_123"
        creds.token = "access_token_123"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "client_id_123"
        creds.client_secret = "client_secret_123"
        creds.scopes = SCOPES
        return creds
    
    @pytest.fixture
    def mock_gmail_service(self):
        """Create mock Gmail service."""
        mock_service = Mock()
        mock_service.users().getProfile().execute.return_value = {
            'emailAddress': 'test@example.com'
        }
        return mock_service
    
    # Test helper functions
    
    def test_is_json_token_path(self):
        """Test JSON token path detection."""
        assert _is_json_token_path("token.json") is True
        assert _is_json_token_path("config/token.json") is True
        assert _is_json_token_path("token.JSON") is True
        assert _is_json_token_path("token.pickle") is False
        assert _is_json_token_path("token.txt") is False
        assert _is_json_token_path("token") is False
    
    def test_atomic_write_text_success(self):
        """Test atomic text write operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            filepath = os.path.join(temp_dir, "test.txt")
            content = "test content"
            
            _atomic_write_text(filepath, content)
            
            assert os.path.exists(filepath)
            with open(filepath, 'r', encoding='utf-8') as f:
                assert f.read() == content
    
    def test_atomic_write_text_exception_handling(self):
        """Test atomic text write with exception handling."""
        with patch('os.makedirs') as mock_makedirs:
            mock_makedirs.side_effect = OSError("Permission denied")
            
            with pytest.raises(OSError):
                _atomic_write_text("/invalid/path/test.txt", "content")
    
    def test_atomic_write_bytes_success(self):
        """Test atomic binary write operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            filepath = os.path.join(temp_dir, "test.bin")
            content = b"binary content"
            
            _atomic_write_bytes(filepath, content)
            
            assert os.path.exists(filepath)
            with open(filepath, 'rb') as f:
                assert f.read() == content
    
    def test_atomic_write_bytes_exception_handling(self):
        """Test atomic binary write with exception handling."""
        with patch('os.makedirs') as mock_makedirs:
            mock_makedirs.side_effect = OSError("Permission denied")
            
            with pytest.raises(OSError):
                _atomic_write_bytes("/invalid/path/test.bin", b"content")
    
    # Test _load_credentials_from_token_file
    
    def test_load_credentials_json_success(self):
        """Test loading credentials from JSON token file."""
        token_data = {
            "token": "access_token_123",
            "refresh_token": "refresh_token_123",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id_123",
            "client_secret": "client_secret_123",
            "scopes": SCOPES
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(token_data, f)
            token_path = f.name
        
        try:
            with patch('src.auth.gmail_auth.Credentials.from_authorized_user_file') as mock_from_file:
                mock_creds = Mock(spec=Credentials)
                mock_from_file.return_value = mock_creds
                
                result = _load_credentials_from_token_file(token_path)
                
                assert result == mock_creds
                mock_from_file.assert_called_once_with(token_path, SCOPES)
        finally:
            os.unlink(token_path)
    
    def test_load_credentials_json_fallback_to_pickle(self):
        """Test JSON load failure with pickle fallback."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            token_path = f.name
        
        try:
            # Mock JSON load to fail
            with patch('src.auth.gmail_auth.Credentials.from_authorized_user_file') as mock_json_load:
                mock_json_load.side_effect = ValueError("Invalid JSON")
                
                # Use SimpleCreds which is picklable
                with patch('builtins.open', mock_open(read_data=pickle.dumps(SimpleCreds()))):
                    with patch('pickle.load', return_value=SimpleCreds()):
                        result = _load_credentials_from_token_file(token_path)
                        
                        assert result is not None
                        mock_json_load.assert_called_once_with(token_path, SCOPES)
        finally:
            os.unlink(token_path)
    
    def test_load_credentials_pickle_success(self):
        """Test loading credentials from pickle token file."""
        pickled_data = pickle.dumps(SimpleCreds())
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pickle', delete=False) as f:
            f.write(pickled_data)
            token_path = f.name
        
        try:
            result = _load_credentials_from_token_file(token_path)
            
            assert result is not None
        finally:
            os.unlink(token_path)
    
    def test_load_credentials_both_fail_quarantine(self):
        """Test when both JSON and pickle loading fail."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid content")
            token_path = f.name
        
        try:
            # Mock both loaders to fail
            with patch('src.auth.gmail_auth.Credentials.from_authorized_user_file') as mock_json_load:
                mock_json_load.side_effect = ValueError("Invalid JSON")
                
                with patch('builtins.open', mock_open(read_data=b"invalid pickle")):
                    with patch('pickle.load', side_effect=pickle.UnpicklingError("Invalid pickle")):
                        with patch('os.replace') as mock_replace:
                            result = _load_credentials_from_token_file(token_path)
                            
                            assert result is None
                            # Should quarantine the corrupted file
                            mock_replace.assert_called_once()
        finally:
            if os.path.exists(token_path):
                os.unlink(token_path)
    
    def test_load_credentials_file_not_found(self):
        """Test loading credentials when token file doesn't exist."""
        result = _load_credentials_from_token_file("/nonexistent/path/token.json")
        assert result is None
    
    # Test _test_token_usable
    
    def test_test_token_usable_success(self, mock_credentials, mock_gmail_service):
        """Test token usability check with valid credentials."""
        with patch('src.auth.gmail_auth.build') as mock_build:
            mock_build.return_value = mock_gmail_service
            
            result = _test_token_usable(mock_credentials)
            
            assert result is True
            mock_build.assert_called_once()
            mock_gmail_service.users().getProfile().execute.assert_called_once()
    
    def test_test_token_usable_http_error(self, mock_credentials):
        """Test token usability check with HTTP error."""
        with patch('src.auth.gmail_auth.build') as mock_build:
            mock_service = Mock()
            mock_error = HttpError(resp=Mock(status=403), content=b'Forbidden')
            mock_service.users().getProfile().execute.side_effect = mock_error
            mock_build.return_value = mock_service
            
            result = _test_token_usable(mock_credentials)
            
            assert result is False
    
    def test_test_token_usable_general_exception(self, mock_credentials):
        """Test token usability check with general exception."""
        with patch('src.auth.gmail_auth.build') as mock_build:
            mock_build.side_effect = Exception("General error")
            
            result = _test_token_usable(mock_credentials)
            
            assert result is False
    
    # Test get_gmail_service with comprehensive mock
    
    def test_get_gmail_service_with_valid_token(self):
        """Test getting Gmail service with valid token."""
        mock_credentials = Mock(spec=Credentials)
        mock_credentials.valid = True
        mock_credentials.expired = False
        
        mock_service = Mock()
        mock_service.users().getProfile().execute.return_value = {'emailAddress': 'test@example.com'}
        
        with patch('src.auth.gmail_auth.os.path.exists', return_value=True):
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                with patch('src.auth.gmail_auth._test_token_usable') as mock_test:
                    with patch('src.auth.gmail_auth.build') as mock_build:
                        mock_load.return_value = mock_credentials
                        mock_test.return_value = True
                        mock_build.return_value = mock_service

                        result = get_gmail_service(
                            client_secrets_path="client_secrets.json",
                            token_path="token.json"
                        )
                    
                    assert result == mock_service
                    mock_load.assert_called_once_with("token.json")
                    mock_test.assert_called_once_with(mock_credentials)
                    mock_build.assert_called_once()
    
    def test_get_gmail_service_with_expired_token_refresh_success(self):
        """Test getting Gmail service with expired token that refreshes successfully."""
        mock_credentials = Mock(spec=Credentials)
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_token_123"
        mock_credentials.token = "old_token"
        def refresh_and_mark_valid(_request):
            mock_credentials.valid = True
        mock_credentials.refresh = Mock(side_effect=refresh_and_mark_valid)
        
        mock_service = Mock()
        mock_service.users().getProfile().execute.return_value = {'emailAddress': 'test@example.com'}
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                with patch('src.auth.gmail_auth._test_token_usable') as mock_test:
                    with patch('src.auth.gmail_auth.build') as mock_build:
                        mock_exists.return_value = True
                        
                        mock_load.return_value = mock_credentials
                        # After refresh, token usability test succeeds
                        mock_test.return_value = True
                        mock_build.return_value = mock_service

                        result = get_gmail_service(
                            client_secrets_path="client_secrets.json",
                            token_path="token.json"
                        )

                        assert result == mock_service
                        mock_credentials.refresh.assert_called_once()
                        # For expired token path, usability is checked after refresh
                        assert mock_test.call_count == 1
    
    def test_get_gmail_service_with_expired_token_refresh_error(self):
        """Test getting Gmail service with expired token that fails to refresh."""
        mock_credentials = Mock(spec=Credentials)
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = None  # No refresh token
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            # client_secrets exists, token doesn't (will be loaded but invalid)
            mock_exists.return_value = True
            
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                with patch('src.auth.gmail_auth._test_token_usable') as mock_test:
                    mock_load.return_value = mock_credentials
                    mock_test.return_value = False
                    
                    # Should trigger new authentication flow
                    with patch('src.auth.gmail_auth.InstalledAppFlow') as mock_flow_class:
                        mock_flow_instance = Mock()
                        mock_flow_class.from_client_secrets_file.return_value = mock_flow_instance
                        mock_flow_instance.run_local_server.return_value = mock_credentials
                        
                        with patch('src.auth.gmail_auth.build') as mock_build:
                            mock_service = Mock()
                            mock_build.return_value = mock_service
                            
                            result = get_gmail_service(
                                client_secrets_path="client_secrets.json",
                                token_path="token.json"
                            )
                            
                            assert result == mock_service
                            mock_flow_class.from_client_secrets_file.assert_called_once_with(
                                "client_secrets.json",
                                SCOPES
                            )
    
    def test_get_gmail_service_new_authentication_oob_flow(self):
        """Test new authentication with OOB (Out-of-Band) flow."""
        mock_credentials = Mock()
        mock_credentials.valid = True
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            # client_secrets exists, token doesn't
            mock_exists.return_value = True
            
            # _load_credentials_from_token_file will return None for token.json
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                mock_load.return_value = None
                
                with patch('src.auth.gmail_auth.Flow') as mock_flow_class_oob:
                    mock_flow_instance = Mock()
                    mock_flow_class_oob.from_client_config.return_value = mock_flow_instance
                    mock_flow_instance.authorization_url.return_value = ('https://example.com/auth', None)
                    mock_flow_instance.credentials = mock_credentials

                    with patch('builtins.input', return_value='manual-auth-code'):
                        with patch('src.auth.gmail_auth._save_credentials_to_token_file'):
                            with patch('src.auth.gmail_auth.build') as mock_build:
                                mock_service = Mock()
                                mock_build.return_value = mock_service

                                result = get_gmail_service(
                                    client_secrets_path="client_secrets.json",
                                    token_path="token.json",
                                    oob_callback=True
                                )

                                assert result == mock_service
                                mock_flow_class_oob.from_client_config.assert_called_once()
                                mock_flow_instance.fetch_token.assert_called_once_with(
                                    authorization_response='manual-auth-code'
                                )
    
    def test_get_gmail_service_manual_token_flow(self):
        """Test authentication with manual token flow."""
        mock_credentials = Mock()
        mock_credentials.valid = True
        
        manual_token = {
            "token": "manual_token_123",
            "refresh_token": "manual_refresh_123",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "manual_client_123",
            "client_secret": "manual_secret_123",
            "scopes": SCOPES
        }
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            mock_exists.return_value = True  # client_secrets exists
            
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                mock_load.return_value = None  # No existing token
                
                with patch('src.auth.gmail_auth.Credentials.from_authorized_user_info') as mock_from_info:
                    mock_from_info.return_value = mock_credentials
                    
                    with patch('src.auth.gmail_auth._test_token_usable') as mock_test:
                        with patch('src.auth.gmail_auth.build') as mock_build:
                            mock_service = Mock()
                            mock_test.return_value = True
                            mock_build.return_value = mock_service
                            
                            result = get_gmail_service(
                                client_secrets_path="client_secrets.json",
                                token_path="token.json",
                                manual_token=manual_token
                            )
                            
                            assert result == mock_service
                            mock_from_info.assert_called_once_with(manual_token, SCOPES)
    
    def test_get_gmail_service_client_secrets_missing(self):
        """Test when client secrets file is missing."""
        with patch('src.auth.gmail_auth.os.path.exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="Client secrets file not found"):
                get_gmail_service(
                    client_secrets_path="/nonexistent/client_secrets.json",
                    token_path="token.json"
                )
    
    def test_get_gmail_service_custom_port(self):
        """Test authentication with custom port."""
        mock_credentials = Mock()
        mock_credentials.valid = True
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            # client_secrets exists, token doesn't
            mock_exists.return_value = True
            
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                mock_load.return_value = None
                
                with patch('src.auth.gmail_auth.InstalledAppFlow') as mock_flow_class:
                    mock_flow_instance = Mock()
                    mock_flow_class.from_client_secrets_file.return_value = mock_flow_instance
                    mock_flow_instance.run_local_server.return_value = mock_credentials
                    
                    with patch('src.auth.gmail_auth.build') as mock_build:
                        mock_service = Mock()
                        mock_build.return_value = mock_service
                        
                        result = get_gmail_service(
                            client_secrets_path="client_secrets.json",
                            token_path="token.json",
                            port=9999
                        )
                        
                        assert result == mock_service
                        # Check that port was passed to run_local_server
                        mock_flow_instance.run_local_server.assert_called_once()
                        call_kwargs = mock_flow_instance.run_local_server.call_args[1]
                        assert 'port' in call_kwargs
                        assert call_kwargs['port'] == 9999
    
    def test_get_gmail_service_token_save_failure(self):
        """Test when token save fails."""
        mock_credentials = Mock()
        mock_credentials.valid = True
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                mock_load.return_value = None
                
                with patch('src.auth.gmail_auth.InstalledAppFlow') as mock_flow_class:
                    mock_flow_instance = Mock()
                    mock_flow_class.from_client_secrets_file.return_value = mock_flow_instance
                    mock_flow_instance.run_local_server.return_value = mock_credentials
                    
                    with patch('src.auth.gmail_auth._save_credentials_to_token_file') as mock_save_token:
                        mock_save_token.side_effect = OSError("Failed to save token")
                        
                        with patch('src.auth.gmail_auth.build') as mock_build:
                            mock_service = Mock()
                            mock_build.return_value = mock_service
                            
                            # Should still return service even if token save fails
                            result = get_gmail_service(
                                client_secrets_path="client_secrets.json",
                                token_path="token.json"
                            )
                            
                            assert result == mock_service
                            mock_save_token.assert_called_once()
    
    def test_get_gmail_service_default_paths(self):
        """Test getting Gmail service with default paths."""
        mock_credentials = Mock()
        mock_credentials.valid = True
        
        with patch('src.auth.gmail_auth.os.path.exists') as mock_exists:
            mock_exists.return_value = True  # Both files exist
            
            with patch('src.auth.gmail_auth._load_credentials_from_token_file') as mock_load:
                with patch('src.auth.gmail_auth._test_token_usable') as mock_test:
                    with patch('src.auth.gmail_auth.build') as mock_build:
                        mock_load.return_value = mock_credentials
                        mock_test.return_value = True
                        mock_build.return_value = Mock()
                        
                        result = get_gmail_service()
                        
                        assert result is not None
                        # Should use default paths from config
                        mock_load.assert_called_once_with(DEFAULT_TOKEN_FILE)
    
    def test_get_gmail_service_retry_decorator(self):
        """Test that retry decorator is applied."""
        import src.auth.gmail_auth as gmail_auth_module
        
        # Check that get_gmail_service has retry decorator
        assert hasattr(gmail_auth_module.get_gmail_service, '__wrapped__')
        
    def test_scopes_constant(self):
        """Test SCOPES constant."""
        assert SCOPES == ['https://www.googleapis.com/auth/gmail.readonly']
        assert len(SCOPES) == 1
    
    def test_default_paths_imported(self):
        """Test that default paths are imported from config."""
        from src.config import OAUTH_CLIENT_SECRETS_PATH, OAUTH_TOKEN_PATH
        assert DEFAULT_CLIENT_SECRETS_FILE == OAUTH_CLIENT_SECRETS_PATH
        assert DEFAULT_TOKEN_FILE == OAUTH_TOKEN_PATH
