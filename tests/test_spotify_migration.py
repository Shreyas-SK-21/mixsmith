"""Unit and integration tests for Spotify February 2026 Web API schema migration and mutation safety."""

from unittest.mock import MagicMock, patch
import pytest

from mixsmith.connectors.spotify import SpotifyConnector
from mixsmith.core.exceptions import (
    APIError,
    PartialMutationError,
    ResourceNotFoundError,
)
from mixsmith.utils.config import AppConfig


@pytest.fixture
def mock_config():
    return AppConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        access_token="test_access_token",
        refresh_token="test_refresh_token"
    )


@pytest.fixture
def connector(mock_config):
    auth_mock = MagicMock()
    auth_mock.get_valid_token.return_value = "valid_token"
    return SpotifyConnector(config=mock_config, auth_manager=auth_mock)


def test_2026_playlist_schema_items_and_item(connector):
    """Verifies parsing of Spotify February 2026 schema using playlist.items.items[].item."""
    mock_payload = {
        "id": "p123",
        "name": "2026 Modern Hits",
        "description": "Modern API response",
        "owner": {"display_name": "Curator"},
        "external_urls": {"spotify": "https://open.spotify.com/playlist/p123"},
        "items": {
            "total": 2,
            "next": None,
            "items": [
                {
                    "added_at": "2026-03-01T12:00:00Z",
                    "added_by": {"id": "user1"},
                    "item": {
                        "id": "t1",
                        "uri": "spotify:track:t1",
                        "name": "First Track",
                        "artists": [{"id": "a1", "name": "Artist One"}],
                        "album": {"name": "Album One", "release_date": "2024-05-01", "album_type": "album"},
                        "duration_ms": 180000,
                        "popularity": None,  # Removed in 2026 Dev Mode!
                        "explicit": False,
                        "external_ids": {"isrc": "USRC12400001"}
                    }
                },
                {
                    "added_at": "2026-03-01T12:01:00Z",
                    "added_by": {"id": "user1"},
                    "item": {
                        "id": "t2",
                        "uri": "spotify:track:t2",
                        "name": "Second Track",
                        "artists": [{"id": "a2", "name": "Artist Two"}],
                        "album": {"name": "Album Two", "release_date": "2023-10-15", "album_type": "album"},
                        "duration_ms": 210000,
                        "popularity": None,
                        "explicit": True,
                        "external_ids": {"isrc": "GBAYE2300002"}
                    }
                }
            ]
        }
    }

    with patch.object(connector, "api_request", return_value=mock_payload):
        with patch.object(connector, "get_artists_data", return_value={}):
            playlist = connector.get_playlist("p123")

    assert playlist.id == "p123"
    assert playlist.total_tracks == 2
    assert len(playlist.tracks) == 2
    assert playlist.tracks[0].name == "First Track"
    assert playlist.tracks[0].popularity is None  # Accurately preserved as None, not 0
    assert playlist.tracks[1].name == "Second Track"
    assert playlist.tracks[1].explicit is True


def test_legacy_playlist_schema_tracks_and_track_compatibility(connector):
    """Verifies backward compatibility with pre-2026 playlist responses (tracks.items[].track)."""
    mock_payload = {
        "id": "p_legacy",
        "name": "Classic Playlist",
        "tracks": {
            "total": 1,
            "next": None,
            "items": [
                {
                    "added_at": "2021-01-01T00:00:00Z",
                    "track": {
                        "id": "t_leg",
                        "uri": "spotify:track:t_leg",
                        "name": "Classic Song",
                        "artists": [{"id": "a_leg", "name": "Old School"}],
                        "album": {"name": "Old Album", "release_date": "1995-04-12"},
                        "duration_ms": 240000,
                        "popularity": 72,
                        "explicit": False,
                        "external_ids": {"isrc": "USLEG9500001"}
                    }
                }
            ]
        }
    }

    with patch.object(connector, "api_request", return_value=mock_payload):
        with patch.object(connector, "get_artists_data", return_value={}):
            playlist = connector.get_playlist("p_legacy")

    assert len(playlist.tracks) == 1
    assert playlist.tracks[0].id == "t_leg"
    assert playlist.tracks[0].popularity == 72
    assert playlist.tracks[0].decade == "90s"


