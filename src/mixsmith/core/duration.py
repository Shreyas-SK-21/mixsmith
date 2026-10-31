"""Playlist duration optimization engine using discrete 0/1 knapsack and multi-objective heuristics."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.duration")


@dataclass
class DurationOptimizationResult:
    """Outcome of playlist duration optimization."""
    selected_tracks: list[Track]
    excluded_tracks: list[Track]
    total_duration_ms: int
    target_duration_ms: int
    tolerance_ms: int
    delta_ms: int
    is_within_tolerance: bool
    selection_reasons: dict[str, str] = field(default_factory=dict)
    exclusion_reasons: dict[str, str] = field(default_factory=dict)


def optimize_playlist_duration(
    tracks: list[Track],
    target_minutes: int | None = None,
    tolerance_minutes: int = 10,
    time_unit_seconds: int = 5,
    target_duration_minutes: int | None = None
) -> DurationOptimizationResult:
    """
    Selects a subset of tracks to match target duration within [target - tol, target + tol],
    while maximizing a combined objective:
      1. Proximity to target duration.
      2. Artist diversity (penalizing redundant tracks from the same artist).
      3. Track quality/popularity.

    Guarantees:
      - Validates argument types and ranges.
      - Never allows time discretisation to exceed the actual runtime ceiling (verified in ms).
      - Actively compares candidate combinations and optimizes artist diversity.
    """
    effective_minutes = target_duration_minutes if target_duration_minutes is not None else target_minutes
    if effective_minutes is None or effective_minutes <= 0:
        raise ValueError(f"target_minutes must be a positive integer, got {effective_minutes}")
    if tolerance_minutes < 0:
        raise ValueError(f"tolerance_minutes cannot be negative, got {tolerance_minutes}")
    if time_unit_seconds <= 0:
        raise ValueError(f"time_unit_seconds must be a positive integer, got {time_unit_seconds}")

    target_ms = effective_minutes * 60 * 1000
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
    max_units = max_acceptable_ms // unit_ms

    # If track count <= 250, use bounded multi-objective Knapsack DP
    if len(tracks) <= 250:
        return _knapsack_dp_duration(
            tracks=tracks,
            target_ms=target_ms,
            tol_ms=tol_ms,
            unit_ms=unit_ms,
            max_units=max_units,
            max_acceptable_ms=max_acceptable_ms
        )
    else:
        return _diversity_aware_large_duration(
            tracks=tracks,
            target_ms=target_ms,
            tol_ms=tol_ms,
            unit_ms=unit_ms,
            max_acceptable_ms=max_acceptable_ms
        )


def _knapsack_dp_duration(
    tracks: list[Track],
    target_ms: int,
    tol_ms: int,
    unit_ms: int,
    max_units: int,
    max_acceptable_ms: int
) -> DurationOptimizationResult:
    """
    0/1 Knapsack dynamic programming tracking actual milliseconds in state
    to prevent discretisation ceiling overrun.
    """
    # Scaled discrete weights (at least 1)
    weights = [max(1, math.ceil(t.duration_ms / unit_ms)) for t in tracks]
    values = [max(10, t.popularity if t.popularity is not None else 50) for t in tracks]

    # dp[w] = (max_val, list_of_indices, actual_total_ms)
    dp: dict[int, tuple[float, list[int], int]] = {0: (0.0, [], 0)}

    for idx, (w, val, track) in enumerate(zip(weights, values, tracks)):
        current_entries = list(dp.items())
        t_dur = track.duration_ms
        primary_artist = (track.primary_artist or "Unknown").lower()

        for prev_w, (prev_val, prev_indices, prev_ms) in current_entries:
            new_w = prev_w + w
            new_ms = prev_ms + t_dur

            # Strict millisecond verification: NEVER exceed max_acceptable_ms
            if new_w <= max_units and new_ms <= max_acceptable_ms:
                artist_occurrences = sum(
                    1 for i in prev_indices if (tracks[i].primary_artist or "Unknown").lower() == primary_artist
                )
                diversity_multiplier = 1.0 / (1.0 + 0.40 * artist_occurrences)
                new_val = prev_val + (val * diversity_multiplier)

                if new_w not in dp or new_val > dp[new_w][0]:
                    dp[new_w] = (new_val, prev_indices + [idx], new_ms)

    # Find the best capacity near target_ms
    min_acceptable_ms = max(0, target_ms - tol_ms)
    best_indices: list[int] = []
    best_score = -float("inf")

    for _w, (dp_val, indices, actual_ms) in dp.items():
        if actual_ms > max_acceptable_ms:
            continue
        # Distance penalty calculated in actual seconds, strongly penalizing drift from target
        distance_penalty = (abs(actual_ms - target_ms) / 1000.0) * 1.5
        score = dp_val - distance_penalty
        if actual_ms >= min_acceptable_ms and score > best_score:
            best_score = score
            best_indices = indices

    # Fallback to closest millisecond state if min_acceptable was not reached
    if not best_indices and dp:
        valid_entries = [item for item in dp.values() if item[2] <= max_acceptable_ms]
        if valid_entries:
            best_item = min(valid_entries, key=lambda item: abs(item[2] - target_ms))
            best_indices = best_item[1]

    # Verify actual millisecond total
    selected_tracks = [tracks[i] for i in best_indices]
    actual_total_ms = sum(t.duration_ms for t in selected_tracks)

    # Guard against any edge-case discretisation overshoot
    while selected_tracks and actual_total_ms > max_acceptable_ms:
        # Drop the track with least value/popularity to respect ceiling
        worst_track = min(selected_tracks, key=lambda t: t.popularity if t.popularity is not None else 50)
        selected_tracks.remove(worst_track)
        actual_total_ms = sum(t.duration_ms for t in selected_tracks)

    selected_set = {id(t) for t in selected_tracks}
    excluded_tracks = [t for t in tracks if id(t) not in selected_set]

    delta_ms = actual_total_ms - target_ms
    within_tol = abs(delta_ms) <= tol_ms and actual_total_ms <= max_acceptable_ms

    sel_reasons = {
        t.id: f"Selected by 0/1 Knapsack optimizer (duration {t.duration_formatted}, popularity {t.popularity if t.popularity is not None else 'N/A'})"
        for t in selected_tracks
    }
    ex_reasons = {
        t.id: f"Excluded: Track duration ({t.duration_formatted}) did not fit in optimal knapsack combination."
        for t in excluded_tracks
    }

    return DurationOptimizationResult(
        selected_tracks=selected_tracks,
        excluded_tracks=excluded_tracks,
        total_duration_ms=actual_total_ms,
        target_duration_ms=target_ms,
        tolerance_ms=tol_ms,
        delta_ms=delta_ms,
        is_within_tolerance=within_tol,
        selection_reasons=sel_reasons,
        exclusion_reasons=ex_reasons
    )


def _diversity_aware_large_duration(
    tracks: list[Track],
    target_ms: int,
    tol_ms: int,
    unit_ms: int,
    max_acceptable_ms: int
) -> DurationOptimizationResult:
    """
    Scalable multi-combination optimizer for large libraries.
    Ranks tracks by diversity-penalized score, compares multiple candidate combinations,
    and runs sub-knapsack optimization on the top candidate pool.
    """
    # 1. Calculate overall artist frequencies in input library
    artist_freq = Counter((t.primary_artist or "Unknown").lower() for t in tracks)

    # 2. Score tracks with diversity bonus (fewer tracks by same artist = higher priority)
    scored_candidates = []
    for t in tracks:
        a = (t.primary_artist or "Unknown").lower()
        # Diversity score: rewards moderate popularity and penalizes artist saturation
        pop_val = t.popularity if t.popularity is not None else 50
        div_score = (pop_val + 20) / math.sqrt(artist_freq[a])
        scored_candidates.append((div_score, t))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    # Filter to top 150 diverse candidate tracks and run knapsack DP
    top_candidates = [item[1] for item in scored_candidates[:150]]
    max_units = max_acceptable_ms // unit_ms

    dp_result = _knapsack_dp_duration(
        tracks=top_candidates,
        target_ms=target_ms,
        tol_ms=tol_ms,
        unit_ms=unit_ms,
        max_units=max_units,
        max_acceptable_ms=max_acceptable_ms
    )

    # Build full exclusion map including tracks outside the top 150
    selected_set = {id(t) for t in dp_result.selected_tracks}
    all_excluded = [t for t in tracks if id(t) not in selected_set]
    all_ex_reasons = dict(dp_result.exclusion_reasons)
    for t in all_excluded:
        if t.id not in all_ex_reasons:
            all_ex_reasons[t.id] = "Excluded: Deprioritized for artist diversity in large library selection."

    return DurationOptimizationResult(
        selected_tracks=dp_result.selected_tracks,
        excluded_tracks=all_excluded,
        total_duration_ms=dp_result.total_duration_ms,
        target_duration_ms=target_ms,
        tolerance_ms=tol_ms,
        delta_ms=dp_result.delta_ms,
        is_within_tolerance=dp_result.is_within_tolerance,
        selection_reasons=dp_result.selection_reasons,
        exclusion_reasons=all_ex_reasons
    )
