"""Regression tests for independent constraint validation engine."""

from mixsmith.core.models import Track
from mixsmith.core.validation import PlaylistValidator


def test_validation_fails_when_hard_constraint_fails():
    """Validation report summary MUST say FAILED when a hard constraint fails."""
    t1 = Track(id="1", uri="spotify:track:1", name="Track 1", artists=["Radiohead"], primary_artist="Radiohead")
    t2 = Track(id="2", uri="spotify:track:2", name="Track 2", artists=["Radiohead"], primary_artist="Radiohead")

    report = PlaylistValidator.validate_playlist(
        original_tracks=[t1, t2],
        final_tracks=[t1, t2],  # Consecutive tracks by same artist
        min_artist_spacing=1
    )

    assert report.is_valid is False
    assert "FAILED" in report.summary
    assert report.has_errors is True
    assert "artist_spacing" in report.summary


def test_artist_spacing_reports_all_violations_and_min_gap():
    """Spacing report must record all violations and the actual minimum gap."""
    t1 = Track(id="1", uri="spotify:track:1", name="Track 1", artists=["Artist A"], primary_artist="Artist A")
    t2 = Track(id="2", uri="spotify:track:2", name="Track 2", artists=["Artist A"], primary_artist="Artist A")
    t3 = Track(id="3", uri="spotify:track:3", name="Track 3", artists=["Artist B"], primary_artist="Artist B")
    t4 = Track(id="4", uri="spotify:track:4", name="Track 4", artists=["Artist B"], primary_artist="Artist B")

    res = PlaylistValidator.validate_artist_spacing([t1, t2, t3, t4], min_spacing=2)

    assert res.satisfied is False
    assert res.severity == "error"
    assert "actual minimum gap: 0" in res.details
    assert "Track #1" in res.details and "Track #3" in res.details


def test_decade_distribution_validation():
    """Validates decade quotas and flags excessive deviations."""
    tracks = [
        Track(id="1", uri="1", name="T1", artists=["A"], decade="90s"),
        Track(id="2", uri="2", name="T2", artists=["B"], decade="90s"),
        Track(id="3", uri="3", name="T3", artists=["C"], decade="80s"),
        Track(id="4", uri="4", name="T4", artists=["D"], decade="2000s"),
    ]

    # Target: 50% 90s, 25% 80s, 25% 2000s
    res_pass = PlaylistValidator.validate_decade_distribution(
        tracks,
        target_quotas={"90s": 0.50, "80s": 0.25, "2000s": 0.25},
        tolerance_pct=5.0
    )
    assert res_pass.satisfied is True

    # Target expecting 80% 80s (actual 25%)
    res_fail = PlaylistValidator.validate_decade_distribution(
        tracks,
        target_quotas={"80s": 0.80, "90s": 0.20},
        tolerance_pct=5.0
    )
    assert res_fail.satisfied is False
    assert res_fail.severity == "warning"


def test_track_preservation_detects_foreign_and_multiplied_tracks():
    """Detects tracks not in the original pool and tracks duplicated beyond source count."""
    t1 = Track(id="1", uri="spotify:track:1", name="Original 1", artists=["A"])
    t2 = Track(id="2", uri="spotify:track:2", name="Original 2", artists=["B"])
    t_foreign = Track(id="99", uri="spotify:track:99", name="Foreign", artists=["C"])

    # Foreign track test
    res_foreign = PlaylistValidator.validate_track_preservation(
        original_pool=[t1, t2],
        final_tracks=[t1, t_foreign]
    )
    assert res_foreign.satisfied is False
    assert "foreign track(s)" in res_foreign.details

    # Multiplication test (t1 appears once in source, but twice in final)
    res_multi = PlaylistValidator.validate_track_preservation(
        original_pool=[t1, t2],
        final_tracks=[t1, t1, t2]
    )
    assert res_multi.satisfied is False
    assert "repeated beyond" in res_multi.details


def test_track_preservation_handles_missing_track_ids():
    """Validates preservation without error when track IDs are empty strings."""
    t1 = Track(id="", uri="spotify:track:aaa", name="Song Alpha", artists=["Artist 1"])
    t2 = Track(id="", uri="spotify:track:bbb", name="Song Beta", artists=["Artist 2"])

    res = PlaylistValidator.validate_track_preservation(
        original_pool=[t1, t2],
        final_tracks=[t1, t2]
    )
    assert res.satisfied is True


def test_consistent_featured_artist_handling():
    """Featured artists must be audited consistently across spacing and max-per-artist limits."""
    t1 = Track(id="1", uri="1", name="T1", artists=["Daft Punk", "Pharrell Williams"])
    t2 = Track(id="2", uri="2", name="T2", artists=["Robin Thicke", "Pharrell Williams"])

    # Max 1 track per artist with consider_all_artists=True must flag Pharrell Williams (appears twice)
    res_max = PlaylistValidator.validate_max_tracks_per_artist([t1, t2], max_tracks=1, consider_all_artists=True)
    assert res_max.satisfied is False
    assert "Pharrell Williams" in res_max.details

    # Spacing 1 with consider_all_artists=True must flag Pharrell Williams
    res_spacing = PlaylistValidator.validate_artist_spacing([t1, t2], min_spacing=1, consider_all_artists=True)
    assert res_spacing.satisfied is False
