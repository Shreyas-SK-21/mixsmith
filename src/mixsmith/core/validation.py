"""Central independent constraint validation engine for Mixsmith.

Every constraint must be independently verified on the final playlist state,
ensuring that satisfaction is never falsely reported simply because candidates were found.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from mixsmith.core.models import ConstraintResult, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.validation")


@dataclass
class ValidationReport:
    """Consolidated independent audit report of all constraints on a playlist."""
    is_valid: bool
    results: list[ConstraintResult]
    total_violations: int
    summary: str

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == "warning" for r in self.results)

    @property
    def has_errors(self) -> bool:
        return any(r.severity == "error" for r in self.results)


class PlaylistValidator:
    """
    Independently verifies a finished playlist against requested curation constraints.
    Enforces strict distinction between hard constraints (which fail validation upon violation)
    and soft constraints (which record visible warnings without silent pass masquerading).
    """

    @staticmethod
    def validate_artist_spacing(
        tracks: list[Track],
        min_spacing: int,
        consider_all_artists: bool = True
    ) -> ConstraintResult:
        """
        Hard Constraint: Verifies that no two tracks within distance min_spacing share an artist.
        Reports all violations and the actual minimum gap observed.
        """
        if min_spacing <= 0 or len(tracks) <= 1:
            return ConstraintResult(
                name="artist_spacing",
                satisfied=True,
                details=f"Spacing constraint ({min_spacing}) trivially satisfied (playlist size {len(tracks)}).",
                severity="info"
            )

        def get_artists(t: Track) -> set[str]:
            raw_arts = t.artists if consider_all_artists and t.artists else ([t.primary_artist] if t.primary_artist else [])
            return {a.lower().strip() for a in raw_arts if a and a.strip()}

        violations = []
        min_gap_observed = float("inf")

        for i in range(len(tracks)):
            artists_i = get_artists(tracks[i])
            if not artists_i:
                continue
            window_end = min(len(tracks), i + min_spacing + 1)
            for j in range(i + 1, window_end):
                artists_j = get_artists(tracks[j])
                overlap = artists_i & artists_j
                if overlap:
                    gap = j - i - 1
                    min_gap_observed = min(min_gap_observed, gap)
                    violations.append((i, j, tracks[i].name, tracks[j].name, sorted(overlap), gap))

        if not violations:
            return ConstraintResult(
                name="artist_spacing",
                satisfied=True,
                details=f"All {len(tracks)} tracks satisfy >= {min_spacing} track spacing between repeated artists.",
                severity="info"
            )
        else:
            min_gap_str = str(min_gap_observed) if min_gap_observed != float("inf") else "0"
            violation_details = "; ".join(
                f"Track #{v[0] + 1} '{v[2]}' & #{v[1] + 1} '{v[3]}' (gap {v[5]}, artist {v[4]})"
                for v in violations[:10]
            )
            details = (
                f"{len(violations)} spacing violation(s) detected (requested min spacing: {min_spacing}, "
                f"actual minimum gap: {min_gap_str}). Details: {violation_details}."
            )
            return ConstraintResult(
                name="artist_spacing",
                satisfied=False,
                details=details,
                severity="error"  # Hard constraint violation
            )

    @staticmethod
    def validate_max_tracks_per_artist(
        tracks: list[Track],
        max_tracks: int | None,
        consider_all_artists: bool = True
    ) -> ConstraintResult:
        """
        Hard Constraint: Verifies no artist appears more than max_tracks times.
        Consistent with spacing, checks both primary and featured/co-artists when consider_all_artists=True.
        """
        if max_tracks is None or max_tracks <= 0:
            return ConstraintResult(
                name="max_tracks_per_artist",
                satisfied=True,
                details="No max tracks per artist limit configured.",
                severity="info"
            )

        counts: Counter = Counter()
        for t in tracks:
            raw_arts = t.artists if consider_all_artists and t.artists else ([t.primary_artist] if t.primary_artist else [])
            unique_arts = {a.strip() for a in raw_arts if a and a.strip()}
            for a in unique_arts:
                counts[a] += 1

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
                severity="error"  # Hard constraint violation
            )

    @staticmethod
    def validate_target_duration(
        tracks: list[Track],
        target_minutes: int | None,
        tolerance_minutes: int = 10
    ) -> ConstraintResult:
        """Soft Constraint: Verifies total duration is within target +/- tolerance."""
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
            severity="info" if satisfied else "warning"  # Soft constraint
        )

    @staticmethod
    def validate_genre_distribution(
        tracks: list[Track],
        target_quotas: dict[str, float] | None,
        tolerance_pct: float = 8.0
    ) -> ConstraintResult:
        """Soft Constraint: Verifies actual final genre distribution matches target quotas within tolerance."""
        if not target_quotas or not tracks:
            return ConstraintResult(
                name="genre_distribution",
                satisfied=True,
                details="No genre quotas specified.",
                severity="info"
            )

        total = len(tracks)
        actual_counts: dict[str, int] = defaultdict(int)
        for t in tracks:
            actual_counts[t.primary_genre.lower().strip()] += 1

        total_ratio = sum(target_quotas.values())
        discrepancies = []
        details_list = []

        for genre, requested_weight in target_quotas.items():
            expected_pct = (requested_weight / total_ratio) * 100.0 if total_ratio > 0 else 0.0
            actual_cnt = actual_counts.get(genre.lower().strip(), 0)
            actual_pct = (actual_cnt / total) * 100.0 if total > 0 else 0.0
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
    def validate_decade_distribution(
        tracks: list[Track],
        target_quotas: dict[str, float] | None,
        tolerance_pct: float = 8.0
    ) -> ConstraintResult:
        """Soft Constraint: Verifies actual final decade distribution matches target quotas within tolerance."""
        if not target_quotas or not tracks:
            return ConstraintResult(
                name="decade_distribution",
                satisfied=True,
                details="No decade quotas specified.",
                severity="info"
            )

        total = len(tracks)
        actual_counts: dict[str, int] = defaultdict(int)
        for t in tracks:
            dec = (t.decade or "").strip().lower()
            if dec:
                actual_counts[dec] += 1

        total_ratio = sum(target_quotas.values())
        discrepancies = []
        details_list = []

        for decade, requested_weight in target_quotas.items():
            expected_pct = (requested_weight / total_ratio) * 100.0 if total_ratio > 0 else 0.0
            actual_cnt = actual_counts.get(decade.lower().strip(), 0)
            actual_pct = (actual_cnt / total) * 100.0 if total > 0 else 0.0
            delta = abs(actual_pct - expected_pct)

            details_list.append(f"{decade}: {actual_pct:.1f}% (target: {expected_pct:.1f}%)")
            if delta > tolerance_pct:
                discrepancies.append((decade, actual_pct, expected_pct, delta))

        satisfied = len(discrepancies) == 0
        details = (
            f"Decade shares: {', '.join(details_list)}."
            + (f" Deviations exceeding +/-{tolerance_pct}%: {', '.join(d[0] for d in discrepancies)}." if discrepancies else "")
        )
        return ConstraintResult(
            name="decade_distribution",
            satisfied=satisfied,
            details=details,
            severity="info" if satisfied else "warning"
        )

    @staticmethod
    def validate_pinned_positions(
        tracks: list[Track],
        pinned_positions: dict[int, str] | None
    ) -> ConstraintResult:
        """Hard Constraint: Verifies pinned tracks occupy their exact requested positions."""
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
                (t.id and t.id.lower() == ident_clean) or
                (t.uri and t.uri.lower() == ident_clean) or
                (t.name and t.name.lower() == ident_clean)
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
            severity="info" if satisfied else "error"  # Hard constraint
        )

    @staticmethod
    def validate_track_preservation(
        original_pool: list[Track],
        final_tracks: list[Track]
    ) -> ConstraintResult:
        """
        Hard Constraint: Ensures all tracks in the final playlist strictly originate from
        the source pool and that no track is duplicated beyond its authorized occurrences.
        Handles missing track IDs by falling back to URI and track signature.
        """
        def track_key(t: Track) -> str:
            if t.id and t.id.strip():
                return f"id:{t.id.strip()}"
            if t.uri and t.uri.strip():
                return f"uri:{t.uri.strip()}"
            art_str = "-".join(sorted(a.lower().strip() for a in t.artists)) if t.artists else (t.primary_artist.lower().strip() if t.primary_artist else "unknown")
            return f"meta:{t.name.lower().strip()}:{art_str}"

        original_counts: Counter[str] = Counter(track_key(t) for t in original_pool)
        final_counts: Counter[str] = Counter(track_key(t) for t in final_tracks)

        foreign_keys = [k for k in final_counts if k not in original_counts]
        multiplied_keys = [k for k, cnt in final_counts.items() if k in original_counts and cnt > original_counts[k]]

        violations = []
        if foreign_keys:
            violations.append(f"{len(foreign_keys)} foreign track(s) not found in original pool: {foreign_keys[:5]}")
        if multiplied_keys:
            violations.append(f"{len(multiplied_keys)} track(s) repeated beyond authorized count: {multiplied_keys[:5]}")

        satisfied = len(violations) == 0
        details = (
            f"All {len(final_tracks)} track(s) originate strictly from authorized input pool with valid occurrence counts."
            if satisfied else f"Track preservation violations: {'; '.join(violations)}."
        )
        return ConstraintResult(
            name="track_preservation",
            satisfied=satisfied,
            details=details,
            severity="info" if satisfied else "error"  # Hard constraint
        )

    @classmethod
    def validate_playlist(
        cls,
        original_tracks: list[Track],
        final_tracks: list[Track],
        min_artist_spacing: int = 1,
        max_tracks_per_artist: int | None = None,
        target_duration_minutes: int | None = None,
        duration_tolerance_minutes: int = 10,
        genre_distribution: dict[str, float] | None = None,
        decade_distribution: dict[str, float] | None = None,
        pinned_positions: dict[int, str] | None = None,
        consider_all_artists: bool = True
    ) -> ValidationReport:
        """
        Executes full independent validation across all constraint dimensions.
        Distinguishes Hard constraints from Soft constraints.
        A validation warning is never reported as complete satisfaction.
        """
        results = [
            cls.validate_track_preservation(original_tracks, final_tracks),
            cls.validate_artist_spacing(final_tracks, min_artist_spacing, consider_all_artists=consider_all_artists),
            cls.validate_max_tracks_per_artist(final_tracks, max_tracks_per_artist, consider_all_artists=consider_all_artists),
            cls.validate_target_duration(final_tracks, target_duration_minutes, duration_tolerance_minutes),
            cls.validate_genre_distribution(final_tracks, genre_distribution),
            cls.validate_decade_distribution(final_tracks, decade_distribution),
            cls.validate_pinned_positions(final_tracks, pinned_positions)
        ]

        total_violations = sum(1 for r in results if not r.satisfied)
        hard_violations = [r for r in results if not r.satisfied and r.severity == "error"]
        soft_violations = [r for r in results if not r.satisfied and r.severity == "warning"]

        # Hard constraints dictate is_valid
        is_valid = len(hard_violations) == 0

        if not is_valid:
            summary = (
                f"Validation FAILED: {len(hard_violations)} hard constraint(s) unsatisfied "
                f"({', '.join(r.name for r in hard_violations)})."
            )
        elif soft_violations:
            summary = (
                f"Validation PASSED WITH WARNINGS: All hard constraints satisfied, but {len(soft_violations)} "
                f"soft constraint warning(s) detected: {', '.join(r.name for r in soft_violations)}."
            )
        else:
            summary = f"Validation PASSED: All {len(results)} constraint(s) fully satisfied."

        return ValidationReport(
            is_valid=is_valid,
            results=results,
            total_violations=total_violations,
            summary=summary
        )
