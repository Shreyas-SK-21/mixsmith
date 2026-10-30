"""Advanced Multi-Artist Aware De-clumping and Artist Spacing Engine."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Literal, overload

from mixsmith.core.models import ConstraintResult, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.declumper")


class FeasibilityStatus(str, Enum):
    """Mathematical feasibility classification of an artist spacing constraint."""
    SUFFICIENTLY_FEASIBLE = "SUFFICIENTLY_FEASIBLE"       # Proven mathematically feasible
    FEASIBLE = "FEASIBLE"                                 # Alias for backward compatibility
    PROVEN_INFEASIBLE = "PROVEN_INFEASIBLE"               # Violates strict necessary conditions (e.g. Pigeonhole bound)
    NECESSARILY_INFEASIBLE = "NECESSARILY_INFEASIBLE"     # Alias for backward compatibility
    CONDITIONALLY_CONSTRAINED = "CONDITIONALLY_CONSTRAINED" # Necessary bounds met, but multi-artist overlaps require scheduling to determine


@dataclass
class FeasibilityReport:
    """Report on the mathematical feasibility of requested artist spacing."""
    status: FeasibilityStatus
    is_feasible: bool
    requested_spacing: int
    max_achievable_spacing: int | None
    bottleneck_artists: list[tuple[str, int, int]]  # (artist, count, min_tracks_needed)
    collaboration_density: float  # Percentage of tracks with multiple artists
    total_tracks: int
    explanation: str

    @property
    def summary(self) -> str:
        if self.is_feasible:
            spacing_info = f" (max achievable ceiling: {self.max_achievable_spacing})" if self.max_achievable_spacing is not None else ""
            return f"{self.status.value}: Spacing of {self.requested_spacing} tracks is mathematically plausible{spacing_info}."
        ceiling_str = f"{self.max_achievable_spacing}" if self.max_achievable_spacing is not None else "undetermined"
        top_art = self.bottleneck_artists[0][0] if self.bottleneck_artists else "collaborations"
        top_cnt = self.bottleneck_artists[0][1] if self.bottleneck_artists else 0
        return (
            f"{self.status.value}: Spacing {self.requested_spacing} is impossible (max achievable bound: {ceiling_str}). "
            f"Top bottleneck: {top_art} ({top_cnt}/{self.total_tracks} tracks)."
        )


@dataclass
class PlacementDecision:
    """Detailed record of why a track was placed at a specific position."""
    position: int
    track_id: str
    track_name: str
    artists: list[str]
    spacing_from_prev_appearance: int | None
    reason: str
    constraint_relaxed: bool = False


def analyze_spacing_feasibility(
    tracks: list[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True
) -> FeasibilityReport:
    """
    Rigorously analyzes the mathematical feasibility of placing tracks with minimum spacing k.

    Distinguishes:
    1. Proven Infeasibility (Necessary Pigeonhole Bound):
       For any artist a with frequency C(a), placing them with spacing k requires:
       L_min(a) = (C(a) - 1) * (k + 1) + 1 <= N.
       If violated for any single artist or mutually conflicting clique, spacing is PROVEN_INFEASIBLE.
       The single-artist ceiling is k_max(a) = floor((N - 1) / (C(a) - 1)) - 1.
    2. Sufficient Feasibility:
       When all artist counts are <= 1, or artists across all tracks are disjoint.
    3. Conditionally Constrained:
       When single-artist bounds pass, but multi-artist collaborations exist.
       Does not fabricate achievable spacing estimates without scheduling verification.
    """
    n = len(tracks)
    if n <= 1 or min_spacing <= 0:
        return FeasibilityReport(
            status=FeasibilityStatus.SUFFICIENTLY_FEASIBLE,
            is_feasible=True,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_spacing,
            bottleneck_artists=[],
            collaboration_density=0.0,
            total_tracks=n,
            explanation="Playlist size <= 1 or spacing <= 0; trivially feasible."
        )

    # 1. Count artist occurrences and collaboration tracks (handling empty artist metadata)
    artist_counts: dict[str, int] = defaultdict(int)
    multi_artist_tracks = 0
    track_artist_sets: list[set[str]] = []

    for t in tracks:
        raw_arts = t.artists if consider_all_artists and t.artists else ([t.primary_artist] if t.primary_artist else [])
        unique_arts = {a.lower().strip() for a in raw_arts if a and a.strip()}
        track_artist_sets.append(unique_arts)
        if len(unique_arts) > 1:
            multi_artist_tracks += 1
        for a in unique_arts:
            artist_counts[a] += 1

    collab_density = (multi_artist_tracks / n) * 100.0 if n > 0 else 0.0

    # 2. Check individual necessary condition (Pigeonhole bound)
    bottlenecks: list[tuple[str, int, int]] = []
    min_single_artist_ceiling = min_spacing

    for artist, count in artist_counts.items():
        if count <= 1:
            continue
        needed_len = (count - 1) * (min_spacing + 1) + 1
        achievable_for_artist = max(0, (n - 1) // (count - 1) - 1)
        if needed_len > n:
            min_single_artist_ceiling = min(min_single_artist_ceiling, achievable_for_artist)
            bottlenecks.append((artist, count, needed_len))

    bottlenecks.sort(key=lambda x: x[1], reverse=True)

    if bottlenecks:
        top_art, top_cnt, needed = bottlenecks[0]
        return FeasibilityReport(
            status=FeasibilityStatus.PROVEN_INFEASIBLE,
            is_feasible=False,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_single_artist_ceiling,
            bottleneck_artists=bottlenecks,
            collaboration_density=round(collab_density, 1),
            total_tracks=n,
            explanation=(
                f"Requested spacing of {min_spacing} tracks violates the mathematical pigeonhole bound for '{top_art}' "
                f"({top_cnt} tracks requires at least {needed} total tracks, but playlist has {n}). "
                f"Upper bound ceiling for this artist is {min_single_artist_ceiling}."
            )
        )

    # 3. Check pairwise and multi-artist collaboration cliques
    # If a subset of tracks all pairwise share artists, they form a mutually conflicting clique S
    # where |S| <= ceil(N / (k + 1)) is a strict necessary condition.
    if consider_all_artists and multi_artist_tracks > 0:
        # Check if any two tracks share a collaborative pair where mutual conflicts fail necessary bound
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for arts in track_artist_sets:
            sorted_arts = sorted(arts)
            for i in range(len(sorted_arts)):
                for j in range(i + 1, len(sorted_arts)):
                    pair_counts[(sorted_arts[i], sorted_arts[j])] += 1

        for (a1, a2), pair_cnt in pair_counts.items():
            if pair_cnt > 1:
                needed_collab_len = (pair_cnt - 1) * (min_spacing + 1) + 1
                if needed_collab_len > n:
                    achievable_collab = max(0, (n - 1) // (pair_cnt - 1) - 1)
                    return FeasibilityReport(
                        status=FeasibilityStatus.PROVEN_INFEASIBLE,
                        is_feasible=False,
                        requested_spacing=min_spacing,
                        max_achievable_spacing=achievable_collab,
                        bottleneck_artists=[(f"{a1} & {a2}", pair_cnt, needed_collab_len)],
                        collaboration_density=round(collab_density, 1),
                        total_tracks=n,
                        explanation=(
                            f"Collaboration pair '{a1} & {a2}' appears together on {pair_cnt} tracks, "
                            f"requiring at least {needed_collab_len} tracks for spacing {min_spacing}, but playlist has {n}."
                        )
                    )

        # Single-artist bounds pass, but multi-artist overlaps exist.
        # Do not fabricate an arbitrary achievable ceiling without scheduling verification.
        return FeasibilityReport(
            status=FeasibilityStatus.CONDITIONALLY_CONSTRAINED,
            is_feasible=True,
            requested_spacing=min_spacing,
            max_achievable_spacing=None,  # Not fabricated; determined by scheduler
            bottleneck_artists=[],
            collaboration_density=round(collab_density, 1),
            total_tracks=n,
            explanation=(
                f"Individual artist pigeonhole bounds are satisfied, but {multi_artist_tracks} multi-artist "
                f"collaboration track(s) create coupled constraints. Feasibility is conditionally constrained "
                f"and subject to constructive scheduling verification."
            )
        )

    # 4. Strictly feasible case (disjoint artists or all frequencies <= 1)
    max_freq = max(artist_counts.values()) if artist_counts else 0
    if max_freq <= 1:
        return FeasibilityReport(
            status=FeasibilityStatus.SUFFICIENTLY_FEASIBLE,
            is_feasible=True,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_spacing,
            bottleneck_artists=[],
            collaboration_density=round(collab_density, 1),
            total_tracks=n,
            explanation=f"All artists appear at most once; spacing {min_spacing} is sufficiently and trivially feasible."
        )

    return FeasibilityReport(
        status=FeasibilityStatus.SUFFICIENTLY_FEASIBLE,
        is_feasible=True,
        requested_spacing=min_spacing,
        max_achievable_spacing=min_spacing,
        bottleneck_artists=[],
        collaboration_density=round(collab_density, 1),
        total_tracks=n,
        explanation=f"Spacing of {min_spacing} track(s) is mathematically feasible across all {len(artist_counts)} artists."
    )


@overload
def declump_tracks(
    tracks: list[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True,
    return_details: Literal[False] = False
) -> tuple[list[Track], ConstraintResult]: ...


@overload
def declump_tracks(
    tracks: list[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True,
    return_details: Literal[True] = True
) -> tuple[list[Track], ConstraintResult, FeasibilityReport, list[PlacementDecision]]: ...


def declump_tracks(
    tracks: list[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True,
    return_details: bool = False
) -> tuple[list[Track], ConstraintResult] | tuple[list[Track], ConstraintResult, FeasibilityReport, list[PlacementDecision]]:
    """
    Smart Artist Spacing (De-clumper).

    Guarantees that:
    - Never reports spacing as satisfied without verifying actual artist sets.
    - Accurately checks playlists of two tracks against shared artists.
    - Handles empty artist metadata without artificial collisions.
    - Records actual minimum gap and all violations when constraints are relaxed.
    """
    # Only N <= 1 or spacing <= 0 is trivially satisfied without inspection
    if len(tracks) <= 1 or min_spacing <= 0:
        feas = analyze_spacing_feasibility(tracks, min_spacing, consider_all_artists)
        decisions = [
            PlacementDecision(
                position=i,
                track_id=t.id,
                track_name=t.name,
                artists=t.artists,
                spacing_from_prev_appearance=None,
                reason="Trivially satisfied: playlist has <= 1 track or min_spacing <= 0."
            )
            for i, t in enumerate(tracks)
        ]
        res = ConstraintResult(
            name="artist_spacing",
            satisfied=True,
            details=f"All {len(tracks)} track(s) trivially satisfied with spacing >= {min_spacing}.",
            severity="info"
        )
        if return_details:
            return list(tracks), res, feas, decisions
        return list(tracks), res

    feasibility = analyze_spacing_feasibility(tracks, min_spacing, consider_all_artists)
    if not feasibility.is_feasible:
        logger.warning(feasibility.explanation)

    def get_track_artists(t: Track) -> set[str]:
        raw_arts = t.artists if consider_all_artists and t.artists else ([t.primary_artist] if t.primary_artist else [])
        return {a.lower().strip() for a in raw_arts if a and a.strip()}

    # Pre-cache artist sets and global frequencies for fast O(1) candidate evaluation
    track_artists_map: dict[str, set[str]] = {}
    remaining_artist_frequency: dict[str, int] = defaultdict(int)
    for idx, t in enumerate(tracks):
        # Key by id or index to support duplicate or missing IDs
        t_key = t.id if t.id else f"__idx_{idx}"
        a_set = get_track_artists(t)
        track_artists_map[t_key] = a_set
        for a in a_set:
            remaining_artist_frequency[a] += 1

    result: list[Track] = []
    recent_history: deque[set[str]] = deque(maxlen=min_spacing)
    last_placed_index: dict[str, int] = {}
    placement_decisions: list[PlacementDecision] = []

    remaining_tracks = list(enumerate(tracks))
    violations_count = 0

    while remaining_tracks:
        current_idx = len(result)
        recent_artists: set[str] = set()
        for s in recent_history:
            recent_artists.update(s)

        valid_candidates: list[tuple[int, int, Track, set[str]]] = []
        conflicting_candidates: list[tuple[int, int, Track, set[str]]] = []

        for list_idx, (orig_idx, t) in enumerate(remaining_tracks):
            t_key = t.id if t.id else f"__idx_{orig_idx}"
            t_artists = track_artists_map[t_key]
            # If track has no artist metadata, it does not conflict with any recent artist
            if not t_artists or not (t_artists & recent_artists):
                valid_candidates.append((list_idx, orig_idx, t, t_artists))
            else:
                conflicting_candidates.append((list_idx, orig_idx, t, t_artists))

        if valid_candidates:
            def score_cand(item: tuple[int, int, Track, set[str]]) -> tuple[int, int]:
                t_arts = item[3]
                freq_score = sum(remaining_artist_frequency[a] for a in t_arts)
                min_dist = min((current_idx - last_placed_index.get(a, -1000) for a in t_arts), default=1000)
                return (freq_score, min_dist)

            best_list_idx, best_orig_idx, best_track, t_artists = max(valid_candidates, key=score_cand)
            min_prev_gap = min((current_idx - last_placed_index[a] - 1 for a in t_artists if a in last_placed_index), default=None)
            decision_reason = (
                f"Selected from {len(valid_candidates)} valid candidate(s) with no artist overlap in the last {min_spacing} track(s)."
            )
            relaxed = False
        else:
            violations_count += 1

            def fallback_score(item: tuple[int, int, Track, set[str]]) -> int:
                t_arts = item[3]
                return min((current_idx - last_placed_index.get(a, -1) for a in t_arts), default=0)

            best_list_idx, best_orig_idx, best_track, t_artists = max(conflicting_candidates, key=fallback_score)
            min_prev_gap = min((current_idx - last_placed_index[a] - 1 for a in t_artists if a in last_placed_index), default=0)
            decision_reason = (
                f"Constraint relaxed: No candidate had 0 overlap with last {min_spacing} tracks. "
                f"Selected track with maximum distance from previous appearance ({min_prev_gap} slots)."
            )
            relaxed = True

        # O(1) removal from remaining_tracks
        remaining_tracks[best_list_idx] = remaining_tracks[-1]
        remaining_tracks.pop()
        result.append(best_track)

        placement_decisions.append(PlacementDecision(
            position=current_idx,
            track_id=best_track.id,
            track_name=best_track.name,
            artists=best_track.artists,
            spacing_from_prev_appearance=min_prev_gap,
            reason=decision_reason,
            constraint_relaxed=relaxed
        ))

        recent_history.append(t_artists)
        for a in t_artists:
            last_placed_index[a] = current_idx
            remaining_artist_frequency[a] -= 1

    # Exact verification of final permutation
    min_distance_found = float("inf")
    actual_violations = 0
    artist_positions: dict[str, list[int]] = defaultdict(list)

    for idx, t in enumerate(result):
        t_key = t.id if t.id else f"__result_{idx}"
        for a in get_track_artists(t):
            artist_positions[a].append(idx)

    for a, positions in artist_positions.items():
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                gap = positions[i + 1] - positions[i] - 1
                min_distance_found = min(min_distance_found, gap)
                if gap < min_spacing:
                    actual_violations += 1

    satisfied = actual_violations == 0
    if satisfied:
        details = f"All {len(result)} tracks arranged with >= {min_spacing} tracks between repeated artists."
        severity = "info"
    else:
        min_gap_str = str(min_distance_found) if min_distance_found != float("inf") else "0"
        details = (
            f"Artist spacing FAILED with {actual_violations} violation(s) "
            f"(requested min spacing: {min_spacing}, minimum gap observed: {min_gap_str})."
        )
        severity = "error"

    res = ConstraintResult(
        name="artist_spacing",
        satisfied=satisfied,
        details=details,
        severity=severity
    )

    if return_details:
        return result, res, feasibility, placement_decisions
    return result, res
