"""Exportify-compatible CSV exporter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Union

from mixsmith.core.models import Playlist, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.export.csv")

CSV_HEADERS = [
    "Track URI",
    "Track Name",
    "Artist Name(s)",
    "Album Name",
    "Album Type",
    "Primary Genre",
    "All Genres",
    "Theme / Vibe",
    "Era / Decade",
    "Release Year",
    "Release Date",
    "Language / Region",
    "Popularity Tier",
    "Popularity Score",
    "Duration",
    "Duration (ms)",
    "Length Category",
    "Explicit",
    "Added At",
    "Added By",
    "ISRC",
    "Track Number",
    "Disc Number",
    "Spotify URL",
    "Track ID"
]


def export_tracks_to_csv(tracks: List[Track], output_path: Union[str, Path]) -> str:
    """Exports tracks to standard Exportify-compatible CSV with UTF-8 BOM."""
    output_file = Path(output_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for t in tracks:
            writer.writerow([
                t.uri,
                t.name,
                t.artist_display,
                t.album,
                t.album_type,
                t.primary_genre,
                ", ".join(t.all_genres),
                t.theme,
                f"{t.era} ({t.decade})",
                t.release_year or "",
                t.release_date,
                t.language,
                "Superstar Hit" if t.popularity >= 75 else ("Mainstream Popular" if t.popularity >= 50 else ("Moderate" if t.popularity >= 25 else "Hidden Gem")),
                t.popularity,
                t.duration_formatted,
                t.duration_ms,
                "Quick Track (<2:30)" if t.duration_ms < 150000 else ("Standard (2:30-5:00)" if t.duration_ms <= 300000 else "Extended / Epic (>5:00)"),
                "true" if t.explicit else "false",
                t.added_at,
                t.added_by,
                t.isrc,
                t.track_number,
                t.disc_number,
                t.spotify_url,
                t.id
            ])

    logger.info(f"Successfully exported {len(tracks)} tracks to {output_file}")
    return str(output_file)


def export_playlist_to_csv(playlist: Playlist, output_path: Union[str, Path]) -> str:
    """Exports playlist to CSV."""
    return export_tracks_to_csv(playlist.tracks, output_path)
