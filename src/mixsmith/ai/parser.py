"""Natural language instruction interpreter for playlist curation."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from mixsmith.ai.schema import NaturalLanguageCurationSpec
from mixsmith.core.filters import filter_tracks
from mixsmith.core.models import CurationPlan, Track
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.ai")


def parse_natural_language_heuristics(prompt: str) -> NaturalLanguageCurationSpec:
    """
    Deterministic rule-based parser that extracts structured constraints from natural language.
    Does not require external API keys.
    """
    p = prompt.lower()
    spec = NaturalLanguageCurationSpec()

    # 1. Target Duration
    dur_match = re.search(r"\b(\d+)\s*(?:hour|hr)s?\b", p)
    if dur_match:
        spec.target_duration_minutes = int(dur_match.group(1)) * 60
    else:
        # Check text numbers (two-hour, 1 hour, etc.)
        word_to_num = {"one": 60, "two": 120, "three": 180, "four": 240}
        for word, mins in word_to_num.items():
            if f"{word}-hour" in p or f"{word} hour" in p:
                spec.target_duration_minutes = mins
                break

    min_match = re.search(r"\b(\d+)\s*(?:minute|min)s?\b", p)
    if min_match:
        spec.target_duration_minutes = (spec.target_duration_minutes or 0) + int(min_match.group(1))

    # 2. Artist Spacing
    spacing_match = re.search(r"(?:repeat|spacing|distance|buffer).*?(\d+)\s*(?:track|song)", p)
    if not spacing_match:
        spacing_match = re.search(r"within\s+(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:track|song)", p)
    if spacing_match:
        raw_val = spacing_match.group(1)
        word_map = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        spec.min_artist_spacing = word_map.get(raw_val, int(raw_val) if raw_val.isdigit() else 1)
    elif "no back-to-back" in p or "no consecutive" in p or "declump" in p or "avoid repeating" in p:
        spec.min_artist_spacing = 1

    # 3. Themes
    theme_keywords = {
        "late-night drive": "Late Night Drive",
        "late night drive": "Late Night Drive",
        "late-night": "Late Night Drive",
        "late night": "Late Night Drive",
        "workout": "Workout / Gym",
        "gym": "Workout / Gym",
        "chill": "Chill & Coffee Shop",
        "coffee": "Chill & Coffee Shop",
        "party": "Party & Club",
        "club": "Party & Club",
        "road trip": "Road Trip",
        "focus": "Focus & Study",
        "study": "Focus & Study",
        "heartbreak": "Heartbreak & Melancholy",
        "love": "Love & Romance"
    }
    for kw, th in theme_keywords.items():
        if kw in p and th not in spec.themes_included:
            spec.themes_included.append(th)

    # 4. Decades
    for dec in ["60s", "70s", "80s", "90s", "2000s", "2010s", "2020s"]:
        if dec in p:
            spec.decades_included.append(dec)

    # 5. Genres
    genres = [
        "shoegaze", "dream pop", "rock", "indie", "metal", "hip-hop", "rap",
        "pop", "r&b", "soul", "latin", "k-pop", "j-pop", "desi", "country",
        "folk", "jazz", "blues", "classical", "electronic", "dance"
    ]
    for g in genres:
        if re.search(rf"\b{g}\b", p):
            spec.genres_included.append(g.title())

    # 6. Sorting mode
    if "mellow to energetic" in p or "energy" in p or "gradual" in p:
        spec.sort_mode = "gems"  # Start underground/mellow towards superstar hits
    elif "chronological" in p or "time travel" in p or "oldest" in p:
        spec.sort_mode = "chronological"
    elif "decade" in p or "era" in p:
        spec.sort_mode = "decade"
    elif "genre" in p:
        spec.sort_mode = "genre"
    else:
        spec.sort_mode = "declump"

    # 7. Explicit / Clean
    if "clean only" in p or "radio friendly" in p or "family friendly" in p:
        spec.clean_only = True
    elif "explicit only" in p:
        spec.explicit_only = True

    # 8. Playlist Name
    if spec.themes_included:
        spec.name = f"{spec.themes_included[0]} Mix"
    elif spec.genres_included:
        spec.name = f"{spec.genres_included[0]} Session"
    else:
        spec.name = "Curated Selection"

    return spec


def execute_natural_language_curation(
    tracks: List[Track],
    prompt: str,
    spec_override: Optional[NaturalLanguageCurationSpec] = None
) -> Tuple[CurationPlan, NaturalLanguageCurationSpec]:
    """
    Accepts natural-language instructions, parses them into structured constraints,
    and executes deterministic filtering and sequencing.
    """
    spec = spec_override or parse_natural_language_heuristics(prompt)

    # 1. Deterministic Filtering
    filtered = filter_tracks(
        tracks,
        artist_filter=",".join(spec.artists_included) if spec.artists_included else None,
        genre_filter=",".join(spec.genres_included) if spec.genres_included else None,
        theme_filter=",".join(spec.themes_included) if spec.themes_included else None,
        decade_filter=",".join(spec.decades_included) if spec.decades_included else None,
        clean_only=spec.clean_only,
        explicit_only=spec.explicit_only
    )

    if not filtered:
        # Fall back to base tracks if combined filter was too restrictive
        logger.warning("Combined filter matched 0 tracks; relaxing to all source tracks for sequencing.")
        filtered = list(tracks)

    # 2. Deterministic Constraint Sequencing
    constraints = CurationConstraints(
        min_artist_spacing=spec.min_artist_spacing,
        max_tracks_per_artist=spec.max_tracks_per_artist,
        target_duration_minutes=spec.target_duration_minutes,
        sort_mode=spec.sort_mode
    )

    engine = ConstraintSequencingEngine()
    plan = engine.curate(filtered, constraints=constraints, playlist_name=spec.name)

    return plan, spec
