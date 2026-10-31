"""Natural language instruction interpreter for playlist curation with constraint tiering."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from mixsmith.ai.schema import (
    Ambiguity,
    CurationSpecification,
    NaturalLanguageCurationSpec,
)
from mixsmith.core.exceptions import FilterMatchError
from mixsmith.core.filters import filter_tracks
from mixsmith.core.models import CurationPlan, Track
from mixsmith.core.quotas import allocate_genre_quotas
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.ai")


class LLMProviderBase(ABC):
    """Abstract interface for LLM-assisted and heuristic natural language parsers."""

    @abstractmethod
    def parse_instruction(self, prompt: str) -> CurationSpecification:
        """Parses natural language prompt into structured CurationSpecification."""


class OfflineHeuristicProvider(LLMProviderBase):
    """Deterministic rule-based parser extracting hard, soft constraints and preferences."""

    def parse_instruction(self, prompt: str) -> CurationSpecification:
        return parse_natural_language_to_spec(prompt)


def parse_natural_language_to_spec(prompt: str) -> CurationSpecification:
    """
    Deterministic rule-based parser that extracts tiered constraints from natural language.
    Produces a CurationSpecification containing HardConstraints, SoftConstraints, and Preferences,
    with automatic conflict and ambiguity detection.
    """
    p = prompt.lower()
    spec = CurationSpecification()
    hard = spec.hard_constraints
    soft = spec.soft_constraints
    prefs = spec.preferences

    # 1. Target Duration & Duration Bounds
    dur_match = re.search(r"\b(\d+)[-\s]*(?:hour|hr)s?\b", p)
    if dur_match:
        soft.target_duration_minutes = int(dur_match.group(1)) * 60
    else:
        word_to_num = {"one": 60, "two": 120, "three": 180, "four": 240}
        for word, mins in word_to_num.items():
            if f"{word}-hour" in p or f"{word} hour" in p:
                soft.target_duration_minutes = mins
                break

    min_match = re.search(r"\b(\d+)[-\s]*(?:minute|min)s?\b", p)
    if min_match:
        soft.target_duration_minutes = (soft.target_duration_minutes or 0) + int(min_match.group(1))

    # Min/Max duration bounds
    min_bound = re.search(r"(?:at least|minimum of|min)\s+(\d+)\s*(?:min|minute|hour|hr)", p)
    if min_bound:
        val = int(min_bound.group(1))
        if "hour" in min_bound.group(0) or "hr" in min_bound.group(0):
            val *= 60
        hard.min_duration_minutes = val

    max_bound = re.search(r"(?:at most|maximum of|under|max)\s+(\d+)\s*(?:min|minute|hour|hr)", p)
    if max_bound:
        val = int(max_bound.group(1))
        if "hour" in max_bound.group(0) or "hr" in max_bound.group(0):
            val *= 60
        hard.max_duration_minutes = val

    # 2. Artist Spacing (Hard constraint)
    spacing_match = re.search(r"(?:repeat|spacing|distance|buffer).*?(\d+)\s*(?:track|song)", p)
    if not spacing_match:
        spacing_match = re.search(r"within\s+(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:track|song)", p)
    if spacing_match:
        raw_val = spacing_match.group(1)
        word_map = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        hard.min_artist_spacing = word_map.get(raw_val, int(raw_val) if raw_val.isdigit() else 1)
    elif "no back-to-back" in p or "no consecutive" in p or "declump" in p or "avoid repeating" in p:
        hard.min_artist_spacing = 1

    # 3. Max tracks per artist
    max_tracks_match = re.search(r"(?:max|at most|no more than)\s+(\d+|one|two|three|four|five)\s*(?:tracks?|songs?)\s*(?:per|from each|from any)\s*artist", p)
    if max_tracks_match:
        m_val = max_tracks_match.group(1)
        word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        hard.max_tracks_per_artist = word_map.get(m_val, int(m_val) if m_val.isdigit() else 2)

    # 4. Clean / Explicit
    if "clean only" in p or "radio friendly" in p or "family friendly" in p or "clean version" in p or "no explicit" in p:
        hard.clean_only = True
    if "explicit only" in p or "explicit tracks only" in p or "all explicit" in p:
        hard.explicit_only = True

    # 5. Themes (Soft constraint)
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
        if kw in p and th not in soft.desired_themes:
            soft.desired_themes.append(th)

    # 6. Decades
    for dec in ["60s", "70s", "80s", "90s", "2000s", "2010s", "2020s"]:
        if dec in p:
            hard.must_include_decades.append(dec)

    # 7. Genres (Inclusions, Exclusions, Quotas)
    known_genres = [
        "shoegaze", "dream pop", "rock", "indie rock", "indie", "metal", "hip-hop", "rap",
        "pop", "r&b", "soul", "latin", "k-pop", "j-pop", "desi", "country",
        "folk", "jazz", "blues", "classical", "electronic", "dance"
    ]
    for g in known_genres:
        if re.search(rf"\b(?:no|exclude|without|skip)\s+{g}\b", p):
            hard.must_exclude_genres.append(g.title())
        elif re.search(rf"\b{g}\b", p):
            pct_match = re.search(rf"(\d+)%\s*{g}", p)
            if pct_match:
                soft.desired_genres[g.title()] = float(pct_match.group(1)) / 100.0
            else:
                hard.must_include_genres.append(g.title())

    # 8. Artist inclusions & exclusions
    for exclude_match in re.finditer(r"\b(?:no|exclude|without|skip)\s+([A-Za-z0-9\s,\'\"\.\-]+?)(?:,|$|\.|\band\b|\bbut\b|\binclude\b)", prompt, re.IGNORECASE):
        candidate_clause = exclude_match.group(1).strip()
        for cand in re.split(r",|\band\b", candidate_clause):
            cand_clean = cand.strip()
            if cand_clean and cand_clean.lower() not in [g.lower() for g in known_genres] and len(cand_clean) > 2:
                if not any(k in cand_clean.lower() for k in ["repeat", "track", "hour", "minute", "drive", "energy"]):
                    hard.must_exclude_artists.append(cand_clean.title())

    for with_match in re.finditer(r"\b(?:with|featuring|include|including)\s+([A-Za-z0-9\s,\'\"\.\-]+?)(?:\.|$|\bavoid\b|\bstart\b|\bno\b|\bbut\b|\bexclude\b)", prompt, re.IGNORECASE):
        candidate_clause = with_match.group(1).strip()
        for cand in re.split(r",|\band\b", candidate_clause):
            cand_clean = cand.strip()
            if cand_clean and cand_clean.lower() not in [g.lower() for g in known_genres] and len(cand_clean) > 2:
                if not any(k in cand_clean.lower() for k in ["repeat", "track", "hour", "minute", "drive", "energy"]):
                    hard.must_include_artists.append(cand_clean.title())

    # 9. Preferences: Journey, Popularity, Energy (Distinct from Popularity)
    if "hidden gems" in p or "deep cuts" in p or "underground" in p:
        prefs.popularity_preference = "hidden_gems"
        prefs.sort_journey = "gems"
    elif "superstar hits" in p or "hits first" in p or "popular" in p:
        prefs.popularity_preference = "hits"
        prefs.sort_journey = "popularity"

    # Distinct energy preference: Popularity is NOT musical energy
    if "mellow to energetic" in p or "gradual energy" in p or re.search(r"\bstarts?\s+mellow\b", p) or ("mellow" in p and "energy" in p) or "builds energy" in p or "build energy" in p:
        prefs.tempo_energy_preference = "mellow_to_energetic"
        # Preserve artist spacing journey rather than conflating energy with popularity
        if not prefs.sort_journey:
            prefs.sort_journey = "declump"
        spec.ambiguities.append(Ambiguity(
            parameter="tempo_energy",
            query=prompt,
            default_interpretation="Energy progression requested; artist spacing preserved without conflating popularity with acoustic energy."
        ))
    elif "energetic to mellow" in p or "wind down" in p:
        prefs.tempo_energy_preference = "energetic_to_mellow"
        if not prefs.sort_journey:
            prefs.sort_journey = "declump"
    elif "chronological" in p or "time travel" in p or "oldest" in p:
        prefs.sort_journey = "chronological"
    elif "decade" in p or "era" in p:
        prefs.sort_journey = "decade"
    elif "genre" in p:
        prefs.sort_journey = "genre"
    elif not prefs.sort_journey:
        prefs.sort_journey = "declump"

    # 10. Ambiguity Detection
    if "some" in p and not soft.desired_genres:
        spec.ambiguities.append(Ambiguity(
            parameter="quotas",
            query=prompt,
            default_interpretation="Equal proportional quota fallback."
        ))

    # 11. Playlist Name
    if soft.desired_themes:
        spec.name = f"{soft.desired_themes[0]} Mix"
    elif hard.must_include_genres:
        spec.name = f"{hard.must_include_genres[0]} Session"
    elif hard.must_include_artists:
        spec.name = f"{hard.must_include_artists[0]} & Friends Mix"
    else:
        spec.name = "Curated Selection"

    spec.description = f"Intelligently curated based on: '{prompt}'"

    # Run conflict validation
    spec.validate_conflicts()
    return spec


def parse_natural_language_heuristics(prompt: str) -> NaturalLanguageCurationSpec:
    """
    Deterministic rule-based parser returning backward-compatible flat spec.
    """
    spec = parse_natural_language_to_spec(prompt)
    return spec.to_flat_spec()


def execute_natural_language_curation(
    tracks: list[Track],
    prompt: str,
    spec_override: CurationSpecification | NaturalLanguageCurationSpec | None = None
) -> tuple[CurationPlan, CurationSpecification]:
    """
    Accepts natural-language instructions, parses them into structured constraints,
    and executes deterministic filtering, knapsack duration, and sequencing.
    Returns the generated CurationPlan and the active CurationSpecification.
    """
    if spec_override is None:
        spec = parse_natural_language_to_spec(prompt)
    elif isinstance(spec_override, NaturalLanguageCurationSpec):
        spec = spec_override.to_curation_spec()
    else:
        spec = spec_override

    # Halt on hard conflicts
    conflicts = spec.validate_conflicts()
    if conflicts:
        conflict_msg = "; ".join(f"{c.conflict_type}: {c.description}" for c in conflicts)
        logger.error(f"Cannot execute curation due to constraint conflicts: {conflict_msg}")
        raise ValueError(f"Constraint conflict detected: {conflict_msg}")

    # 1. Deterministic Filtering
    hard = spec.hard_constraints
    soft = spec.soft_constraints
    prefs = spec.preferences

    artists_inc = ",".join(hard.must_include_artists) if hard.must_include_artists else None
    genres_inc = ",".join(hard.must_include_genres) if hard.must_include_genres else None
    themes_inc = ",".join(soft.desired_themes) if soft.desired_themes else None
    decades_inc = ",".join(hard.must_include_decades) if hard.must_include_decades else None

    filtered = filter_tracks(
        tracks,
        artist_filter=artists_inc,
        genre_filter=genres_inc,
        theme_filter=themes_inc,
        decade_filter=decades_inc,
        clean_only=hard.clean_only,
        explicit_only=hard.explicit_only,
    )

    # Filter out excluded artists and genres
    if hard.must_exclude_artists:
        ex_artists_lower = set(a.lower() for a in hard.must_exclude_artists)
        filtered = [t for t in filtered if not any(a.lower() in ex_artists_lower for a in t.all_artists)]

    if hard.must_exclude_genres:
        ex_genres_lower = set(g.lower() for g in hard.must_exclude_genres)
        filtered = [t for t in filtered if not any(g.lower() in ex_genres_lower for g in t.all_genres)]

    if not filtered:
        msg = (
            f"Curation filter matched 0 tracks from input library of {len(tracks)} tracks. "
            f"Active filters: artists={hard.must_include_artists}, "
            f"genres={hard.must_include_genres}, decades={hard.must_include_decades}, "
            f"clean_only={hard.clean_only}, explicit_only={hard.explicit_only}."
        )
        logger.error(msg)
        raise FilterMatchError(msg)

    # 2. Genre Quota Allocation (if soft constraints specify desired genre ratios)
    if soft.desired_genres:
        quota_res = allocate_genre_quotas(filtered, soft.desired_genres)
        if quota_res.selected_tracks:
            filtered = quota_res.selected_tracks

    # 3. Deterministic Constraint Sequencing
    pop_bias = "hits" if prefs.popularity_preference == "hits" else ("gems" if prefs.popularity_preference == "hidden_gems" else None)
    constraints = CurationConstraints(
        min_artist_spacing=hard.min_artist_spacing,
        max_tracks_per_artist=hard.max_tracks_per_artist,
        target_duration_minutes=soft.target_duration_minutes,
        min_duration_minutes=hard.min_duration_minutes,
        max_duration_minutes=hard.max_duration_minutes,
        genre_distribution=soft.desired_genres,
        decade_distribution=soft.desired_decades,
        sort_mode=prefs.sort_journey or "declump",
        energy_progression=prefs.tempo_energy_preference,
        popularity_bias=pop_bias
    )

    engine = ConstraintSequencingEngine()
    plan = engine.curate(filtered, constraints=constraints, playlist_name=spec.name)

    return plan, spec
