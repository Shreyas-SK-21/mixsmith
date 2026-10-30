"""Playlist management: splitting, merging, comparison, and snapshots."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from mixsmith.core.models import Playlist, Track
from mixsmith.utils.config import get_default_config_dir
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.manager")


def split_by_genre(playlist: Playlist) -> dict[str, Playlist]:
    """Splits a playlist into sub-playlists grouped by primary genre."""
    groups: dict[str, list[Track]] = defaultdict(list)
    for t in playlist.tracks:
        groups[t.primary_genre].append(t)

    result = {}
    for genre, tracks in groups.items():
        clean_name = f"{playlist.name} - {genre}"
        result[genre] = Playlist(
            id=f"{playlist.id}_{genre.lower().replace(' ', '_')}",
            name=clean_name,
            description=f"Genre subset ({genre}) from {playlist.name}",
            owner=playlist.owner,
            tracks=tracks
        )
    return result


def split_by_decade(playlist: Playlist) -> dict[str, Playlist]:
    """Splits a playlist into sub-playlists grouped by decade."""
    groups: dict[str, list[Track]] = defaultdict(list)
    for t in playlist.tracks:
        groups[t.decade].append(t)

    result = {}
    for decade, tracks in sorted(groups.items()):
        clean_name = f"{playlist.name} - {decade}"
        result[decade] = Playlist(
            id=f"{playlist.id}_{decade}",
            name=clean_name,
            description=f"Decade subset ({decade}) from {playlist.name}",
            owner=playlist.owner,
            tracks=tracks
        )
    return result


def merge_playlists(
    playlists: list[Playlist],
    name: str = "Merged Playlist",
    description: str = "",
    deduplicate: bool = True
) -> Playlist:
    """Merges multiple playlists into one, optionally deduplicating tracks."""
    combined_tracks: list[Track] = []
    seen_ids: set[str] = set()

    for p in playlists:
        for t in p.tracks:
            if deduplicate:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    combined_tracks.append(t)
            else:
                combined_tracks.append(t)

    return Playlist(
        id="merged_playlist",
        name=name,
        description=description or f"Merged from {len(playlists)} playlists",
        tracks=combined_tracks
    )


def compare_playlists(p1: Playlist, p2: Playlist) -> dict[str, Any]:
    """Compares two playlists, calculating overlap, differences, and Jaccard similarity."""
    set1 = {t.id: t for t in p1.tracks}
    set2 = {t.id: t for t in p2.tracks}

    common_ids = set(set1.keys()) & set(set2.keys())
    unique_p1_ids = set(set1.keys()) - set(set2.keys())
    unique_p2_ids = set(set2.keys()) - set(set1.keys())

    union_len = len(set(set1.keys()) | set(set2.keys()))
    jaccard_similarity = len(common_ids) / union_len if union_len > 0 else 0.0

    return {
        "playlist_1": p1.name,
        "playlist_2": p2.name,
        "common_count": len(common_ids),
        "unique_to_p1_count": len(unique_p1_ids),
        "unique_to_p2_count": len(unique_p2_ids),
        "jaccard_similarity": round(jaccard_similarity * 100, 1),
        "common_tracks": [set1[i].name for i in list(common_ids)[:10]],
        "unique_to_p1": [set1[i].name for i in list(unique_p1_ids)[:10]],
        "unique_to_p2": [set2[i].name for i in list(unique_p2_ids)[:10]]
    }


def save_playlist_snapshot(playlist: Playlist, snapshot_dir: Path | None = None) -> Path:
    """Saves a JSON snapshot of a playlist state before modification."""
    target_dir = snapshot_dir or (get_default_config_dir() / "snapshots")
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_id = "".join(c for c in playlist.id if c.isalnum() or c in ("-", "_"))
    filepath = target_dir / f"snapshot_{clean_id}_{timestamp}.json"

    data = {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "timestamp": timestamp,
        "total_tracks": len(playlist.tracks),
        "tracks": [t.to_dict() for t in playlist.tracks]
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved snapshot to {filepath}")
    return filepath