def test_null_and_podcast_items_filtered(connector):
    """Verifies that null items, podcasts, episodes, or tracks without IDs are cleanly excluded."""
    mock_payload = {
        "id": "p_mixed",
        "items": {
            "total": 3,
            "next": None,
            "items": [
                None,  # Null entry
                {"item": None},  # Unavailable / restricted track
                {
                    "item": {
                        "type": "episode",  # Podcast episode (no track id)
                        "name": "Daily News Podcast"
                    }
                },
                {
                    "item": {
                        "id": "valid_1",
                        "name": "Real Song",
                        "artists": [{"name": "Singer"}],
                        "album": {"release_date": "2020"},
                        "duration_ms": 150000
                    }
                }
            ]
        }
    }

    with patch.object(connector, "api_request", return_value=mock_payload):
        with patch.object(connector, "get_artists_data", return_value={}):
            playlist = connector.get_playlist("p_mixed")

    assert len(playlist.tracks) == 1
    assert playlist.tracks[0].id == "valid_1"


def test_bulk_artists_removal_graceful_fallback(connector):
    """Verifies that removal of GET /artists?ids=... in 2026 Dev Mode does not crash get_artists_data."""
    def mock_api(method, endpoint, **kwargs):
        if "artists?ids=" in endpoint:
            raise ResourceNotFoundError("Endpoint removed in Development Mode (HTTP 404)")
        if endpoint == "artists/art_1":
            return {"id": "art_1", "name": "Solo Artist", "genres": ["indie rock"], "popularity": None}
        return {}

    with patch.object(connector, "api_request", side_effect=mock_api):
        res = connector.get_artists_data(["art_1", "art_2"])

    assert "art_1" in res
    assert res["art_1"]["genres"] == ["indie rock"]
    assert res["art_1"]["popularity"] is None


def test_partial_mutation_failure_reporting(connector):
    """Verifies that a failure during sequential API batches raises PartialMutationError with state details."""
    snapshot_data = {
        "id": "p_target",
        "name": "Target Playlist",
        "snapshot_id": "snap_initial",
        "items": {"total": 10}
    }

    call_count = 0

    def mock_api(method, endpoint, **kwargs):
        nonlocal call_count
        call_count += 1
        if "playlists/p_target?fields=" in endpoint:
            return snapshot_data
        if method == "PUT" and "playlists/p_target/items" in endpoint:
            return {"snapshot_id": "snap_after_batch_1"}
        if method == "POST" and "playlists/p_target/items" in endpoint:
            raise APIError("Spotify API Error HTTP 500: Internal server error", status_code=500)
        return {}

    # 150 tracks = 2 batches (100 + 50)
    fake_uris = [f"spotify:track:{i:022d}" for i in range(150)]

    with patch.object(connector, "api_request", side_effect=mock_api):
        with pytest.raises(PartialMutationError) as exc_info:
            connector.mutate_playlist_tracks("p_target", fake_uris, replace=True)

    err = exc_info.value
    assert err.playlist_id == "p_target"
    assert err.batches_completed == 1
    assert err.tracks_added == 100
    assert err.details["mutation_result"].is_partial is True


def test_post_mutation_verification_check(connector):
    """Verifies that successful mutation performs sequence verification against resulting tracks."""
    snapshot_data = {
        "id": "p_verify",
        "snapshot_id": "snap_done",
        "items": {"total": 2}
    }

    track_uris = ["spotify:track:0000000000000000000001", "spotify:track:0000000000000000000002"]

    def mock_api(method, endpoint, **kwargs):
        if "playlists/p_verify?fields=" in endpoint:
            return snapshot_data
        if method == "PUT" and "playlists/p_verify/items" in endpoint:
            return {"snapshot_id": "snap_done"}
        if "playlists/p_verify/items?limit=100" in endpoint:
            return {
                "items": [
                    {"item": {"uri": track_uris[0]}},
                    {"item": {"uri": track_uris[1]}}
                ],
                "next": None
            }
        return {}

    with patch.object(connector, "api_request", side_effect=mock_api):
        res = connector.mutate_playlist_tracks("p_verify", track_uris, replace=True)

    assert res.verified_tracks_match is True
    assert res.is_partial is False
    assert res.resulting_track_uris == track_uris
