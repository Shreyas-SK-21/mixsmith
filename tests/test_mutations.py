"""Tests for safe playlist mutation safeguards and external drift detection."""

from unittest.mock import MagicMock, patch

import pytest

from mixsmith.connectors.spotify import SpotifyConnector
from mixsmith.core.exceptions import SnapshotDriftError
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


def test_validate_and_normalize_track_uri(mock_connector):
    """Verifies that URI validation accepts URIs, bare IDs, URLs, and rejects garbage."""
    # Standard URI
    assert mock_connector.validate_and_normalize_track_uri("spotify:track:4cOdK2wGLETKBW3PvgPWqT") == "spotify:track:4cOdK2wGLETKBW3PvgPWqT"

    # Bare ID
    assert mock_connector.validate_and_normalize_track_uri("4cOdK2wGLETKBW3PvgPWqT") == "spotify:track:4cOdK2wGLETKBW3PvgPWqT"

    # Open Spotify URL
    url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc"
    assert mock_connector.validate_and_normalize_track_uri(url) == "spotify:track:4cOdK2wGLETKBW3PvgPWqT"

    # Invalid string
    assert mock_connector.validate_and_normalize_track_uri("invalid_uri_string") is None
    assert mock_connector.validate_and_normalize_track_uri("") is None


def test_mutation_dry_run(mock_connector):
    """Verifies dry-run returns projected results without making modification calls."""
    with patch.object(mock_connector, "get_playlist_snapshot") as mock_snap:
        mock_snap.return_value = {
            "id": "p123",
            "name": "My Mix",
            "snapshot_id": "snap_v1",
            "total_tracks": 10,
            "owner_id": "user1"
        }
        with patch.object(mock_connector, "api_request") as mock_req:
            res = mock_connector.mutate_playlist_tracks(
                identifier="p123",
                track_uris=["4cOdK2wGLETKBW3PvgPWqT", "invalid"],
                dry_run=True,
                replace=False
            )

            assert res.dry_run is True
            assert res.tracks_added == 1
            assert len(res.invalid_uris) == 1
            assert res.initial_track_count == 10
            assert res.final_track_count == 11
            assert res.batches_executed == 0
            # api_request should not have made POST or PUT calls
            mock_req.assert_not_called()


def test_mutation_snapshot_drift_detection(mock_connector):
    """Verifies SnapshotDriftError is raised when expected snapshot ID doesn't match current state."""
    with patch.object(mock_connector, "get_playlist_snapshot") as mock_snap:
        mock_snap.return_value = {
            "id": "p123",
            "name": "My Mix",
            "snapshot_id": "snap_v2",  # Changed externally!
            "total_tracks": 12,
            "owner_id": "user1"
        }

        with pytest.raises(SnapshotDriftError, match="snapshot drift detected"):
            mock_connector.mutate_playlist_tracks(
                identifier="p123",
                track_uris=["4cOdK2wGLETKBW3PvgPWqT"],
                expected_snapshot_id="snap_v1",  # Expected older snapshot
                strict_drift=True
            )


def test_mutation_successful_batch_execution(mock_connector):
    """Verifies tracks are sent in chunks and post-state verification completes."""
    with patch.object(mock_connector, "get_playlist_snapshot") as mock_snap:
        mock_snap.side_effect = [
            {"id": "p123", "name": "Mix", "snapshot_id": "snap_v1", "total_tracks": 0, "owner_id": "u1"},
            {"id": "p123", "name": "Mix", "snapshot_id": "snap_v2", "total_tracks": 2, "owner_id": "u1"}
        ]
        with patch.object(mock_connector, "api_request") as mock_req:
            mock_req.return_value = {"snapshot_id": "snap_v2"}

            res = mock_connector.mutate_playlist_tracks(
                identifier="p123",
                track_uris=["4cOdK2wGLETKBW3PvgPWqT", "3n3Ppam7vgaVa1iaRUc9Lp"],
                replace=True
            )

            assert res.tracks_added == 2
            assert res.final_track_count == 2
            assert res.batches_executed == 1
            assert res.initial_snapshot_id == "snap_v1"
            assert res.final_snapshot_id == "snap_v2"
