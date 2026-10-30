"""Regression tests for artist de-clumper and mathematical feasibility."""

from mixsmith.core.declumper import (
    FeasibilityStatus,
    analyze_spacing_feasibility,
    declump_tracks,
)
from mixsmith.core.models import Track


def test_two_consecutive_tracks_same_artist():
    """A 2-track playlist by the same artist must never be reported as satisfied with min_spacing >= 1."""
    t1 = Track(id="1", uri="spotify:track:1", name="Song 1", artists=["Radiohead"], primary_artist="Radiohead")
    t2 = Track(id="2", uri="spotify:track:2", name="Song 2", artists=["Radiohead"], primary_artist="Radiohead")

    result, res, feas, decisions = declump_tracks([t1, t2], min_spacing=1, return_details=True)

    # Must be marked unsatisfied with an error severity
    assert res.satisfied is False
    assert res.severity == "error"
    assert "violation(s)" in res.details
    assert feas.is_feasible is False
    assert feas.status == FeasibilityStatus.PROVEN_INFEASIBLE
    assert feas.max_achievable_spacing == 0


def test_two_tracks_different_artists():
    """A 2-track playlist by different artists must satisfy spacing 1."""
    t1 = Track(id="1", uri="spotify:track:1", name="Song 1", artists=["Radiohead"], primary_artist="Radiohead")
    t2 = Track(id="2", uri="spotify:track:2", name="Song 2", artists=["Portishead"], primary_artist="Portishead")

    result, res, feas, _ = declump_tracks([t1, t2], min_spacing=1, return_details=True)

    assert res.satisfied is True
    assert res.severity == "info"
    assert feas.is_feasible is True


def test_two_collaborative_pair_tracks_in_four_track_playlist_spacing_2():
    """
    Two tracks sharing collaborative pair {A, B} in a 4-track playlist with spacing 2:
    Can be placed at indices 0 and 3 (gap 2 >= 2).
    """
    t1 = Track(id="1", uri="spotify:track:1", name="Collab 1", artists=["Artist A", "Artist B"])
    t2 = Track(id="2", uri="spotify:track:2", name="Solo 1", artists=["Artist C"])
    t3 = Track(id="3", uri="spotify:track:3", name="Solo 2", artists=["Artist D"])
    t4 = Track(id="4", uri="spotify:track:4", name="Collab 2", artists=["Artist A", "Artist B"])

    result, res, feas, _ = declump_tracks([t1, t2, t3, t4], min_spacing=2, return_details=True)

    # Finding positions 0 and 3 gives gap 2, satisfying min_spacing 2
    assert res.satisfied is True
    assert res.severity == "info"
    # Verify positions of t1 and t4 in result
    indices = [i for i, t in enumerate(result) if t.id in ("1", "4")]
    assert len(indices) == 2
    assert abs(indices[1] - indices[0]) - 1 >= 2


def test_multi_artist_overlapping_collaborations():
    """Multi-artist overlapping tracks (A+B, B+C, C+D, D+E) with spacing 1."""
    tracks = [
        Track(id="1", uri="spotify:track:1", name="T1", artists=["A", "B"]),
        Track(id="2", uri="spotify:track:2", name="T2", artists=["B", "C"]),
        Track(id="3", uri="spotify:track:3", name="T3", artists=["C", "D"]),
        Track(id="4", uri="spotify:track:4", name="T4", artists=["D", "E"]),
        Track(id="5", uri="spotify:track:5", name="T5", artists=["E", "F"]),
        Track(id="6", uri="spotify:track:6", name="T6", artists=["F", "G"]),
    ]

    result, res, feas, _ = declump_tracks(tracks, min_spacing=1, return_details=True)

    assert res.satisfied is True
    assert res.severity == "info"


def test_conditionally_constrained_feasibility():
    """
    Individual artists satisfy pigeonhole bounds, but multi-artist collaborations
    are recognized as conditionally constrained without fabricating achievable ceilings.
    """
    # 5 tracks, min_spacing 2:
    # Each single artist appears at most twice (ceil(5 / 3) = 2), so single-artist bounds pass.
    tracks = [
        Track(id="1", uri="spotify:track:1", name="T1", artists=["A", "B"]),
        Track(id="2", uri="spotify:track:2", name="T2", artists=["A", "C"]),
        Track(id="3", uri="spotify:track:3", name="T3", artists=["B", "C"]),
        Track(id="4", uri="spotify:track:4", name="T4", artists=["D"]),
        Track(id="5", uri="spotify:track:5", name="T5", artists=["E"]),
    ]
    report = analyze_spacing_feasibility(tracks, min_spacing=2)

    assert report.status == FeasibilityStatus.CONDITIONALLY_CONSTRAINED
    assert report.is_feasible is True
    assert report.max_achievable_spacing is None  # Not fabricated


def test_empty_artist_metadata():
    """Tracks with empty or missing artist metadata should not crash or create false collisions."""
    t_empty_1 = Track(id="1", uri="spotify:track:1", name="Empty 1", artists=[], primary_artist="")
    t_empty_2 = Track(id="2", uri="spotify:track:2", name="Empty 2", artists=[], primary_artist="")
    t_valid = Track(id="3", uri="spotify:track:3", name="Valid", artists=["Artist A"], primary_artist="Artist A")

    result, res, feas, decisions = declump_tracks([t_empty_1, t_empty_2, t_valid], min_spacing=1, return_details=True)

    assert len(result) == 3
    assert res.satisfied is True
    assert feas.is_feasible is True
