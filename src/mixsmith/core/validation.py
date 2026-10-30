"""Central independent constraint validation engine for Mixsmith.

Every constraint must be independently verified on the final playlist state,
ensuring that satisfaction is never falsely reported simply because candidates were found.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from mixsmith.core.models import ConstraintResult, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.validation")


@dataclass
class ValidationReport:
    """Consolidated independent audit report of all constraints on a playlist."""
    is_valid: bool
    results: List[ConstraintResult]
    total_violations: int
    summary: str

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == "warning" for r in self.results)

    @property
    def has_errors(self) -> bool:
        return any(r.severity == "error" for r in self.results)


class PlaylistValidator:
    """Independently verifies a finished playlist against requested curation constraints."""

    @staticmethod
    def validate_artist_spacing(
        tracks: List[Track],
        min_spacing: int,
        consider_all_artists: bool = True
    ) -> ConstraintResult:
        """Verifies that no two tracks within distance min_spacing share an artist."""
        if min_spacing <= 0 or len(tracks) <= 1:
            return ConstraintResult(
                name="artist_spacing",
                satisfied=True,
                details=f"Spacing constraint ({min_spacing}) trivially satisfied (playlist size {len(tracks)}).",
                severity="info"
            )

        def get_artists(t: Track) -> Set[str]:
            if consider_all_artists and t.artists:
                return {a.lower().strip() for a in t.artists if a.strip()}
            return {t.primary_artist.lower().strip()} if t.primary_artist else {"unknown"}

        violations = []
        min_gap_observed = float("inf")

        for i in range(len(tracks)):
            artists_i = get_artists(tracks[i])
            window_end = min(len(tracks), i + min_spacing + 1)
            for j in range(i + 1, window_end):
                artists_j = get_artists(tracks[j])
                overlap = artists_i & artists_j
                if overlap:
                    gap = j - i - 1
                    min_gap_observed = min(min_gap_observed, gap)
                    violations.append((i, j, tracks[i].name, tracks[j].name, list(overlap), gap))

        if not violations:
            return ConstraintResult(
                name="artist_spacing",
                satisfied=True,
                details=f"All {len(tracks)} tracks satisfy >= {min_spacing} track spacing between repeated artists.",
                severity="info"
            )
        else:
            first_v = violations[0]
            details = (
                f"{len(violations)} spacing violation(s) detected (requested min spacing: {min_spacing}). "
                f"Example: Track #{first_v[0] + 1} '{first_v[2]}' and Track #{first_v[1] + 1} '{first_v[3]}' "
                f"share artist(s) {first_v[4]} with spacing of {first_v[5]} tracks."
            )
            return ConstraintResult(
                name="artist_spacing",
                satisfied=False,
                details=details,
                severity="warning"
            )

    @staticmethod
    def validate_max_tracks_per_artist(
        tracks: List[Track],
        max_tracks: Optional[int],
        consider_all_artists: bool = False
    ) -> ConstraintResult:
        """Verifies no artist appears more than max_tracks times."""
        if max_tracks is None or max_tracks <= 0:
            return ConstraintResult(
                name="max_tracks_per_artist",
                satisfied=True,
                details="No max tracks per artist limit configured.",
                severity="info"
            )

        counts: Counter = Counter()
        for t in tracks:
            if consider_all_artists and t.artists:
                for a in set(t.artists):
                    counts[a.strip()] += 1
            else:
                counts[t.primary_artist or "Unknown"] += 1

        exceeded = [(artist, cnt) for artist, cnt in counts.items() if cnt > max_tracks]

        if not exceeded:
            return ConstraintResult(
                name="max_tracks_per_artist",
                satisfied=True,
                details=f"All artists are within the limit of max {max_tracks} track(s).",
                severity="info"
            )
        else:
            details = (
                f"{len(exceeded)} artist(s) exceed the limit of {max_tracks} tracks: "
                + ", ".join(f"{a} ({cnt})" for a, cnt in exceeded[:5])
            )
            return ConstraintResult(
                name="max_tracks_per_artist",
                satisfied=False,
                details=details,
                severity="error"
            )

    @staticmethod
    def validate_target_duration(
        tracks: List[Track],
        target_minutes: Optional[int],
        tolerance_minutes: int = 10
    ) -> ConstraintResult:
        """Verifies total duration is within target +/- tolerance."""
        if target_minutes is None:
            return ConstraintResult(
                name="target_duration",
                satisfied=True,
                details="No target duration specified.",
                severity="info"
            )

        total_ms = sum(t.duration_ms for t in tracks)
        total_mins = total_ms / 60000.0
        target_min_bound = max(0, target_minutes - tolerance_minutes)
        target_max_bound = target_minutes + tolerance_minutes

        satisfied = target_min_bound <= total_mins <= target_max_bound
        diff = total_mins - target_minutes

        details = (
            f"Total duration: {total_mins:.1f} min (Target: {target_minutes} +/- {tolerance_minutes} min, "
            f"Delta: {'+' if diff >= 0 else ''}{diff:.1f} min)."
        )
        return ConstraintResult(
            name="target_duration",
            satisfied=satisfied,
            details=details,
            severity="info" if satisfied else "warning"
        )

    @staticmethod
    def validate_genre_distribution(
        tracks: List[Track],
        target_quotas: Optional[Dict[str, float]],
        tolerance_pct: float = 8.0
    ) -> ConstraintResult:
        """Verifies actual final genre distribution matches target quotas within tolerance."""
        if not target_quotas or not tracks:
            return ConstraintResult(
                name="genre_distribution",
                satisfied=True,
                details="No genre quotas specified.",
                severity="info"
            )

        total = len(tracks)
        actual_counts: Dict[str, int] = defaultdict(int)
        for t in tracks:
            actual_counts[t.primary_genre.lower()] += 1

        total_ratio = sum(target_quotas.values())
        discrepancies = []
        details_list = []

        for genre, requested_weight in target_quotas.items():
            expected_pct = (requested_weight / total_ratio) * 100.0
            actual_cnt = actual_counts.get(genre.lower(), 0)
            actual_pct = (actual_cnt / total) * 100.0
            delta = abs(actual_pct - expected_pct)

            details_list.append(f"{genre}: {actual_pct:.1f}% (target: {expected_pct:.1f}%)")
            if delta > tolerance_pct:
                discrepancies.append((genre, actual_pct, expected_pct, delta))

        satisfied = len(discrepancies) == 0
        details = (
            f"Genre shares: {', '.join(details_list)}."
            + (f" Deviations exceeding +/-{tolerance_pct}%: {', '.join(d[0] for d in discrepancies)}." if discrepancies else "")
        )
        return ConstraintResult(
            name="genre_distribution",
            satisfied=satisfied,
            details=details,
            severity="info" if satisfied else "warning"
        )

    @staticmethod
    def validate_pinned_positions(
        tracks: List[Track],
        pinned_positions: Optional[Dict[int, str]]
    ) -> ConstraintResult:
        """Verifies pinned tracks occupy their exact requested positions."""
        if not pinned_positions:
            return ConstraintResult(
                name="pinned_positions",
                satisfied=True,
                details="No pinned track positions specified.",
                severity="info"
            )

        violations = []
        for pos, ident in pinned_positions.items():
            idx = pos if pos >= 0 else len(tracks) + pos
            if not (0 <= idx < len(tracks)):
                violations.append(f"Position {pos} out of range (length {len(tracks)})")
                continue

            t = tracks[idx]
            ident_clean = ident.lower().strip()
            matches = (
                t.id.lower() == ident_clean or
                t.uri.lower() == ident_clean or
                t.name.lower() == ident_clean
            )
            if not matches:
                violations.append(f"Position {idx}: expected '{ident}', found '{t.name}' ({t.id})")

        satisfied = len(violations) == 0
        details = (
            f"All {len(pinned_positions)} pinned positions verified."
            if satisfied else f"Pinned position violations: {'; '.join(violations)}."
        )
        return ConstraintResult(
            name="pinned_positions",
            satisfied=satisfied,
            details=details,
            severity="info" if satisfied else "error"
        )

    @staticmethod
    def validate_track_preservation(
        original_pool: List[Track],
        final_tracks: List[Track]
    ) -> ConstraintResult:
        """Ensures all tracks in final playlist strictly originate from the source pool."""
        original_ids = {t.id for t in original_pool if t.id}
        final_ids = [t.id for t in final_tracks if t.id]

        foreign = [t_id for t_id in final_ids if t_id not in original_ids]
        if not foreign:
            return ConstraintResult(
                name="track_preservation",
                satisfied=True,
                details=f"All {len(final_tracks)} tracks originate strictly from the authorized input library.",
                severity="info"
            )
        else:
            return ConstraintResult(
                name="track_preservation",
                satisfied=False,
                details=f"{len(foreign)} unverified or foreign track ID(s) found in playlist: {foreign[:5]}",
                severity="error"
            )

    @classmethod
    def validate_playlist(
        cls,
        original_tracks: List[Track],
        final_tracks: List[Track],
        min_artist_spacing: int = 1,
        max_tracks_per_artist: Optional[int] = None,
        target_duration_minutes: Optional[int] = None,
        duration_tolerance_minutes: int = 10,
        genre_distribution: Optional[Dict[str, float]] = None,
        pinned_positions: Optional[Dict[int, str]] = None
    ) -> ValidationReport:
        """Executes full independent validation across all constraint dimensions."""
        results = [
            cls.validate_track_preservation(original_tracks, final_tracks),
            cls.validate_artist_spacing(final_tracks, min_artist_spacing),
            cls.validate_max_tracks_per_artist(final_tracks, max_tracks_per_artist),
            cls.validate_target_duration(final_tracks, target_duration_minutes, duration_tolerance_minutes),
            cls.validate_genre_distribution(final_tracks, genre_distribution),
            cls.validate_pinned_positions(final_tracks, pinned_positions)
        ]

        total_violations = sum(1 for r in results if not r.satisfied)
        is_valid = not any(r.severity == "error" for r in results if not r.satisfied)

        summary = (
            f"Validation PASSED ({len(results) - total_violations}/{len(results)} constraints fully met)"
            if is_valid else f"Validation FAILED ({total_violations} constraint(s) unsatisfied)"
        )

        return ValidationReport(
            is_valid=is_valid,
            results=results,
            total_violations=total_violations,
            summary=summary
        )
