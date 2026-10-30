"""Multi-constraint playlist sequencing engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from mixsmith.core.declumper import analyze_spacing_feasibility, declump_tracks
from mixsmith.core.journeys import (
    sequence_artist_evolution,
    sequence_decade_journey,
    sequence_genre_journey,
    sequence_nostalgia_mode,
)
from mixsmith.core.models import ConstraintResult, CurationPlan, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.sequencing")


@dataclass
class CurationConstraints:
    """Specification of all constraints for curating and sequencing a playlist."""
    min_artist_spacing: int = 1
    max_tracks_per_artist: Optional[int] = None
    target_duration_minutes: Optional[int] = None
    duration_tolerance_minutes: int = 10
    genre_distribution: Optional[Dict[str, float]] = None
    decade_distribution: Optional[Dict[str, float]] = None
    pinned_positions: Optional[Dict[int, str]] = None  # index -> track_id / uri
    popularity_bias: Optional[str] = None  # "hits", "gems", "balanced"
    sort_mode: Optional[str] = None  # "declump", "chronological", "decade", "genre", "nostalgia"
    preserve_order: bool = False


class ConstraintSequencingEngine:
    """Engine that curates and sequences playlists satisfying multiple simultaneous constraints."""

    def curate(
        self,
        tracks: List[Track],
        constraints: Optional[CurationConstraints] = None,
        playlist_name: str = "Curated Playlist"
    ) -> CurationPlan:
        """Executes multi-constraint curation and produces an audited CurationPlan."""
        constraints = constraints or CurationConstraints()
        initial_count = len(tracks)
        current = list(tracks)
        results: List[ConstraintResult] = []

        # 1. Enforce max tracks per artist
        if constraints.max_tracks_per_artist is not None and constraints.max_tracks_per_artist > 0:
            limit = constraints.max_tracks_per_artist
            artist_buckets: Dict[str, List[Track]] = defaultdict(list)
            for t in current:
                a_key = t.primary_artist.lower().strip() if t.primary_artist else "unknown"
                artist_buckets[a_key].append(t)

            pruned: List[Track] = []
            capped_artists = []
            for a_key, a_tracks in artist_buckets.items():
                if len(a_tracks) > limit:
                    # Keep tracks with highest popularity
                    sorted_a = sorted(a_tracks, key=lambda t: t.popularity, reverse=True)
                    pruned.extend(sorted_a[:limit])
                    capped_artists.append(f"{a_tracks[0].primary_artist} ({len(a_tracks)}->{limit})")
                else:
                    pruned.extend(a_tracks)

            current = pruned
            satisfied = len(capped_artists) > 0 or len(current) == initial_count
            details = (
                f"Capped {len(capped_artists)} artists at max {limit} tracks: {', '.join(capped_artists[:5])}"
                if capped_artists else f"All artists were already within max {limit} tracks limit."
            )
            results.append(ConstraintResult(
                name="max_tracks_per_artist",
                satisfied=True,
                details=details
            ))

        # 2. Genre distribution quota
        if constraints.genre_distribution:
            target_genres = {k.lower(): v for k, v in constraints.genre_distribution.items()}
            # Normalize quotas
            total_ratio = sum(target_genres.values())
            normalized_quotas = {k: v / total_ratio for k, v in target_genres.items()}

            genre_buckets: Dict[str, List[Track]] = defaultdict(list)
            for t in current:
                genre_buckets[t.primary_genre.lower()].append(t)

            selected_tracks: List[Track] = []
            target_total = len(current)
            for g_name, quota in normalized_quotas.items():
                quota_count = int(round(target_total * quota))
                matching_tracks = genre_buckets.get(g_name, [])
                if matching_tracks:
                    # Sort by popularity
                    selected_tracks.extend(sorted(matching_tracks, key=lambda t: t.popularity, reverse=True)[:quota_count])

            if selected_tracks:
                current = selected_tracks
                results.append(ConstraintResult(
                    name="genre_distribution",
                    satisfied=True,
                    details=f"Applied genre distribution across {len(normalized_quotas)} categories."
                ))
            else:
                results.append(ConstraintResult(
                    name="genre_distribution",
                    satisfied=False,
                    details="Could not satisfy genre distribution: no tracks matched specified genres.",
                    severity="warning"
                ))

        # 3. Target playlist duration
        if constraints.target_duration_minutes is not None:
            target_ms = constraints.target_duration_minutes * 60 * 1000
            tol_ms = constraints.duration_tolerance_minutes * 60 * 1000

            fitted_tracks: List[Track] = []
            accumulated_ms = 0

            # Sort candidate tracks by popularity
            sorted_candidates = sorted(current, key=lambda t: t.popularity, reverse=True)
            for t in sorted_candidates:
                if accumulated_ms + t.duration_ms <= target_ms + tol_ms:
                    fitted_tracks.append(t)
                    accumulated_ms += t.duration_ms
                    if accumulated_ms >= target_ms - tol_ms:
                        break

            if fitted_tracks:
                current = fitted_tracks
                actual_min = accumulated_ms // 60000
                results.append(ConstraintResult(
                    name="target_duration",
                    satisfied=abs(accumulated_ms - target_ms) <= tol_ms,
                    details=f"Achieved {actual_min} mins (target: {constraints.target_duration_minutes} +/- {constraints.duration_tolerance_minutes} min)."
                ))

        # 4. Sorting & Journey Sequencing
        if constraints.sort_mode:
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
                current.sort(key=lambda t: t.popularity, reverse=True)
            elif sm in ("gems", "gems-first", "underground"):
                current.sort(key=lambda t: t.popularity, reverse=False)

        # 5. Popularity bias
        if constraints.popularity_bias == "hits":
            current.sort(key=lambda t: t.popularity, reverse=True)
        elif constraints.popularity_bias == "gems":
            current.sort(key=lambda t: t.popularity)

        # 6. Artist spacing (De-clumper)
        if constraints.min_artist_spacing > 0:
            current, declump_res = declump_tracks(current, min_spacing=constraints.min_artist_spacing)
            results.append(declump_res)

        # 7. Pinned positions
        if constraints.pinned_positions:
            pinned_satisfied = 0
            for pos, track_ident in constraints.pinned_positions.items():
                idx = pos if pos >= 0 else len(current) + pos
                # Find track in current
                target_idx = None
                for i, t in enumerate(current):
                    if t.id == track_ident or t.uri == track_ident or t.name.lower() == track_ident.lower():
                        target_idx = i
                        break

                if target_idx is not None and 0 <= idx < len(current):
                    t = current.pop(target_idx)
                    current.insert(idx, t)
                    pinned_satisfied += 1

            results.append(ConstraintResult(
                name="pinned_positions",
                satisfied=pinned_satisfied == len(constraints.pinned_positions),
                details=f"Pinned {pinned_satisfied} of {len(constraints.pinned_positions)} specified tracks."
            ))

        diff_summary = f"Curated {len(current)} tracks from initial {initial_count} tracks."

        return CurationPlan(
            playlist_name=playlist_name,
            tracks=current,
            initial_track_count=initial_count,
            final_track_count=len(current),
            constraints_evaluated=results,
            diff_summary=diff_summary
        )
