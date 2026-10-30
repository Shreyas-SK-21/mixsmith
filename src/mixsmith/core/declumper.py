"""Advanced Multi-Artist Aware De-clumping and Artist Spacing Engine."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from mixsmith.core.models import ConstraintResult, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.declumper")


class FeasibilityStatus(str, Enum):
    """Mathematical feasibility classification of an artist spacing constraint."""
    FEASIBLE = "FEASIBLE"
    NECESSARILY_INFEASIBLE = "NECESSARILY_INFEASIBLE"
    COLLABORATION_CONSTRAINED = "COLLABORATION_CONSTRAINED"
    CONDITIONALLY_TIGHT = "CONDITIONALLY_TIGHT"


@dataclass
class FeasibilityReport:
    """Report on the mathematical feasibility of requested artist spacing."""
    status: FeasibilityStatus
    is_feasible: bool
    requested_spacing: int
    max_achievable_spacing: int
    bottleneck_artists: List[Tuple[str, int, int]]  # (artist, count, min_tracks_needed)
    collaboration_density: float  # Percentage of tracks with multiple artists
    total_tracks: int
    explanation: str

    @property
    def summary(self) -> str:
        if self.is_feasible:
            return f"Feasible: spacing of {self.requested_spacing} tracks is mathematically sound."
        return (
            f"{self.status.value}: Spacing {self.requested_spacing} is impossible (max achievable: {self.max_achievable_spacing}). "
            f"Top bottleneck: {self.bottleneck_artists[0][0]} ({self.bottleneck_artists[0][1]}/{self.total_tracks} tracks)."
        )


@dataclass
class PlacementDecision:
    """Detailed record of why a track was placed at a specific position."""
    position: int
    track_id: str
    track_name: str
    artists: List[str]
    spacing_from_prev_appearance: Optional[int]
    reason: str
    constraint_relaxed: bool = False


def analyze_spacing_feasibility(
    tracks: List[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True
) -> FeasibilityReport:
    """
    Rigorously analyzes the mathematical feasibility of placing tracks with minimum spacing k.
    
    Distinguishes:
    1. Necessary individual pigeonhole condition:
       For any artist a with frequency C(a), placing them with spacing k requires:
       L_min(a) = (C(a) - 1) * (k + 1) + 1 <= N.
       If violated, spacing is NECESSARILY_INFEASIBLE.
    2. Collaboration hypergraph condition:
       When multiple artists appear on shared tracks, mutual exclusion sets intersect,
       creating additional constraints even when individual frequencies pass.
    """
    n = len(tracks)
    if n <= 1 or min_spacing <= 0:
        return FeasibilityReport(
            status=FeasibilityStatus.FEASIBLE,
            is_feasible=True,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_spacing,
            bottleneck_artists=[],
            collaboration_density=0.0,
            total_tracks=n,
            explanation="Playlist size <= 1 or spacing <= 0; trivially feasible."
        )

    # 1. Count artist occurrences and collaboration tracks
    artist_counts: Dict[str, int] = defaultdict(int)
    multi_artist_tracks = 0

    for t in tracks:
        all_arts = t.artists if consider_all_artists and t.artists else [t.primary_artist or "Unknown"]
        unique_arts = {a.lower().strip() for a in all_arts if a.strip()}
        if len(unique_arts) > 1:
            multi_artist_tracks += 1
        for a in unique_arts:
            artist_counts[a] += 1

    collab_density = (multi_artist_tracks / n) * 100.0 if n > 0 else 0.0

    # 2. Check individual necessary condition (Pigeonhole bound)
    bottlenecks: List[Tuple[str, int, int]] = []
    min_achievable = min_spacing

    for artist, count in artist_counts.items():
        if count <= 1:
            continue
        needed_len = (count - 1) * (min_spacing + 1) + 1
        if needed_len > n:
            achievable = max(0, (n - 1) // (count - 1) - 1)
            min_achievable = min(min_achievable, achievable)
            bottlenecks.append((artist, count, needed_len))

    bottlenecks.sort(key=lambda x: x[1], reverse=True)

    if bottlenecks:
        top_art, top_cnt, needed = bottlenecks[0]
        return FeasibilityReport(
            status=FeasibilityStatus.NECESSARILY_INFEASIBLE,
            is_feasible=False,
            requested_spacing=min_spacing,
            max_achievable_spacing=min_achievable,
            bottleneck_artists=bottlenecks,
            collaboration_density=round(collab_density, 1),
            total_tracks=n,
            explanation=(
                f"Requested spacing of {min_spacing} tracks violates the pigeonhole bound for '{top_art}' "
                f"({top_cnt} tracks requires at least {needed} total tracks, but playlist has {n}). "
                f"Maximum achievable spacing without collisions is {min_achievable}."
            )
        )

    # 3. Check pairwise collaboration density condition
    # If two artists appear together on tracks, their union count must also fit
    if consider_all_artists and collab_density > 25.0:
        pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for t in tracks:
            arts = sorted({a.lower().strip() for a in t.artists if a.strip()})
            for i in range(len(arts)):
                for j in range(i + 1, len(arts)):
                    pair_counts[(arts[i], arts[j])] += 1

        tight_collabs = [
            (f"{pair[0]} & {pair[1]}", cnt)
            for pair, cnt in pair_counts.items()
            if cnt > (n // (min_spacing + 1))
        ]
        if tight_collabs:
            return FeasibilityReport(
                status=FeasibilityStatus.COLLABORATION_CONSTRAINED,
                is_feasible=False,
                requested_spacing=min_spacing,
                max_achievable_spacing=max(0, min_spacing - 1),
                bottleneck_artists=[(tc[0], tc[1], tc[1] * (min_spacing + 1)) for tc in tight_collabs],
                collaboration_density=round(collab_density, 1),
                total_tracks=n,
                explanation=(
                    f"Frequent collaborations between {tight_collabs[0][0]} ({tight_collabs[0][1]} shared tracks) "
                    f"make requested spacing of {min_spacing} tracks tightly constrained."
                )
            )

    return FeasibilityReport(
        status=FeasibilityStatus.FEASIBLE,
        is_feasible=True,
        requested_spacing=min_spacing,
        max_achievable_spacing=min_spacing,
        bottleneck_artists=[],
        collaboration_density=round(collab_density, 1),
        total_tracks=n,
        explanation=f"Spacing of {min_spacing} track(s) is mathematically feasible across all {len(artist_counts)} artists."
    )


def declump_tracks(
    tracks: List[Track],
    min_spacing: int = 1,
    consider_all_artists: bool = True,
    return_details: bool = False
) -> Union[Tuple[List[Track], ConstraintResult], Tuple[List[Track], ConstraintResult, FeasibilityReport, List[PlacementDecision]]]:
    """
    Smart Artist Spacing (De-clumper).
    
    Returns:
    - If return_details=False: (result_tracks, constraint_result)
    - If return_details=True: (result_tracks, constraint_result, feasibility_report, placement_decisions)
    """
    if len(tracks) <= 2 or min_spacing <= 0:
        feas = analyze_spacing_feasibility(tracks, min_spacing, consider_all_artists)
        decisions = [
            PlacementDecision(
                position=i,
                track_id=t.id,
                track_name=t.name,
                artists=t.artists,
                spacing_from_prev_appearance=None,
                reason="Trivial placement: playlist has <= 2 tracks or spacing is 0."
            )
            for i, t in enumerate(tracks)
        ]
        res = ConstraintResult(
            name="artist_spacing",
            satisfied=True,
            details=f"All {len(tracks)} tracks retained with spacing >= {min_spacing}."
        )
        if return_details:
            return list(tracks), res, feas, decisions
        return list(tracks), res

    feasibility = analyze_spacing_feasibility(tracks, min_spacing, consider_all_artists)
    if not feasibility.is_feasible:
        logger.warning(feasibility.explanation)

    def get_track_artists(t: Track) -> Set[str]:
        if consider_all_artists and t.artists:
            return {a.lower().strip() for a in t.artists if a.strip()}
        return {t.primary_artist.lower().strip()} if t.primary_artist else {"unknown"}

    # Pre-cache artist sets and global frequencies for fast O(1) candidate evaluation
    track_artists_map: Dict[str, Set[str]] = {}
    remaining_artist_frequency: Dict[str, int] = defaultdict(int)
    for t in tracks:
        a_set = get_track_artists(t)
        track_artists_map[t.id] = a_set
        for a in a_set:
            remaining_artist_frequency[a] += 1

    result: List[Track] = []
    recent_history: deque[Set[str]] = deque(maxlen=min_spacing)
    last_placed_index: Dict[str, int] = {}
    placement_decisions: List[PlacementDecision] = []

    remaining_tracks = list(tracks)
    violations_count = 0

    while remaining_tracks:
        current_idx = len(result)
        recent_artists: Set[str] = set()
        for s in recent_history:
            recent_artists.update(s)

        valid_candidates: List[Tuple[int, Track, Set[str]]] = []
        conflicting_candidates: List[Tuple[int, Track, Set[str]]] = []

        for idx, t in enumerate(remaining_tracks):
            t_artists = track_artists_map[t.id]
            if not (t_artists & recent_artists):
                valid_candidates.append((idx, t, t_artists))
            else:
                conflicting_candidates.append((idx, t, t_artists))

        if valid_candidates:
            # Score: prioritize tracks whose artists have highest remaining global frequency
            def score_cand(item: Tuple[int, Track, Set[str]]) -> Tuple[int, int]:
                t_arts = item[2]
                freq_score = sum(remaining_artist_frequency[a] for a in t_arts)
                min_dist = min((current_idx - last_placed_index.get(a, -1000) for a in t_arts), default=1000)
                return (freq_score, min_dist)

            best_idx, best_track, t_artists = max(valid_candidates, key=score_cand)
            min_prev_gap = min((current_idx - last_placed_index[a] - 1 for a in t_artists if a in last_placed_index), default=None)
            decision_reason = (
                f"Selected from {len(valid_candidates)} valid candidate(s) with no artist overlap in the last {min_spacing} track(s). "
                f"Highest remaining frequency ({sum(remaining_artist_frequency[a] for a in t_artists)})."
            )
            relaxed = False
        else:
            # Graceful fallback: maximize the distance from the most recent appearance
            violations_count += 1

            def fallback_score(item: Tuple[int, Track, Set[str]]) -> int:
                t_arts = item[2]
                return min((current_idx - last_placed_index.get(a, -1) for a in t_arts), default=0)

            best_idx, best_track, t_artists = max(conflicting_candidates, key=fallback_score)
            min_prev_gap = min((current_idx - last_placed_index[a] - 1 for a in t_artists if a in last_placed_index), default=0)
            decision_reason = (
                f"Constraint relaxed: No candidate had 0 overlap with last {min_spacing} tracks. "
                f"Selected track with maximum distance from previous appearance ({min_prev_gap} slots)."
            )
            relaxed = True

        # O(1) removal from remaining_tracks
        remaining_tracks[best_idx] = remaining_tracks[-1]
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

    # Measure exact spacing outcome on the final permutation
    min_distance_found = float("inf")
    actual_violations = 0
    artist_positions: Dict[str, List[int]] = defaultdict(list)

    for idx, t in enumerate(result):
        for a in track_artists_map[t.id]:
            artist_positions[a].append(idx)

    for a, positions in artist_positions.items():
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                gap = positions[i + 1] - positions[i] - 1
                if gap < min_distance_found:
                    min_distance_found = gap
                if gap < min_spacing:
                    actual_violations += 1

    satisfied = actual_violations == 0
    if satisfied:
        details = f"All {len(result)} tracks arranged with >= {min_spacing} tracks between repeated artists."
        severity = "info"
    else:
        details = (
            f"Spacing relaxed with {actual_violations} violation(s) "
            f"(requested min spacing: {min_spacing}, minimum gap observed: {min_distance_found if min_distance_found != float('inf') else 0})."
        )
        severity = "warning"

    res = ConstraintResult(
        name="artist_spacing",
        satisfied=satisfied,
        details=details,
        severity=severity
    )

    if return_details:
        return result, res, feasibility, placement_decisions
    return result, res
