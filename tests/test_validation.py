"""Unit tests for the Independent Constraint Validation System."""

from mixsmith.core.validation import PlaylistValidator


def test_validate_artist_spacing_detects_violations(make_track):
    """Verifies that the validator correctly detects spacing violations."""
    t1 = make_track(id="t1", name="Song 1", artists=["Artist A"])
    t2 = make_track(id="t2", name="Song 2", artists=["Artist B"])
    t3 = make_track(id="t3", name="Song 3", artists=["Artist A"])  # Spacing 1 from t1

    # Spacing = 1 requires gap >= 1 (j - i - 1 >= 1 => j - i >= 2). Here gap = 2 - 0 - 1 = 1 >= 1.
    res_k1 = PlaylistValidator.validate_artist_spacing([t1, t2, t3], min_spacing=1)
    assert res_k1.satisfied is True

    # Spacing = 2 requires gap >= 2. Here gap = 1 < 2, so it must fail!
    res_k2 = PlaylistValidator.validate_artist_spacing([t1, t2, t3], min_spacing=2)
    assert res_k2.satisfied is False
    assert "spacing violation" in res_k2.details.lower()


def test_validate_max_tracks_per_artist(make_track):
    """Verifies detection when an artist exceeds allowable track limit."""
    tracks = [
        make_track(id=f"t{i}", name=f"Song {i}", artists=["The Weeknd"]) for i in range(4)
    ]
    res = PlaylistValidator.validate_max_tracks_per_artist(tracks, max_tracks=2)
    assert res.satisfied is False
    assert res.severity == "error"
    assert "The Weeknd" in res.details


def test_validate_target_duration(make_track):
    """Verifies duration validation within tolerance."""
    # 3 tracks of 200,000 ms (3.33 min each = 10 min total)
    tracks = [make_track(duration_ms=200000) for _ in range(3)]

    # Target 10 min +/- 2 min: PASS
    res_pass = PlaylistValidator.validate_target_duration(tracks, target_minutes=10, tolerance_minutes=2)
    assert res_pass.satisfied is True

    # Target 60 min +/- 5 min: FAIL
    res_fail = PlaylistValidator.validate_target_duration(tracks, target_minutes=60, tolerance_minutes=5)
    assert res_fail.satisfied is False


def test_validate_track_preservation_foreign_track_detection(make_track):
    """Verifies foreign tracks not in original pool trigger an error."""
    pool = [make_track(id="t1"), make_track(id="t2")]
    final = [make_track(id="t1"), make_track(id="t_foreign")]

    res = PlaylistValidator.validate_track_preservation(pool, final)
    assert res.satisfied is False
    assert res.severity == "error"
    assert "t_foreign" in res.details
