"""Unit tests for Duration Optimization (0/1 Knapsack)."""

import pytest
from mixsmith.core.duration import optimize_playlist_duration


def test_knapsack_duration_exact_fit(make_track):
    """Verifies that Knapsack selects optimal combination within target duration."""
    # 5 tracks of 3 mins (180,000 ms), 5 tracks of 4 mins (240,000 ms), 5 tracks of 5 mins (300,000 ms)
    tracks = (
        [make_track(id=f"t3_{i}", duration_ms=180000, popularity=50) for i in range(5)] +
        [make_track(id=f"t4_{i}", duration_ms=240000, popularity=70) for i in range(5)] +
        [make_track(id=f"t5_{i}", duration_ms=300000, popularity=60) for i in range(5)]
    )

    # Target: 15 minutes = 900,000 ms +/- 2 minutes
    res = optimize_playlist_duration(tracks, target_minutes=15, tolerance_minutes=2)

    assert res.is_within_tolerance is True
    assert 13 * 60 * 1000 <= res.total_duration_ms <= 17 * 60 * 1000
    assert len(res.selected_tracks) > 0
    assert len(res.excluded_tracks) > 0
    # Every excluded track must have an explanation reason
    for t in res.excluded_tracks:
        assert t.id in res.exclusion_reasons


def test_duration_optimization_pool_already_fits(make_track):
    """Verifies that when entire pool fits under target ceiling, all are selected."""
    tracks = [make_track(id=f"t_{i}", duration_ms=120000) for i in range(3)]  # 6 min total
    res = optimize_playlist_duration(tracks, target_minutes=10, tolerance_minutes=5)

    assert len(res.selected_tracks) == 3
    assert len(res.excluded_tracks) == 0
    assert res.is_within_tolerance is True
