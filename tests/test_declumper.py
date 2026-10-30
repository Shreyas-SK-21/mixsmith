"""Unit tests for the Advanced Artist De-clumping Engine."""

import pytest
from mixsmith.core.declumper import analyze_spacing_feasibility, declump_tracks


def test_declump_no_consecutive_artists(make_track):
    """Verifies that no two consecutive tracks share the same primary artist."""
    # 4 tracks by Artist A, 4 tracks by Artist B
    tracks = [
        make_track(id=f"a_{i}", artists=["Artist A"]) for i in range(4)
    ] + [
        make_track(id=f"b_{i}", artists=["Artist B"]) for i in range(4)
    ]

    result, constraint = declump_tracks(tracks, min_spacing=1)

    assert len(result) == 8
    assert constraint.satisfied is True
    # Verify no consecutive artist
    for i in range(len(result) - 1):
        assert result[i].primary_artist != result[i + 1].primary_artist


def test_declump_featured_and_co_artists(make_track):
    """Verifies that collaboration tracks with shared artists are separated."""
    tracks = [
        make_track(id="t1", artists=["Artist A", "Artist B"]),
        make_track(id="t2", artists=["Artist B"]),
        make_track(id="t3", artists=["Artist C"]),
        make_track(id="t4", artists=["Artist D"]),
    ]

    result, constraint = declump_tracks(tracks, min_spacing=1, consider_all_artists=True)

    assert len(result) == 4
    for i in range(len(result) - 1):
        artists_curr = set(result[i].artists)
        artists_next = set(result[i + 1].artists)
        assert len(artists_curr & artists_next) == 0


def test_declump_k_spacing_window(make_track):
    """Verifies configurable spacing k >= 2."""
    # 3 tracks by A, 3 by B, 3 by C (9 total)
    tracks = (
        [make_track(id=f"a_{i}", artists=["Artist A"]) for i in range(3)] +
        [make_track(id=f"b_{i}", artists=["Artist B"]) for i in range(3)] +
        [make_track(id=f"c_{i}", artists=["Artist C"]) for i in range(3)]
    )

    result, constraint = declump_tracks(tracks, min_spacing=2)

    assert len(result) == 9
    assert constraint.satisfied is True
    # Verify that each artist has at least 2 tracks between appearances
    artist_positions = {}
    for idx, t in enumerate(result):
        a = t.primary_artist
        if a in artist_positions:
            gap = idx - artist_positions[a] - 1
            assert gap >= 2
        artist_positions[a] = idx


def test_declump_infeasible_constraints_graceful_fallback(make_track):
    """Verifies that impossible constraints are detected, reported, and fall back gracefully without losing tracks."""
    # 8 tracks by Artist A, 2 tracks by Artist B (10 total)
    # Impossible to have spacing of 1 without consecutive Artist A
    tracks = (
        [make_track(id=f"a_{i}", artists=["Artist A"]) for i in range(8)] +
        [make_track(id=f"b_{i}", artists=["Artist B"]) for i in range(2)]
    )

    feasibility = analyze_spacing_feasibility(tracks, min_spacing=1)
    assert feasibility.is_feasible is False
    assert len(feasibility.bottleneck_artists) == 1
    assert feasibility.bottleneck_artists[0][0] == "artist a"

    # Execution should still complete and preserve all 10 tracks
    result, constraint = declump_tracks(tracks, min_spacing=1)
    assert len(result) == 10
    assert constraint.satisfied is False
    assert constraint.severity == "warning"
    # Ensure all original track IDs are present
    assert set(t.id for t in result) == set(t.id for t in tracks)
