"""Playlist duration optimization engine using discrete 0/1 knapsack and multi-objective heuristics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.duration")


@dataclass
class DurationOptimizationResult:
    """Outcome of playlist duration optimization."""
    selected_tracks: List[Track]
    excluded_tracks: List[Track]
    total_duration_ms: int
    target_duration_ms: int
    tolerance_ms: int
    delta_ms: int
    is_within_tolerance: bool
    selection_reasons: Dict[str, str] = field(default_factory=dict)
    exclusion_reasons: Dict[str, str] = field(default_factory=dict)


def optimize_playlist_duration(
    tracks: List[Track],
    target_minutes: int,
    tolerance_minutes: int = 10,
    time_unit_seconds: int = 5
) -> DurationOptimizationResult:
    """
    Selects a subset of tracks to match target duration within [target - tol, target + tol],
    while maximizing a combined objective:
      1. Proximity to target duration.
      2. Artist diversity (penalizing redundant tracks from the same artist).
      3. Track quality/popularity.
    
    Uses scaled discrete dynamic programming (0/1 Knapsack) for datasets <= 250 tracks,
    and a bounded approximation heuristic for larger libraries.
    """
    target_ms = target_minutes * 60 * 1000
    tol_ms = tolerance_minutes * 60 * 1000
    min_acceptable_ms = max(0, target_ms - tol_ms)
    max_acceptable_ms = target_ms + tol_ms

    if not tracks:
        return DurationOptimizationResult(
            selected_tracks=[],
            excluded_tracks=[],
            total_duration_ms=0,
            target_duration_ms=target_ms,
            tolerance_ms=tol_ms,
            delta_ms=-target_ms,
            is_within_tolerance=False
        )

    total_pool_ms = sum(t.duration_ms for t in tracks)
    # If the entire pool is already smaller than or equal to max acceptable
    if total_pool_ms <= max_acceptable_ms:
        within = total_pool_ms >= min_acceptable_ms
        return DurationOptimizationResult(
            selected_tracks=list(tracks),
            excluded_tracks=[],
            total_duration_ms=total_pool_ms,
            target_duration_ms=target_ms,
            tolerance_ms=tol_ms,
            delta_ms=total_pool_ms - target_ms,
            is_within_tolerance=within,
            selection_reasons={t.id: "Entire track pool fits within duration ceiling" for t in tracks}
        )

    # Coarse time discretization for DP capacity
    unit_ms = time_unit_seconds * 1000
    target_units = target_ms // unit_ms
    max_units = max_acceptable_ms // unit_ms

    # If track count is reasonable (<= 300), use bounded multi-objective Knapsack DP
    if len(tracks) <= 300:
        return _knapsack_dp_duration(
            tracks=tracks,
            target_ms=target_ms,
            tol_ms=tol_ms,
            unit_ms=unit_ms,
            max_units=max_units
        )
    else:
        return _greedy_diversity_duration(
            tracks=tracks,
            target_ms=target_ms,
            tol_ms=tol_ms
        )


def _knapsack_dp_duration(
    tracks: List[Track],
    target_ms: int,
    tol_ms: int,
    unit_ms: int,
    max_units: int
) -> DurationOptimizationResult:
    """0/1 Knapsack dynamic programming with diversity and popularity weighting."""
    n = len(tracks)
    # Weight per track in discrete units (at least 1)
    weights = [max(1, t.duration_ms // unit_ms) for t in tracks]

    # Value function: base popularity score (50-100)
    values = [max(10, t.popularity) for t in tracks]

    # dp[w] = (max_val, list_of_indices)
    # We use a memory-efficient sparse table / dict
    dp: Dict[int, Tuple[float, List[int]]] = {0: (0.0, [])}

    for idx, (w, val, track) in enumerate(zip(weights, values, tracks)):
        # Decreasing update to enforce 0/1 constraint
        current_entries = list(dp.items())
        for prev_w, (prev_val, prev_indices) in current_entries:
            new_w = prev_w + w
            if new_w <= max_units:
                # Count prior tracks by this artist in prev_indices for diversity penalty
                artist_occurrences = sum(1 for i in prev_indices if tracks[i].primary_artist == track.primary_artist)
                diversity_multiplier = 1.0 / (1.0 + 0.35 * artist_occurrences)
                new_val = prev_val + (val * diversity_multiplier)

                if new_w not in dp or new_val > dp[new_w][0]:
                    dp[new_w] = (new_val, prev_indices + [idx])

    # Find the best capacity near target_ms
    target_units = target_ms // unit_ms
    best_indices: List[int] = []
    best_score = -float("inf")
    best_w = 0

    min_acceptable_units = max(0, (target_ms - tol_ms) // unit_ms)

    for w, (val, indices) in dp.items():
        # Score considers value + proximity penalty to exact target
        distance_penalty = abs(w - target_units) * 8.0
        score = val - distance_penalty
        if w >= min_acceptable_units and score > best_score:
            best_score = score
            best_indices = indices
            best_w = w

    # Fallback to closest weight if min_acceptable was not reached
    if not best_indices and dp:
        closest_w = min(dp.keys(), key=lambda w: abs(w - target_units))
        best_indices = dp[closest_w][1]

    selected_set = set(best_indices)
    selected_tracks = [tracks[i] for i in best_indices]
    excluded_tracks = [tracks[i] for i in range(n) if i not in selected_set]

    total_dur = sum(t.duration_ms for t in selected_tracks)
    delta_ms = total_dur - target_ms
    within_tol = abs(delta_ms) <= tol_ms

    sel_reasons = {}
    for t in selected_tracks:
        sel_reasons[t.id] = f"Selected by 0/1 Knapsack optimizer (duration {t.duration_formatted}, popularity {t.popularity})"

    ex_reasons = {}
    for t in excluded_tracks:
        ex_reasons[t.id] = (
            f"Excluded: Track duration ({t.duration_formatted}) did not fit in optimal {target_ms // 60000}-minute "
            f"knapsack combination or was deprioritized for artist diversity."
        )

    return DurationOptimizationResult(
        selected_tracks=selected_tracks,
        excluded_tracks=excluded_tracks,
        total_duration_ms=total_dur,
        target_duration_ms=target_ms,
        tolerance_ms=tol_ms,
        delta_ms=delta_ms,
        is_within_tolerance=within_tol,
        selection_reasons=sel_reasons,
        exclusion_reasons=ex_reasons
    )


def _greedy_diversity_duration(
    tracks: List[Track],
    target_ms: int,
    tol_ms: int
) -> DurationOptimizationResult:
    """Scalable greedy duration optimizer with artist diversity weighting for large libraries."""
    max_ms = target_ms + tol_ms
    min_ms = max(0, target_ms - tol_ms)

    # Sort with diversity-aware rank
    artist_seen: Dict[str, int] = {}
    selected: List[Track] = []
    excluded: List[Track] = []
    accumulated_ms = 0

    sel_reasons = {}
    ex_reasons = {}

    # Sort tracks by popularity initially
    candidates = sorted(tracks, key=lambda t: t.popularity, reverse=True)

    for t in candidates:
        if accumulated_ms + t.duration_ms <= max_ms:
            selected.append(t)
            accumulated_ms += t.duration_ms
            artist_seen[t.primary_artist] = artist_seen.get(t.primary_artist, 0) + 1
            sel_reasons[t.id] = f"Selected within runtime budget ({t.duration_formatted})"
            if accumulated_ms >= target_ms:
                # Target satisfied
                break
        else:
            excluded.append(t)
            ex_reasons[t.id] = f"Excluded: Adding track ({t.duration_formatted}) exceeds max allowable duration."

    for t in candidates:
        if t not in selected and t not in excluded:
            excluded.append(t)
            ex_reasons[t.id] = "Excluded: Runtime budget reached."

    delta_ms = accumulated_ms - target_ms
    within = min_ms <= accumulated_ms <= max_ms

    return DurationOptimizationResult(
        selected_tracks=selected,
        excluded_tracks=excluded,
        total_duration_ms=accumulated_ms,
        target_duration_ms=target_ms,
        tolerance_ms=tol_ms,
        delta_ms=delta_ms,
        is_within_tolerance=within,
        selection_reasons=sel_reasons,
        exclusion_reasons=ex_reasons
    )
