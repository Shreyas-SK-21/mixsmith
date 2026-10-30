"""Unit tests for Spotify API error handling with mocked network calls."""

from unittest.mock import MagicMock, patch
import pytest
from mixsmith.connectors.spotify import SpotifyConnector
from mixsmith.core.exceptions import APIError, ResourceNotFoundError
from mixsmith.utils.config import AppConfig


@pytest.fixture
def mock_connector():
    config = AppConfig(
        client_id="mock_id",
        client_secret="mock_secret",
        access_token="mock_access_token",
        refresh_token="mock_refresh_token"
    )
    auth = MagicMock()
    auth.get_valid_token.return_value = "mock_token"
    return SpotifyConnector(config=config, auth_manager=auth)


def test_api_request_success(mock_connector):
    """Tests successful JSON API response."""
    with patch("requests.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "mock_user", "display_name": "Test User"}
        mock_resp.text = '{"id": "mock_user"}'
        mock_req.return_value = mock_resp

        res = mock_connector.api_request("GET", "me")
        assert res["id"] == "mock_user"


def test_api_request_404_raises_resource_not_found(mock_connector):
    """Tests that HTTP 404 raises ResourceNotFoundError."""
    with patch("requests.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_req.return_value = mock_resp

        with pytest.raises(ResourceNotFoundError):
            mock_connector.api_request("GET", "playlists/nonexistent_123")


def test_api_request_401_triggers_token_refresh(mock_connector):
    """Tests that HTTP 401 attempts token refresh."""
    with patch("requests.request") as mock_req:
        # First call returns 401, second call returns 200
        resp_401 = MagicMock(status_code=401, text="Unauthorized")
        resp_200 = MagicMock(status_code=200, text='{"success": true}')
        resp_200.json.return_value = {"success": True}

        mock_req.side_effect = [resp_401, resp_200]
        mock_connector.auth.refresh_access_token.return_value = "new_token"

        res = mock_connector.api_request("GET", "me")
        assert res["success"] is True
        mock_connector.auth.refresh_access_token.assert_called_once()
