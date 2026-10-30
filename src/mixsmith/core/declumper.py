"""Advanced Multi-Artist Aware De-clumping and Artist Spacing Engine."""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from mixsmith.core.models import ConstraintResult, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.declumper")


@dataclass
class FeasibilityReport:
    """Report on mathematical feasibility of requested spacing."""
    is_feasible: bool
    requested_spacing: int
    max_achievable_spacing: int
    bottleneck_artists: List[Tuple[str, int, int]]  # (artist, count, min_tracks_needed)
    total_tracks: int


def analyze_spacing_feasibility(
    tracks: List[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True
) -> FeasibilityReport:
    """
    Checks if a minimum spacing of k tracks between occurrences of the same artist is mathematically possible.
    For an artist appearing C times, placing them with spacing k requires at least (C - 1) * (k + 1) + 1 tracks.
    """
    n = len(tracks)
    if n <= 1:
        return FeasibilityReport(
            is_feasible=True,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_spacing,
            bottleneck_artists=[],
            total_tracks=n
        )

    # Count occurrences per artist
    artist_counts: Dict[str, int] = defaultdict(int)
    for t in tracks:
        artists = t.artists if consider_all_artists and t.artists else [t.primary_artist or "Unknown"]
        for a in set(artists):
            artist_counts[a.lower().strip()] += 1

    bottlenecks = []
    min_achievable = min_spacing

    for artist, count in artist_counts.items():
        if count <= 1:
            continue
        # Length needed for spacing k
        needed_len = (count - 1) * (min_spacing + 1) + 1
        if needed_len > n:
            # Spacing k impossible; compute max achievable
            achievable = max(0, (n - 1) // (count - 1) - 1)
            min_achievable = min(min_achievable, achievable)
            bottlenecks.append((artist, count, needed_len))

    is_feasible = len(bottlenecks) == 0
    return FeasibilityReport(
        is_feasible=is_feasible,
        requested_spacing=min_spacing,
        max_achievable_spacing=min_achievable,
        bottleneck_artists=sorted(bottlenecks, key=lambda x: x[1], reverse=True),
        total_tracks=n
    )


def declump_tracks(
    tracks: List[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True
) -> Tuple[List[Track], ConstraintResult]:
    """
    Smart Artist Spacing (De-clumper).
    
    Ensures that tracks by the same artist (including co-artists and featured artists)
    are separated by at least `min_spacing` tracks.
    
    Uses a maximum-frequency scheduling algorithm with cooldown queues,
    with a graceful degradation fallback if spacing is mathematically tight or infeasible.
    """
    if len(tracks) <= 2:
        return list(tracks), ConstraintResult(
            name="artist_spacing",
            satisfied=True,
            details="Playlist has <= 2 tracks; no de-clumping needed."
        )

    feasibility = analyze_spacing_feasibility(tracks, min_spacing, consider_all_artists)
    if not feasibility.is_feasible:
        logger.warning(
            f"Requested spacing of {min_spacing} tracks is mathematically infeasible. "
            f"Max achievable without collisions: {feasibility.max_achievable_spacing}. "
            f"Top bottleneck: {feasibility.bottleneck_artists[0][0]} ({feasibility.bottleneck_artists[0][1]} tracks in {len(tracks)} total)."
        )

    # Helper to get artists set for a track
    def get_track_artists(t: Track) -> Set[str]:
        if consider_all_artists and t.artists:
            return {a.lower().strip() for a in t.artists if a.strip()}
        return {t.primary_artist.lower().strip()} if t.primary_artist else {"unknown"}

    # Group tracks into per-primary-artist buckets while maintaining original relative order
    buckets: Dict[str, List[Track]] = defaultdict(list)
    for t in tracks:
        key = t.primary_artist.lower().strip() if t.primary_artist else "unknown"
        buckets[key].append(t)

    # Track total remaining occurrences per artist (across primary and featured)
    remaining_artist_frequency: Dict[str, int] = defaultdict(int)
    for t in tracks:
        for a in get_track_artists(t):
            remaining_artist_frequency[a] += 1

    result: List[Track] = []
    # Cooldown history: stores artist sets of the last `min_spacing` tracks
    recent_history: deque[Set[str]] = deque(maxlen=min_spacing)
    # Track the last index each artist was placed at to measure actual distance
    last_placed_index: Dict[str, int] = {}

    remaining_tracks = list(tracks)
    collisions_count = 0

    while remaining_tracks:
        current_idx = len(result)
        recent_artists: Set[str] = set()
        for s in recent_history:
            recent_artists.update(s)

        # Separate candidates into valid (no recent artist overlap) vs conflicting
        valid_candidates: List[Track] = []
        conflicting_candidates: List[Track] = []

        for t in remaining_tracks:
            t_artists = get_track_artists(t)
            if not (t_artists & recent_artists):
                valid_candidates.append(t)
            else:
                conflicting_candidates.append(t)

        if valid_candidates:
            # Score valid candidates: prioritize tracks whose artists have highest remaining global frequency
            # Tie breaker: tracks whose primary artist hasn't been heard in the longest time
            def score_candidate(t: Track) -> Tuple[int, int]:
                freq_score = sum(remaining_artist_frequency[a] for a in get_track_artists(t))
                # Distance since last appearance
                min_dist = min((current_idx - last_placed_index.get(a, -1000) for a in get_track_artists(t)), default=1000)
                return (freq_score, min_dist)

            best_track = max(valid_candidates, key=score_candidate)
        else:
            # Graceful fallback: pick the conflicting candidate that maximizes the distance from its last appearance
            collisions_count += 1

            def fallback_score(t: Track) -> int:
                # Maximize minimum distance from recent placements
                return min((current_idx - last_placed_index.get(a, -1) for a in get_track_artists(t)), default=0)

            best_track = max(conflicting_candidates, key=fallback_score)

        # Place the chosen track
        remaining_tracks.remove(best_track)
        result.append(best_track)

        t_artists = get_track_artists(best_track)
        recent_history.append(t_artists)
        for a in t_artists:
            last_placed_index[a] = current_idx
            remaining_artist_frequency[a] -= 1

    # Measure spacing outcome
    min_distance_found = float("inf")
    violations = 0
    artist_positions: Dict[str, List[int]] = defaultdict(list)

    for idx, t in enumerate(result):
        for a in get_track_artists(t):
            artist_positions[a].append(idx)

    for a, positions in artist_positions.items():
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                gap = positions[i + 1] - positions[i] - 1
                if gap < min_distance_found:
                    min_distance_found = gap
                if gap < min_spacing:
                    violations += 1

    satisfied = violations == 0
    if satisfied:
        details = f"All {len(result)} tracks arranged with >= {min_spacing} tracks between repeated artists."
        severity = "info"
    else:
        details = (
            f"Achieved de-clumping with {violations} relaxed spacing occurrences "
            f"(requested spacing {min_spacing}, best achievable for dataset: {feasibility.max_achievable_spacing})."
        )
        severity = "warning"

    return result, ConstraintResult(
        name="artist_spacing",
        satisfied=satisfied,
        details=details,
        severity=severity
    )
