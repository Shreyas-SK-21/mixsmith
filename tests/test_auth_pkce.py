"""Tests for OAuth2 PKCE code exchange and CSRF state validation."""

import base64
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from mixsmith.auth.manager import OAuthManager
from mixsmith.core.exceptions import AuthorizationDeniedError
from mixsmith.utils.config import AppConfig


@pytest.fixture
def auth_mgr():
    config = AppConfig(
        client_id="mock_client_id",
        client_secret="mock_client_secret",
        redirect_uri="http://127.0.0.1:8888/callback"
    )
    return OAuthManager(config=config)


def test_pkce_generation_rfc7636_compliance(auth_mgr):
    """PKCE pair must satisfy RFC 7636 (verifier length >= 43, challenge = base64url(sha256(verifier)))."""
    verifier, challenge = auth_mgr.generate_pkce_pair()

    assert len(verifier) >= 43
    assert len(verifier) <= 128
    # Verifier must use unreserved URL-safe characters
    assert all(c.isalnum() or c in "-._~" for c in verifier)

    # Recompute challenge
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    assert challenge == expected_challenge


def test_auth_url_contains_pkce_and_state(auth_mgr):
    """Authorization URL must contain code_challenge, code_challenge_method=S256, and state."""
    state = auth_mgr.generate_state()
    verifier, challenge = auth_mgr.generate_pkce_pair()

    url = auth_mgr.get_auth_url(state=state, code_challenge=challenge)

    assert "code_challenge=" in url
    assert f"code_challenge={challenge}" in url
    assert "code_challenge_method=S256" in url
    assert f"state={state}" in url
    assert "client_id=mock_client_id" in url


def test_state_mismatch_raises_authorization_denied(auth_mgr):
    """Callback with mismatched state parameter must be rejected as possible CSRF."""
    with patch("webbrowser.open"):
        with patch("socketserver.TCPServer") as mock_server_cls:
            mock_server = MagicMock()
            def fake_handle():
                from mixsmith.auth.manager import _AuthCallbackHandler
                _AuthCallbackHandler.auth_code = "valid_code_123"
                _AuthCallbackHandler.received_state = "tampered_or_fake_state"
            mock_server.handle_request.side_effect = fake_handle
            mock_server_cls.return_value.__enter__.return_value = mock_server

            with pytest.raises(AuthorizationDeniedError, match="OAuth state mismatch"):
                auth_mgr.authorize_interactive()


def test_exchange_code_sends_code_verifier(auth_mgr):
    """Token exchange must send code_verifier in payload."""
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_new_access_token",
            "refresh_token": "mock_new_refresh_token"
        }
        mock_post.return_value = mock_resp

        token = auth_mgr.exchange_code_for_token(
            code="test_code",
            code_verifier="test_verifier_value"
        )

        assert token == "mock_new_access_token"
        called_args, called_kwargs = mock_post.call_args
        sent_data = called_kwargs.get("data", {})
        assert sent_data.get("code_verifier") == "test_verifier_value"
        assert sent_data.get("grant_type") == "authorization_code"
