"""Multi-constraint playlist sequencing and curation engine with full explainability."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from mixsmith.core.declumper import PlacementDecision, declump_tracks
from mixsmith.core.duration import optimize_playlist_duration
from mixsmith.core.exceptions import InfeasibleConstraintError
from mixsmith.core.explanation import CurationExplanation, TrackCurationDecision
from mixsmith.core.journeys import (
    compute_track_energy,
    sequence_artist_evolution,
    sequence_decade_journey,
    sequence_energy_progression,
    sequence_genre_journey,
    sequence_nostalgia_mode,
)
from mixsmith.core.models import CurationPlan, Track
from mixsmith.core.quotas import allocate_genre_quotas
from mixsmith.core.validation import PlaylistValidator
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.sequencing")


@dataclass
class CurationConstraints:
    """Specification of all constraints for curating and sequencing a playlist."""
    min_artist_spacing: int = 1
    max_tracks_per_artist: int | None = None
    target_duration_minutes: int | None = None
    duration_tolerance_minutes: int = 10
    min_duration_minutes: int | None = None
    max_duration_minutes: int | None = None
    genre_distribution: dict[str, float] | None = None
    decade_distribution: dict[str, float] | None = None
    pinned_positions: dict[int, str] | None = None  # index -> track_id / uri
    popularity_bias: str | None = None  # "hits", "gems", "balanced"
    sort_mode: str | None = None  # "declump", "chronological", "decade", "genre", "nostalgia"
    energy_progression: str | None = None  # "mellow_to_energetic", "energetic_to_mellow"
    preserve_order: bool = False


class ConstraintSequencingEngine:
    """Engine that curates and sequences playlists satisfying multiple simultaneous constraints."""

    def curate(
        self,
        tracks: list[Track],
        constraints: CurationConstraints | None = None,
        playlist_name: str = "Curated Playlist"
    ) -> CurationPlan:
        """Executes multi-constraint curation, independent validation, and compiles a CurationExplanation."""
        constraints = constraints or CurationConstraints()
        initial_count = len(tracks)
        current = list(tracks)

        # Pre-flight duration bounds check
        if constraints.min_duration_minutes is not None and constraints.max_duration_minutes is not None:
            if constraints.min_duration_minutes > constraints.max_duration_minutes:
                raise InfeasibleConstraintError(
                    f"min_duration_minutes ({constraints.min_duration_minutes}) cannot exceed max_duration_minutes ({constraints.max_duration_minutes})",
                    constraint="duration_bounds"
                )
        if constraints.min_duration_minutes is not None:
            total_avail_ms = sum(t.duration_ms for t in tracks)
            if total_avail_ms < constraints.min_duration_minutes * 60000:
                raise InfeasibleConstraintError(
                    f"Available track pool total duration ({total_avail_ms / 60000:.1f}m) is less than required minimum ({constraints.min_duration_minutes}m)",
                    constraint="min_duration"
                )

        # Decision tracking dictionary for explainability: track_id -> TrackCurationDecision
        decisions: dict[str, TrackCurationDecision] = {
            t.id: TrackCurationDecision(
                track_id=t.id,
                track_name=t.name,
                artists=t.artists,
                selected=True,
                selection_reasons=["Included in candidate pool"],
                constraints_applied=[]
            )
            for t in tracks
        }

        # 1. Enforce max tracks per artist
        if constraints.max_tracks_per_artist is not None and constraints.max_tracks_per_artist > 0:
            limit = constraints.max_tracks_per_artist
            artist_buckets: dict[str, list[Track]] = defaultdict(list)
            for t in current:
                a_key = t.primary_artist.lower().strip() if t.primary_artist else "unknown"
                artist_buckets[a_key].append(t)

            pruned: list[Track] = []
            for a_key, a_tracks in artist_buckets.items():
                if len(a_tracks) > limit:
                    # Keep tracks with highest popularity (handling None popularity gracefully)
                    sorted_a = sorted(a_tracks, key=lambda t: (t.popularity if t.popularity is not None else 50), reverse=True)
                    retained = sorted_a[:limit]
                    pruned.extend(retained)
                    for t in retained:
                        pop_desc = f"popularity {t.popularity}" if t.popularity is not None else "unrated"
                        decisions[t.id].selection_reasons.append(f"Retained within {t.primary_artist} max {limit} quota ({pop_desc})")
                        decisions[t.id].constraints_applied.append("max_tracks_per_artist")
                    for t in sorted_a[limit:]:
                        decisions[t.id].selected = False
                        decisions[t.id].exclusion_reasons.append(
                            f"Excluded: Artist '{t.primary_artist}' reached max limit of {limit} tracks."
                        )
                        decisions[t.id].constraints_applied.append("max_tracks_per_artist")
                else:
                    pruned.extend(a_tracks)
                    for t in a_tracks:
                        decisions[t.id].constraints_applied.append("max_tracks_per_artist")

            current = pruned

        # 2. Genre distribution quota using Largest Remainder (Hamilton-Hare method)
        if constraints.genre_distribution:
            quota_res = allocate_genre_quotas(current, constraints.genre_distribution)
            if quota_res.selected_tracks:
                current = quota_res.selected_tracks
                for t in current:
                    if t.id in quota_res.selection_reasons:
                        decisions[t.id].selection_reasons.append(quota_res.selection_reasons[t.id])
                        decisions[t.id].constraints_applied.append("genre_distribution")
                for t_id, reason in quota_res.exclusion_reasons.items():
                    if t_id in decisions and decisions[t_id].selected:
                        decisions[t_id].selected = False
                        decisions[t_id].exclusion_reasons.append(reason)
                        decisions[t_id].constraints_applied.append("genre_distribution")

        # 3. Target playlist duration using 0/1 Knapsack optimization
        if constraints.target_duration_minutes is not None:
            dur_res = optimize_playlist_duration(
                tracks=current,
                target_minutes=constraints.target_duration_minutes,
                tolerance_minutes=constraints.duration_tolerance_minutes
            )
            if dur_res.selected_tracks:
                current = dur_res.selected_tracks
                for t in current:
                    if t.id in dur_res.selection_reasons:
                        decisions[t.id].selection_reasons.append(dur_res.selection_reasons[t.id])
                        decisions[t.id].constraints_applied.append("target_duration")
                for t in dur_res.excluded_tracks:
                    if t.id in decisions and decisions[t.id].selected:
                        decisions[t.id].selected = False
                        if t.id in dur_res.exclusion_reasons:
                            decisions[t.id].exclusion_reasons.append(dur_res.exclusion_reasons[t.id])
                        decisions[t.id].constraints_applied.append("target_duration")

        # 4. Sorting & Journey Sequencing
        if constraints.energy_progression:
            current = sequence_energy_progression(current, direction=constraints.energy_progression)
            for t in current:
                en_score, _, _ = compute_track_energy(t)
                decisions[t.id].placement_reason = f"Ordered along {constraints.energy_progression} curve (energy score: {en_score:.1f})"
                decisions[t.id].constraints_applied.append(f"energy_progression:{constraints.energy_progression}")
        elif constraints.sort_mode:
            sm = constraints.sort_mode.lower().strip()
            if sm in ("chronological", "time-travel", "oldest-first"):
                current = sequence_artist_evolution(current, reverse=False)
            elif sm in ("newest", "newest-first", "reverse-chronological"):
                current = sequence_artist_evolution(current, reverse=True)
            elif sm in ("decade", "decade-journey", "era"):
                current = sequence_decade_journey(current)
            elif sm in ("genre", "genre-journey", "genre-flow"):
                current = sequence_genre_journey(current)
            elif sm in ("nostalgia", "nostalgia-mode"):
                current = sequence_nostalgia_mode(current)
            elif sm in ("popularity", "hits", "hits-first"):
                current.sort(key=lambda t: (t.popularity is not None, t.popularity or 0), reverse=True)
            elif sm in ("gems", "gems-first", "underground"):
                current.sort(key=lambda t: (t.popularity is not None, -(t.popularity or 0)), reverse=True)

            for t in current:
                decisions[t.id].constraints_applied.append(f"sort_mode:{sm}")

        # 5. Popularity bias (safe for None popularity)
        if constraints.popularity_bias == "hits":
            current.sort(key=lambda t: (t.popularity is not None, t.popularity or 0), reverse=True)
        elif constraints.popularity_bias == "gems":
            current.sort(key=lambda t: (t.popularity is not None, -(t.popularity or 0)), reverse=True)

        # 6. Artist spacing (De-clumper)
        placement_records: list[PlacementDecision] = []
        if constraints.min_artist_spacing > 0:
            current, _, _, placement_records = declump_tracks(
                current,
                min_spacing=constraints.min_artist_spacing,
                return_details=True
            )
            for rec in placement_records:
                if rec.track_id in decisions:
                    decisions[rec.track_id].placement_reason = rec.reason
                    decisions[rec.track_id].constraints_applied.append("artist_spacing")
                    if rec.constraint_relaxed:
                        decisions[rec.track_id].constraints_relaxed.append("artist_spacing")

        # 7. Pinned positions
        if constraints.pinned_positions:
            for pos, track_ident in constraints.pinned_positions.items():
                idx = pos if pos >= 0 else len(current) + pos
                target_idx = None
                for i, t in enumerate(current):
                    if t.id == track_ident or t.uri == track_ident or t.name.lower() == track_ident.lower():
                        target_idx = i
                        break

                if target_idx is not None and 0 <= idx < len(current):
                    t = current.pop(target_idx)
                    current.insert(idx, t)
                    decisions[t.id].placement_reason = f"Explicitly pinned to position #{idx + 1}"
                    decisions[t.id].constraints_applied.append("pinned_positions")

        # Assign final 1-based positions for all selected tracks
        for idx, t in enumerate(current, 1):
            if t.id in decisions:
                decisions[t.id].position = idx
                if not decisions[t.id].placement_reason:
                    decisions[t.id].placement_reason = f"Ordered at position #{idx} via journey flow"

        # 8. CENTRAL INDEPENDENT VALIDATION
        # Run PlaylistValidator on the actual finished tracks
        validation_report = PlaylistValidator.validate_playlist(
            original_tracks=tracks,
            final_tracks=current,
            min_artist_spacing=constraints.min_artist_spacing,
            max_tracks_per_artist=constraints.max_tracks_per_artist,
            target_duration_minutes=constraints.target_duration_minutes,
            duration_tolerance_minutes=constraints.duration_tolerance_minutes,
            min_duration_minutes=constraints.min_duration_minutes,
            max_duration_minutes=constraints.max_duration_minutes,
            genre_distribution=constraints.genre_distribution,
            decade_distribution=constraints.decade_distribution,
            pinned_positions=constraints.pinned_positions
        )

        diff_summary = f"Curated {len(current)} tracks from initial pool of {initial_count} tracks."
        total_duration_ms = sum(t.duration_ms for t in current)

        # 9. Compile CurationExplanation
        explanation = CurationExplanation(
            playlist_name=playlist_name,
            source_track_count=initial_count,
            final_track_count=len(current),
            duration_achieved_ms=total_duration_ms,
            duration_target_minutes=constraints.target_duration_minutes,
            constraint_audits=validation_report.results,
            track_decisions=list(decisions.values()),
            diff_summary=diff_summary
        )

        return CurationPlan(
            playlist_name=playlist_name,
            tracks=current,
            initial_track_count=initial_count,
            final_track_count=len(current),
            constraints_evaluated=validation_report.results,
            diff_summary=diff_summary,
            explanation=explanation
        )
