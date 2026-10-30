"""Listening journey sequencing modes."""

from __future__ import annotations

from typing import Dict, List, Optional

from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.journeys")

# Canonical acoustic and stylistic adjacency map for genre transitions
GENRE_JOURNEY_ORDER = [
    "Classical / Cinematic",
    "Jazz & Blues",
    "Folk & Acoustic",
    "Country / Americana",
    "R&B / Soul",
    "Desi / South Asian",
    "Latin",
    "Pop",
    "K-Pop",
    "J-Pop / Japanese",
    "Shoegaze / Dream Pop",
    "Indie / Alternative",
    "Rock",
    "Metal",
    "Hip-Hop / Rap",
    "Electronic / Dance"
]

DECADE_ORDER = {
    "pre-60s": 0,
    "60s": 1,
    "70s": 2,
    "80s": 3,
    "90s": 4,
    "2000s": 5,
    "2010s": 6,
    "2020s": 7
}


def sequence_artist_evolution(tracks: List[Track], reverse: bool = False) -> List[Track]:
    """Arranges tracks in chronological order of release date to trace musical growth."""
    return sorted(
        tracks,
        key=lambda t: (
            t.release_year or (0 if reverse else 9999),
            t.release_date or "",
            t.album.lower(),
            t.disc_number,
            t.track_number
        ),
        reverse=reverse
    )


def sequence_decade_journey(tracks: List[Track], reverse: bool = False) -> List[Track]:
    """Sequences tracks smoothly through musical eras (60s -> 70s -> 80s -> 90s -> 2000s -> 2010s -> 2020s)."""
    return sorted(
        tracks,
        key=lambda t: (
            DECADE_ORDER.get(t.decade.lower(), 99),
            t.release_year or (0 if reverse else 9999),
            t.release_date or ""
        ),
        reverse=reverse
    )


def sequence_genre_journey(tracks: List[Track], custom_order: Optional[List[str]] = None) -> List[Track]:
    """Sequences tracks to provide smooth sonic transitions between complementary genres."""
    order = custom_order or GENRE_JOURNEY_ORDER
    idx_map: Dict[str, int] = {g.lower(): i for i, g in enumerate(order)}

    return sorted(
        tracks,
        key=lambda t: (
            idx_map.get(t.primary_genre.lower(), 99),
            t.popularity
        )
    )


def sequence_nostalgia_mode(tracks: List[Track], target_decade: str = "90s") -> List[Track]:
    """
    Prioritizes tracks from a target decade, placing them as the centerpiece,
    while smoothly easing in from preceding eras and easing out to modern times.
    """
    target = target_decade.lower().strip()
    target_idx = DECADE_ORDER.get(target, 4)

    def decade_distance(t: Track) -> int:
        d_idx = DECADE_ORDER.get(t.decade.lower(), 99)
        return abs(d_idx - target_idx)

    # Sort primarily by proximity to target decade, secondary by popularity
    return sorted(
        tracks,
        key=lambda t: (
            decade_distance(t),
            -t.popularity
        )
    )
