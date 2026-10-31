"""Spotify API connector: authentication, track enrichment, and playlist operations."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from mixsmith.auth.manager import OAuthManager
from mixsmith.connectors.base import MusicConnectorBase
from mixsmith.core.exceptions import (
    APIError,
    AuthError,
    PartialMutationError,
    RateLimitExceededError,
    ResourceNotFoundError,
    SnapshotDriftError,
)
from mixsmith.core.models import Playlist, Track
from mixsmith.utils.config import AppConfig
from mixsmith.utils.logging import get_logger
from mixsmith.utils.metadata import (
    infer_era_and_decade,
    infer_language_and_region,
    infer_primary_genre,
    infer_theme,
)

logger = get_logger("mixsmith.spotify")

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


@dataclass
class PlaylistMutationResult:
    """Outcome of a safe playlist mutation operation."""
    playlist_id: str
    initial_snapshot_id: str
    final_snapshot_id: str
    initial_track_count: int
    final_track_count: int
    tracks_added: int
    invalid_uris: list[str] = field(default_factory=list)
    batches_executed: int = 0
    total_batches: int = 0
    drift_detected: bool = False
    dry_run: bool = False
    verified_tracks_match: bool = False
    error: str | None = None
    is_partial: bool = False
    resulting_track_uris: list[str] = field(default_factory=list)


class SpotifyConnector(MusicConnectorBase):
    """Production-grade Spotify Web API Connector."""

    def __init__(self, config: AppConfig | None = None, auth_manager: OAuthManager | None = None):
        self.config = config or AppConfig.load()
        self.auth = auth_manager or OAuthManager(self.config)

    def validate_and_normalize_track_uri(self, uri_or_id: str) -> str | None:
        """
        Validates and standardizes a track identifier into a spotify:track:URI.
        Returns None if identifier is malformed.
        """
        if not uri_or_id or not isinstance(uri_or_id, str):
            return None
        cleaned = uri_or_id.strip()

        # spotify:track:22chars
        if re.match(r"^spotify:track:[a-zA-Z0-9]{22}$", cleaned):
            return cleaned

        # 22 alphanumeric chars (bare ID)
        if re.match(r"^[a-zA-Z0-9]{22}$", cleaned):
            return f"spotify:track:{cleaned}"

        # open.spotify.com/track/22chars
        url_match = re.search(r"open\.spotify\.com/track/([a-zA-Z0-9]{22})", cleaned)
        if url_match:
            return f"spotify:track:{url_match.group(1)}"

        return None

    def get_playlist_snapshot(self, identifier: str) -> dict[str, Any]:
        """Fetches lightweight target playlist metadata for mutation safety checks."""
        p_id = self.extract_playlist_id(identifier)
        data = self.api_request("GET", f"playlists/{p_id}?fields=id,name,snapshot_id,items.total,tracks.total,owner.id")

        # In Spotify February 2026 API, 'items.total' is primary, 'tracks.total' is legacy fallback
        total_tracks = 0
        if "items" in data and isinstance(data["items"], dict):
            total_tracks = data["items"].get("total", 0)
        elif "tracks" in data and isinstance(data["tracks"], dict):
            total_tracks = data["tracks"].get("total", 0)

        return {
            "id": data.get("id", p_id),
            "name": data.get("name", ""),
            "snapshot_id": data.get("snapshot_id", ""),
            "total_tracks": total_tracks,
            "owner_id": (data.get("owner") or {}).get("id", "")
        }

    def get_all_playlist_track_uris(self, identifier: str) -> list[str]:
        """Fetches all track URIs in a playlist in order using the current items endpoint."""
        p_id = self.extract_playlist_id(identifier)
        uris: list[str] = []
        url = f"playlists/{p_id}/items?limit=100"

        while url:
            data = self.api_request("GET", url)
            for it in data.get("items", []):
                tr = it.get("item") if (it and "item" in it) else (it.get("track") if it else None)
                if tr and isinstance(tr, dict):
                    uri = tr.get("uri") or (f"spotify:track:{tr['id']}" if tr.get("id") else "")
                    if uri:
                        uris.append(uri)
            url = data.get("next")

        return uris

    def mutate_playlist_tracks(
        self,
        identifier: str,
        track_uris: list[str],
        expected_snapshot_id: str | None = None,
        dry_run: bool = False,
        replace: bool = False,
        strict_drift: bool = True
    ) -> PlaylistMutationResult:
        """
        Safely applies track mutations to an existing Spotify playlist.

        Performs pre-mutation state inspection, external drift detection, URI validation,
        batched requests, explicit partial failure reporting, and post-mutation state verification.
        """
        p_id = self.extract_playlist_id(identifier)

        # 1. Pre-mutation state inspection
        snapshot = self.get_playlist_snapshot(p_id)
        current_snapshot_id = snapshot["snapshot_id"]
        initial_track_count = snapshot["total_tracks"]

        # Drift detection
        drift_detected = False
        if expected_snapshot_id and expected_snapshot_id != current_snapshot_id:
            drift_detected = True
            msg = (
                f"Playlist {p_id} snapshot drift detected: expected '{expected_snapshot_id}' "
                f"but found '{current_snapshot_id}'. Playlist was modified externally."
            )
            if strict_drift:
                logger.error(msg)
                raise SnapshotDriftError(msg)
            else:
                logger.warning(msg)

        # 2. URI Validation
        valid_uris: list[str] = []
        invalid_uris: list[str] = []
        for raw_uri in track_uris:
            normalized = self.validate_and_normalize_track_uri(raw_uri)
            if normalized:
                valid_uris.append(normalized)
            else:
                invalid_uris.append(raw_uri)

        if invalid_uris:
            logger.warning(f"Ignored {len(invalid_uris)} invalid track URIs during playlist mutation.")

        chunk_size = 100
        total_batches = (len(valid_uris) + chunk_size - 1) // chunk_size if valid_uris else (1 if replace else 0)

        # 3. Dry-Run early exit
        if dry_run:
            projected_count = len(valid_uris) if replace else initial_track_count + len(valid_uris)
            return PlaylistMutationResult(
                playlist_id=p_id,
                initial_snapshot_id=current_snapshot_id,
                final_snapshot_id=current_snapshot_id,
                initial_track_count=initial_track_count,
                final_track_count=projected_count,
                tracks_added=len(valid_uris),
                invalid_uris=invalid_uris,
                batches_executed=0,
                total_batches=total_batches,
                drift_detected=drift_detected,
                dry_run=True,
                verified_tracks_match=True,
                is_partial=False
            )

        # 4. Batched mutation execution (Non-atomic sequential batches)
        batches_completed = 0
        tracks_added_count = 0
        latest_snapshot = current_snapshot_id

        try:
            if replace:
                # First batch replaces all items; subsequent batches append
                first_chunk = valid_uris[:chunk_size] if valid_uris else []
                res = self.api_request("PUT", f"playlists/{p_id}/items", json_data={"uris": first_chunk})
                if "snapshot_id" in res:
                    latest_snapshot = res["snapshot_id"]
                batches_completed += 1
                tracks_added_count += len(first_chunk)

                for i in range(chunk_size, len(valid_uris), chunk_size):
                    chunk = valid_uris[i:i + chunk_size]
                    res = self.api_request("POST", f"playlists/{p_id}/items", json_data={"uris": chunk})
                    if "snapshot_id" in res:
                        latest_snapshot = res["snapshot_id"]
                    batches_completed += 1
                    tracks_added_count += len(chunk)
            else:
                for i in range(0, len(valid_uris), chunk_size):
                    chunk = valid_uris[i:i + chunk_size]
                    res = self.api_request("POST", f"playlists/{p_id}/items", json_data={"uris": chunk})
                    if "snapshot_id" in res:
                        latest_snapshot = res["snapshot_id"]
                    batches_completed += 1
                    tracks_added_count += len(chunk)
        except Exception as e:
            # Report partial failure explicitly: user is NEVER told a partial operation succeeded
            partial_res = PlaylistMutationResult(
                playlist_id=p_id,
                initial_snapshot_id=current_snapshot_id,
                final_snapshot_id=latest_snapshot,
                initial_track_count=initial_track_count,
                final_track_count=initial_track_count + tracks_added_count if not replace else tracks_added_count,
                tracks_added=tracks_added_count,
                invalid_uris=invalid_uris,
                batches_executed=batches_completed,
                total_batches=total_batches,
                drift_detected=drift_detected,
                dry_run=False,
                verified_tracks_match=False,
                error=str(e),
                is_partial=True
            )
            msg = (
                f"Playlist mutation failed mid-execution at batch {batches_completed + 1}/{total_batches}. "
                f"Playlist {p_id} was partially updated ({tracks_added_count}/{len(valid_uris)} tracks added). Error: {e}"
            )
            logger.error(msg)
            raise PartialMutationError(
                msg,
                playlist_id=p_id,
                batches_completed=batches_completed,
                tracks_added=tracks_added_count,
                details={"mutation_result": partial_res}
            ) from e

        # 5. Post-mutation state verification
        post_snapshot = self.get_playlist_snapshot(p_id)
        final_count = post_snapshot["total_tracks"]
        final_snapshot_id = post_snapshot.get("snapshot_id", latest_snapshot)

        # Retrieve resulting track URIs to verify complete sequence
        resulting_uris = self.get_all_playlist_track_uris(p_id)
        if replace:
            verified_match = (resulting_uris == valid_uris)
        else:
            verified_match = (len(resulting_uris) == initial_track_count + len(valid_uris))

        return PlaylistMutationResult(
            playlist_id=p_id,
            initial_snapshot_id=current_snapshot_id,
            final_snapshot_id=final_snapshot_id,
            initial_track_count=initial_track_count,
            final_track_count=final_count,
            tracks_added=len(valid_uris),
            invalid_uris=invalid_uris,
            batches_executed=batches_completed,
            total_batches=total_batches,
            drift_detected=drift_detected,
            dry_run=False,
            verified_tracks_match=verified_match,
            resulting_track_uris=resulting_uris
        )

    def api_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
        max_retries: int = 3
    ) -> Any:
        """Makes an authenticated request to the Spotify Web API with rate-limit and token refresh handling."""
        url = endpoint if endpoint.startswith("http") else f"{SPOTIFY_API_BASE}/{endpoint.lstrip('/')}"

        for attempt in range(max_retries):
            token = self.auth.get_valid_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            try:
                resp = requests.request(
                    method, url, headers=headers, params=params, json=json_data, timeout=20
                )
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise APIError(f"Network error communicating with Spotify: {e}")
                time.sleep(1.0)
                continue

            # Handle rate limiting
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                logger.warning(f"Rate limited by Spotify API. Waiting {retry_after}s before retry...")
                time.sleep(retry_after)
                continue

            # Handle expired token
            if resp.status_code == 401:
                logger.info("Access token expired. Refreshing token...")
                if self.auth.refresh_access_token():
                    continue
                else:
                    raise AuthError("Spotify authentication failed (HTTP 401). Please re-login.")

            if resp.status_code == 404:
                raise ResourceNotFoundError(f"Spotify resource not found ({url})")

            if resp.status_code >= 400:
                raise APIError(
                    f"Spotify API Error HTTP {resp.status_code} ({url}): {resp.text}",
                    status_code=resp.status_code,
                    response_text=resp.text
                )

            if resp.status_code == 204 or not resp.text:
                return {}

            return resp.json()

        raise RateLimitExceededError(f"Request failed after {max_retries} retries: {url}")

    def get_me(self) -> dict[str, Any]:
        """Gets current authenticated user's profile."""
        return self.api_request("GET", "me")

    def list_playlists(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lists user's playlists."""
        playlists: list[dict[str, Any]] = []
        url = f"me/playlists?limit={min(limit, 50)}"

        while url and len(playlists) < limit:
            data = self.api_request("GET", url)
            for item in data.get("items", []):
                if item:
                    playlists.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "description": item.get("description", ""),
                        "public": item.get("public", False),
                        "total_tracks": (item.get("tracks") or item.get("items") or {}).get("total", 0),
                        "url": item.get("external_urls", {}).get("spotify", "")
                    })
                    if len(playlists) >= limit:
                        break
            url = data.get("next")

        return playlists

    @staticmethod
    def extract_playlist_id(identifier: str) -> str:
        """Extracts Spotify playlist ID from URL, URI, or raw string."""
        s = identifier.strip()
        if "spotify.com/playlist/" in s:
            match = re.search(r"playlist/([a-zA-Z0-9]+)", s)
            if match:
                return match.group(1)
        if s.startswith("spotify:playlist:"):
            return s.split(":")[-1]
        return s

    def get_artists_data(self, artist_ids: list[str]) -> dict[str, dict[str, Any]]:
        """
        Batch fetches artist metadata (genres).
        Gracefully handles the February 2026 removal of bulk GET /artists?ids=...
        in Spotify Development Mode applications, falling back to individual queries
        or returning partial data without crashing.
        """
        artists_map: dict[str, dict[str, Any]] = {}
        unique_ids = [aid for aid in dict.fromkeys(artist_ids) if aid]
        if not unique_ids:
            return artists_map

        # Try bulk query first (supported if application has extended access)
        chunk_size = 50
        bulk_failed = False
        for i in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[i:i + chunk_size]
            try:
                res = self.api_request("GET", f"artists?ids={','.join(chunk)}")
                for art in res.get("artists", []):
                    if art and art.get("id"):
                        artists_map[art["id"]] = {
                            "name": art.get("name"),
                            "genres": art.get("genres", []),
                            "popularity": art.get("popularity")
                        }
            except (APIError, ResourceNotFoundError) as e:
                logger.info(f"Bulk artists endpoint unavailable ({e}). Falling back to safe single queries or local metadata.")
                bulk_failed = True
                break
            except Exception as e:
                logger.warning(f"Error fetching artist chunk: {e}")
                bulk_failed = True
                break

        if bulk_failed:
            # In Development Mode, bulk endpoint is removed. Limit single queries to top primary artists to avoid 429
            for aid in unique_ids[:20]:
                if aid in artists_map:
                    continue
                try:
                    art = self.api_request("GET", f"artists/{aid}")
                    if art and art.get("id"):
                        artists_map[art["id"]] = {
                            "name": art.get("name"),
                            "genres": art.get("genres", []),
                            "popularity": art.get("popularity")
                        }
                except Exception:
                    # If single query fails or is rate limited, gracefully stop querying and rely on local metadata
                    break

        return artists_map

    def get_playlist(self, identifier: str) -> Playlist:
        """Fetches full playlist metadata and enriches all tracks with human dimensions."""
        is_liked = identifier.strip().lower() in ("liked", "liked-songs", "saved", "me/tracks", "liked songs")
        raw_items: list[tuple[dict[str, Any], dict[str, Any]]] = []

        url: str | None = None
        if is_liked:
            playlist_name = "Liked Songs"
            playlist_id = "liked-songs"
            playlist_desc = "User saved/liked songs"
            playlist_url = "https://open.spotify.com/collection/tracks"
            owner_name = "Me"

            url = "me/tracks?limit=50"
            logger.info("Fetching Liked Songs library...")
            while url:
                data = self.api_request("GET", url)
                for it in data.get("items", []):
                    # Handle both 2026 'item' and legacy 'track'
                    tr = it.get("item") if (it and "item" in it) else (it.get("track") if it else None)
                    if tr and isinstance(tr, dict) and tr.get("id"):
                        raw_items.append((it, tr))
                url = data.get("next")
        else:
            p_id = self.extract_playlist_id(identifier)
            data = self.api_request("GET", f"playlists/{p_id}")
            playlist_id = data.get("id", p_id)
            playlist_name = data.get("name", "Untitled Playlist")
            playlist_desc = data.get("description", "")
            playlist_url = data.get("external_urls", {}).get("spotify", "")
            owner_name = (data.get("owner") or {}).get("display_name", "Unknown")

            # In Spotify February 2026 API: 'items' paging object with 'item' track entity
            items_obj = data.get("items") or data.get("tracks") or {}
            for it in items_obj.get("items", []):
                tr = it.get("item") if (it and "item" in it) else (it.get("track") if it else None)
                if tr and isinstance(tr, dict) and tr.get("id"):
                    raw_items.append((it, tr))

            url = items_obj.get("next")
            while url:
                page_data = self.api_request("GET", url)
                for it in page_data.get("items", []):
                    tr = it.get("item") if (it and "item" in it) else (it.get("track") if it else None)
                    if tr and isinstance(tr, dict) and tr.get("id"):
                        raw_items.append((it, tr))
                url = page_data.get("next")

        # Extract all artist IDs for batch enrichment
        all_artist_ids: list[str] = []
        for it, tr in raw_items:
            for art in tr.get("artists", []):
                if art.get("id"):
                    all_artist_ids.append(art["id"])

        artists_info = self.get_artists_data(all_artist_ids)

        # Build enriched Track models with confidence-aware provenance
        enriched_tracks: list[Track] = []
        for it, tr in raw_items:
            tr_artists = [a.get("name", "Unknown") for a in tr.get("artists", [])]
            primary_artist = tr_artists[0] if tr_artists else "Unknown"

            combined_genres: list[str] = []
            for art in tr.get("artists", []):
                aid = art.get("id")
                if aid and aid in artists_info:
                    combined_genres.extend(artists_info[aid].get("genres", []))
            combined_genres = list(dict.fromkeys(combined_genres))

            album_obj = tr.get("album", {})
            rel_date = album_obj.get("release_date", "")
            dur_ms = tr.get("duration_ms", 0)
            pop = tr.get("popularity")  # Can be None in Spotify 2026 Dev Mode!
            isrc = tr.get("external_ids", {}).get("isrc", "")

            # Confidence-aware metadata inference
            era_res, decade_res, rel_year = infer_era_and_decade(rel_date)
            genre_res = infer_primary_genre(combined_genres)
            theme_res = infer_theme(tr.get("name", ""), combined_genres, genre_res.value, rel_year, pop, dur_ms)
            lang_res = infer_language_and_region(isrc, combined_genres, tr.get("name", ""), tr_artists)

            track_model = Track(
                id=tr["id"],
                uri=tr.get("uri", f"spotify:track:{tr['id']}"),
                name=tr.get("name", "Unknown Track"),
                artists=tr_artists,
                primary_artist=primary_artist,
                album=album_obj.get("name", ""),
                album_type=album_obj.get("album_type", "album"),
                release_date=rel_date,
                release_year=rel_year,
                duration_ms=dur_ms,
                popularity=pop,
                isrc=isrc,
                explicit=tr.get("explicit", False),
                primary_genre=genre_res.value,
                all_genres=combined_genres,
                theme=theme_res.value,
                era=era_res.value,
                decade=decade_res.value,
                language=lang_res.value,
                track_number=tr.get("track_number", 1),
                disc_number=tr.get("disc_number", 1),
                added_at=it.get("added_at", ""),
                added_by=(it.get("added_by") or {}).get("id", ""),
                spotify_url=tr.get("external_urls", {}).get("spotify", ""),
                metadata_confidence={
                    "primary_genre": genre_res.confidence.value,
                    "era": era_res.confidence.value,
                    "decade": decade_res.confidence.value,
                    "theme": theme_res.confidence.value,
                    "language": lang_res.confidence.value,
                },
                metadata_provenance={
                    "primary_genre": genre_res.provenance.value,
                    "era": era_res.provenance.value,
                    "decade": decade_res.provenance.value,
                    "theme": theme_res.provenance.value,
                    "language": lang_res.provenance.value,
                }
            )
            enriched_tracks.append(track_model)

        return Playlist(
            id=playlist_id,
            name=playlist_name,
            description=playlist_desc,
            owner=owner_name,
            tracks=enriched_tracks,
            total_tracks=len(enriched_tracks),
            url=playlist_url
        )

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        tracks: list[Track] | None = None,
        track_uris: list[str] | None = None
    ) -> Playlist:
        """Creates a new playlist and adds tracks in batches of 100 with failure tracking."""
        me = self.get_me()
        user_id = me["id"]

        payload = {
            "name": name,
            "description": description or "Curated by Mixsmith",
            "public": public
        }

        logger.info(f"Creating new Spotify playlist '{name}'...")
        try:
            data = self.api_request("POST", "me/playlists", json_data=payload)
        except Exception:
            data = self.api_request("POST", f"users/{user_id}/playlists", json_data=payload)

        p_id = data["id"]
        p_url = data.get("external_urls", {}).get("spotify", "")

        # Resolve and validate URIs
        raw_candidates: list[str] = []
        if track_uris:
            raw_candidates = list(track_uris)
        elif tracks:
            raw_candidates = [t.uri or t.id for t in tracks]

        resolved_uris: list[str] = []
        for candidate in raw_candidates:
            normalized = self.validate_and_normalize_track_uri(candidate)
            if normalized:
                resolved_uris.append(normalized)

        added_tracks_count = 0
        if resolved_uris:
            logger.info(f"Adding {len(resolved_uris)} verified tracks to playlist '{name}' in batches...")
            chunk_size = 100
            total_chunks = (len(resolved_uris) + chunk_size - 1) // chunk_size
            for idx, i in enumerate(range(0, len(resolved_uris), chunk_size)):
                chunk = resolved_uris[i:i + chunk_size]
                try:
                    self.api_request("POST", f"playlists/{p_id}/items", json_data={"uris": chunk})
                    added_tracks_count += len(chunk)
                except Exception as e:
                    msg = (
                        f"Failed adding batch {idx + 1}/{total_chunks} to new playlist '{name}' (ID: {p_id}). "
                        f"{added_tracks_count}/{len(resolved_uris)} tracks were successfully added before error: {e}"
                    )
                    logger.error(msg)
                    raise PartialMutationError(
                        msg,
                        playlist_id=p_id,
                        batches_completed=idx,
                        tracks_added=added_tracks_count,
                        details={"playlist_url": p_url, "created_playlist_id": p_id}
                    ) from e

        return Playlist(
            id=p_id,
            name=name,
            description=description,
            owner=user_id,
            public=public,
            tracks=tracks or [],
            total_tracks=added_tracks_count,
            url=p_url
        )

    def delete_playlist(self, identifier: str) -> bool:
        """Unfollows (deletes) a playlist from the user's library."""
        p_id = self.extract_playlist_id(identifier)
        self.api_request("DELETE", f"playlists/{p_id}/followers")
        logger.info(f"Unfollowed playlist {p_id}")
        return True


