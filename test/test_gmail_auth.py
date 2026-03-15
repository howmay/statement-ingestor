"""
Unit tests for Gmail authentication module.
"""
import os
import pickle
from unittest.mock import Mock, patch, mock_open, MagicMock
import pytest
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

import sys
from functools import wraps

# No more sys.modules hack here

# Now import the module
from src.integrations.gmail.auth import (
    get_gmail_service,
    _test_token_usable,
    SCOPES,
    DEFAULT_CLIENT_SECRETS_FILE,
    DEFAULT_TOKEN_FILE
)


class TestGmailAuth:
    """Test suite for Gmail authentication functions."""
    
    @pytest.fixture(autouse=True)
    def mock_retry(self):
        """Mock the retry decorator for all tests in this class."""
        with patch('src.support.retry.retry_gmail', side_effect=lambda f: f):
            yield
            
    def test_test_token_usable_success(self):
        """Test token usability check with valid credentials."""
        # Create mock credentials
        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.expired = False

        # Mock the Gmail service build and API call
        with patch('src.integrations.gmail.auth.build') as mock_build:
            mock_service = Mock()
            mock_service.users().getProfile().execute.return_value = {'emailAddress': 'test@example.com'}
            mock_build.return_value = mock_service

            result = _test_token_usable(mock_creds)

            assert result is True
            mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)

    def test_test_token_usable_failure(self):
        """Test token usability check with invalid credentials."""
        mock_creds = Mock(spec=Credentials)

        with patch('src.integrations.gmail.auth.build') as mock_build:
            mock_build.side_effect = Exception("API Error")

            result = _test_token_usable(mock_creds)

            assert result is False

    @patch('src.integrations.gmail.auth.os.path.exists')
    @patch('src.integrations.gmail.auth.Credentials.from_authorized_user_file')
    @patch('src.integrations.gmail.auth._test_token_usable')
    @patch('src.integrations.gmail.auth.build')
    def test_get_gmail_service_with_valid_token(
        self, mock_build, mock_test_token, mock_creds_from_file, mock_exists
    ):
        """Test getting Gmail service with valid existing token."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock token loading - simulate JSON credentials
        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.refresh_token = "refresh_token"
        mock_creds_from_file.return_value = mock_creds

        # Mock token test - should return True so we don't re-auth
        mock_test_token.return_value = True

        # Mock service build
        mock_service = Mock()
        mock_service.status_code = 200
        mock_build.return_value = mock_service

        # Call the function
        result = get_gmail_service()

        assert result == mock_service
        mock_exists.assert_called()
        mock_creds_from_file.assert_called_once()
        mock_test_token.assert_called_once_with(mock_creds)

    @patch('src.integrations.gmail.auth.os.path.exists')
    @patch('src.integrations.gmail.auth.Credentials.from_authorized_user_file')
    @patch('src.integrations.gmail.auth._test_token_usable')
    @patch('src.integrations.gmail.auth.InstalledAppFlow')
    @patch('src.integrations.gmail.auth.build')
    def test_get_gmail_service_with_expired_token(
        self, mock_build, mock_flow_class, mock_test_token, mock_creds_from_file, mock_exists
    ):
        """Test getting Gmail service with expired but refreshable token."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock expired credentials
        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"
        mock_creds_from_file.return_value = mock_creds

        # Mock refresh - should be called
        mock_creds.refresh.return_value = None

        # Mock token test - after refresh, token should be usable
        mock_test_token.return_value = True

        # Mock service build
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Call the function
        result = get_gmail_service()

        assert result == mock_service
        mock_creds.refresh.assert_called_once()
        mock_test_token.assert_called_once_with(mock_creds)

    @patch('src.integrations.gmail.auth.os.path.exists')
    @patch('src.integrations.gmail.auth.pickle.load')
    @patch('src.integrations.gmail.auth._test_token_usable')
    @patch('src.integrations.gmail.auth.InstalledAppFlow')
    @patch('src.integrations.gmail.auth._save_credentials_to_token_file')
    @patch('src.integrations.gmail.auth.build')
    def test_get_gmail_service_new_authentication(
        self, mock_build, mock_save_token, mock_flow_class, mock_test_token,
        mock_pickle_load, mock_exists
    ):
        """Test getting Gmail service with new authentication (no token file)."""
        # Mock: client_secrets exists, but token.json does not
        def side_effect(path):
            if 'client_secrets.json' in path:
                return True
            if 'token.json' in path:
                return False
            return False
        mock_exists.side_effect = side_effect

        # Mock flow
        mock_flow = Mock()
        mock_flow_class.from_client_secrets_file.return_value = mock_flow

        # Mock credentials from flow
        mock_creds = Mock(spec=Credentials)
        mock_flow.run_local_server.return_value = mock_creds

        # Mock token test
        mock_test_token.return_value = True

        # Mock service build
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Call the function
        result = get_gmail_service()

        assert result == mock_service
        mock_flow_class.from_client_secrets_file.assert_called_once()
        mock_flow.run_local_server.assert_called_once()
        mock_save_token.assert_called_once_with(mock_creds, DEFAULT_TOKEN_FILE)
        # Note: _test_token_usable is NOT called for fresh OAuth credentials

    @patch('src.integrations.gmail.auth.os.path.exists')
    @patch('src.integrations.gmail.auth.Credentials.from_authorized_user_file')
    @patch('src.integrations.gmail.auth._test_token_usable')
    @patch('src.integrations.gmail.auth.InstalledAppFlow')
    @patch('src.integrations.gmail.auth._save_credentials_to_token_file')
    @patch('src.integrations.gmail.auth.build')
    def test_get_gmail_service_refresh_error(
        self, mock_build, mock_save_token, mock_flow_class, mock_test_token,
        mock_creds_from_file, mock_exists
    ):
        """Test getting Gmail service when token refresh fails."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock expired credentials with no refresh token
        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = None  # No refresh token
        mock_creds_from_file.return_value = mock_creds

        # Since no refresh token, it should jump to new auth flow
        # Mock new authentication flow
        mock_flow = Mock()
        mock_flow_class.from_client_secrets_file.return_value = mock_flow
        mock_new_creds = Mock(spec=Credentials)
        # Set valid=True so we skip refresh test
        mock_new_creds.valid = True
        mock_flow.run_local_server.return_value = mock_new_creds

        # Mock token test - for new credentials
        mock_test_token.return_value = True

        # Mock service build
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Call the function
        result = get_gmail_service()

        assert result == mock_service
        # Should have created new flow since refresh token was missing
        mock_flow_class.from_client_secrets_file.assert_called_once()

    def test_scopes_constant(self):
        """Test that SCOPES constant is correctly defined."""
        assert SCOPES == ['https://www.googleapis.com/auth/gmail.readonly']
        assert len(SCOPES) == 1
        assert 'https://www.googleapis.com/auth/gmail.readonly' in SCOPES

    @patch('builtins.open', new_callable=mock_open)
    @patch('src.integrations.gmail.auth.os.path.exists')
    @patch('src.integrations.gmail.auth.pickle.load')
    @patch('src.integrations.gmail.auth._test_token_usable')
    @patch('src.integrations.gmail.auth.build')
    def test_get_gmail_service_custom_paths(
        self, mock_build, mock_test_token, mock_pickle_load, mock_exists, mock_open_file
    ):
        """Test getting Gmail service with custom file paths."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock token loading
        mock_creds = Mock(spec=Credentials)
        mock_creds.valid = True
        mock_creds.expired = False
        mock_pickle_load.return_value = mock_creds

        # Mock token test
        mock_test_token.return_value = True

        # Mock service build
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Custom paths
        custom_client_secrets = '/custom/path/client_secrets.json'
        custom_token = '/custom/path/token.pickle'
        custom_port = 8080

        # Call the function with custom paths
        result = get_gmail_service(
            client_secrets_path=custom_client_secrets,
            token_path=custom_token,
            port=custom_port
        )

        assert result == mock_service
        # Note: The function uses the paths but we can't easily assert internal calls
        # without more invasive mocking. This test at least ensures the function
        # accepts custom parameters without error.
