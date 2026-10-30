"""Regression tests for duration optimization and adversarial time discretization."""

import pytest

from mixsmith.core.duration import optimize_playlist_duration
from mixsmith.core.models import Track


def test_adversarial_durations_not_multiples_of_five_seconds():
    """Adversarial millisecond durations must never exceed the runtime ceiling."""
    # Tracks with prime and irregular durations not multiples of 5,000ms
    durations = [213456, 187123, 311999, 145678, 267891, 199999, 233333, 178912]
    tracks = [
        Track(id=f"t{i}", uri=f"uri:{i}", name=f"Song {i}", artists=[f"Artist {i % 3}"], duration_ms=d, popularity=70)
        for i, d in enumerate(durations)
    ]

    target_minutes = 10  # 600,000 ms
    tolerance_minutes = 2  # Max acceptable = 12 min = 720,000 ms
    max_acceptable_ms = (target_minutes + tolerance_minutes) * 60 * 1000

    res = optimize_playlist_duration(
        tracks,
        target_minutes=target_minutes,
        tolerance_minutes=tolerance_minutes,
        time_unit_seconds=5
    )

    # Must strictly satisfy millisecond ceiling
    assert res.total_duration_ms <= max_acceptable_ms
    assert sum(t.duration_ms for t in res.selected_tracks) == res.total_duration_ms
    assert len(res.selected_tracks) > 0


def test_duration_argument_validation():
    """Invalid arguments must raise descriptive ValueError."""
    t = Track(id="1", uri="1", name="T", artists=["A"], duration_ms=180000)

    # Target minutes <= 0
    with pytest.raises(ValueError, match="target_minutes must be a positive integer"):
        optimize_playlist_duration([t], target_minutes=0)

    with pytest.raises(ValueError, match="target_minutes must be a positive integer"):
        optimize_playlist_duration([t], target_minutes=-5)

    # Tolerance < 0
    with pytest.raises(ValueError, match="tolerance_minutes cannot be negative"):
        optimize_playlist_duration([t], target_minutes=30, tolerance_minutes=-1)

    # Time unit <= 0
    with pytest.raises(ValueError, match="time_unit_seconds must be a positive integer"):
        optimize_playlist_duration([t], target_minutes=30, time_unit_seconds=0)


def test_large_library_artist_diversity():
    """Large library optimizer incorporates artist diversity rather than monopolizing top artists."""
    # Generate 350 tracks: Artist Dominant has 150 high-popularity tracks; other artists have 1 track each
    tracks = []
    for i in range(150):
        tracks.append(Track(id=f"dom_{i}", uri=f"dom:{i}", name=f"Dom {i}", artists=["Dominant Star"], duration_ms=200000, popularity=95))
    for i in range(200):
        tracks.append(Track(id=f"indie_{i}", uri=f"indie:{i}", name=f"Indie {i}", artists=[f"Indie Artist {i}"], duration_ms=200000, popularity=80))

    res = optimize_playlist_duration(tracks, target_minutes=30, tolerance_minutes=5)

    # A 30-min playlist (~9 tracks) should NOT be 100% Dominant Star
    dominant_count = sum(1 for t in res.selected_tracks if t.primary_artist == "Dominant Star")
    unique_artists = {t.primary_artist for t in res.selected_tracks}

    assert len(unique_artists) > 1, "Optimizer failed to incorporate artist diversity"
    assert dominant_count < len(res.selected_tracks), "Dominant artist should not monopolize the entire playlist"