# Backward-compatible alias for existing scripts
class SpotifyClient(SpotifyConnector):
    """Backward compatibility wrapper preserving legacy static methods."""

    @staticmethod
    def declump_tracks_by_artist(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from mixsmith.core.declumper import declump_tracks
        track_models = [Track.from_dict(t) for t in tracks]
        result_tracks = declump_tracks(track_models, min_spacing=1)[0]
        return [t.to_dict() for t in result_tracks]

    @staticmethod
    def filter_and_sort_tracks(tracks: list[dict[str, Any]], **kwargs) -> list[dict[str, Any]]:
        from mixsmith.core.filters import filter_tracks
        track_models = [Track.from_dict(t) for t in tracks]

        sort_by = kwargs.pop("sort_by", None)
        filtered_models = filter_tracks(
            track_models,
            artist_filter=kwargs.get("artist_filter"),
            genre_filter=kwargs.get("genre_filter"),
            theme_filter=kwargs.get("theme_filter"),
            decade_filter=kwargs.get("decade_filter"),
            language_filter=kwargs.get("language_filter"),
            clean_only=kwargs.get("clean_only", False),
            explicit_only=kwargs.get("explicit_only", False),
            filter_expr=kwargs.get("filter_expr")
        )

        if sort_by:
            from mixsmith.core.sequencing import (
                ConstraintSequencingEngine,
                CurationConstraints,
            )
            engine = ConstraintSequencingEngine()
            plan = engine.curate(filtered_models, CurationConstraints(sort_mode=sort_by))
            filtered_models = plan.tracks

        return [t.to_dict() for t in filtered_models]
