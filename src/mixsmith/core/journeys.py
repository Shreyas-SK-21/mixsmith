"""Listening journey sequencing modes."""

from __future__ import annotations

import re
from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger
from mixsmith.utils.metadata import MetadataConfidence, MetadataProvenance

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


def sequence_artist_evolution(tracks: list[Track], reverse: bool = False) -> list[Track]:
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


def sequence_decade_journey(tracks: list[Track], reverse: bool = False) -> list[Track]:
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


def sequence_genre_journey(tracks: list[Track], custom_order: list[str] | None = None) -> list[Track]:
    """Sequences tracks to provide smooth sonic transitions between complementary genres."""
    order = custom_order or GENRE_JOURNEY_ORDER
    idx_map: dict[str, int] = {g.lower(): i for i, g in enumerate(order)}

    return sorted(
        tracks,
        key=lambda t: (
            idx_map.get(t.primary_genre.lower(), 99),
            t.popularity if t.popularity is not None else 50
        )
    )


def sequence_nostalgia_mode(tracks: list[Track], target_decade: str = "90s") -> list[Track]:
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
            -(t.popularity if t.popularity is not None else 50)
        )
    )


# Baseline thematic energy mapping (0 to 100)
THEME_ENERGY_MAP: dict[str, float] = {
    "chill & coffee shop": 25.0,
    "focus & study": 30.0,
    "heartbreak": 35.0,
    "love & romance": 45.0,
    "late night drive": 50.0,
    "road trip": 70.0,
    "party & club": 85.0,
    "workout / gym": 90.0,
    "eclectic & diverse": 50.0
}

# Baseline genre energy mapping (0 to 100)
GENRE_ENERGY_MAP: dict[str, float] = {
    "classical / cinematic": 20.0,
    "jazz & blues": 35.0,
    "folk & acoustic": 35.0,
    "r&b / soul": 45.0,
    "shoegaze / dream pop": 45.0,
    "indie / alternative": 55.0,
    "country / americana": 55.0,
    "pop": 65.0,
    "k-pop": 70.0,
    "j-pop / japanese": 65.0,
    "desi / south asian": 70.0,
    "latin": 75.0,
    "hip-hop / rap": 80.0,
    "rock": 85.0,
    "electronic / dance": 90.0,
    "metal": 95.0,
    "other / unclassified": 50.0
}


def compute_track_energy(track: Track) -> tuple[float, MetadataConfidence, MetadataProvenance]:
    """
    Computes a platform-independent energy estimate (0.0 to 100.0) from permitted metadata:
    theme, primary genre, and title version descriptors.
    Never uses popularity as a proxy for musical energy.
    """
    theme_key = track.theme.lower().strip()
    genre_key = track.primary_genre.lower().strip()

    theme_score = THEME_ENERGY_MAP.get(theme_key, 50.0)
    genre_score = GENRE_ENERGY_MAP.get(genre_key, 50.0)

    # Base weighted energy
    if theme_key in THEME_ENERGY_MAP and genre_key in GENRE_ENERGY_MAP:
        base_energy = 0.55 * theme_score + 0.45 * genre_score
        confidence = MetadataConfidence.HIGH
        provenance = MetadataProvenance.GENRE_ASSOCIATION
    elif theme_key in THEME_ENERGY_MAP:
        base_energy = theme_score
        confidence = MetadataConfidence.MEDIUM
        provenance = MetadataProvenance.GENRE_ASSOCIATION
    elif genre_key in GENRE_ENERGY_MAP:
        base_energy = genre_score
        confidence = MetadataConfidence.MEDIUM
        provenance = MetadataProvenance.GENRE_ASSOCIATION
    else:
        base_energy = 50.0
        confidence = MetadataConfidence.LOW
        provenance = MetadataProvenance.DEFAULT_FALLBACK

    # Title version modifiers
    title_lower = track.name.lower()
    modifier = 0.0

    # Calming / mellow cues
    if re.search(r"\b(acoustic|unplugged|piano|lullaby|slowed|ambient|stripped|orchestral)\b", title_lower):
        modifier -= 20.0
        confidence = MetadataConfidence.HIGH
        provenance = MetadataProvenance.TITLE_HEURISTIC
    # Energetic cues
    elif re.search(r"\b(remix|club mix|extended mix|dance mix|hardstyle|live|rave|drop)\b", title_lower):
        modifier += 20.0
        confidence = MetadataConfidence.HIGH
        provenance = MetadataProvenance.TITLE_HEURISTIC

    final_energy = max(5.0, min(95.0, base_energy + modifier))
    return final_energy, confidence, provenance


def sequence_energy_progression(tracks: list[Track], direction: str = "mellow_to_energetic") -> list[Track]:
    """
    Sequences tracks along an acoustic energy progression.
    direction="mellow_to_energetic": smooth ascent from mellow/calm to high energy.
    direction="energetic_to_mellow": descent from energetic anthems into chill-out tracks.
    """
    reverse = (direction == "energetic_to_mellow")

    return sorted(
        tracks,
        key=lambda t: compute_track_energy(t)[0],
        reverse=reverse
    )
