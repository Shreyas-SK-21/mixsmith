"""Regression tests for quota allocation, unfilled slot handling, and validation."""

import pytest

from mixsmith.core.models import Track
from mixsmith.core.quotas import (
    allocate_genre_quotas,
    validate_quota_weights,
)


def test_invalid_quota_weights_raise_error():
    """Negative, NaN, or non-positive weights must raise ValueError."""
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_quota_weights({"Rock": 0.5, "Indie": -0.2})

    with pytest.raises(ValueError, match="cannot be NaN or infinite"):
        validate_quota_weights({"Rock": float("nan")})

    with pytest.raises(ValueError, match="must be strictly positive"):
        validate_quota_weights({"Rock": 0.0, "Indie": 0.0})


def test_insufficient_tracks_reports_unfilled_and_reallocates():
    """
    When a category has insufficient candidate tracks, unfilled slots are recorded
    and reallocated to surplus categories to maintain target playlist size.
    """
    # 2 Metal tracks, 10 Pop tracks
    tracks = [
        Track(id=f"m_{i}", uri=f"m:{i}", name=f"Metal {i}", artists=["Band M"], primary_genre="Metal")
        for i in range(2)
    ] + [
        Track(id=f"p_{i}", uri=f"p:{i}", name=f"Pop {i}", artists=["Pop Star"], primary_genre="Pop")
        for i in range(10)
    ]

    # Request 5 Metal, 5 Pop (Target 10 tracks)
    res = allocate_genre_quotas(
        tracks,
        genre_quotas={"Metal": 0.50, "Pop": 0.50},
        total_tracks_target=10,
        reallocate_unfilled=True
    )

    assert len(res.selected_tracks) == 10
    # Metal had quota 5 but only 2 available -> 3 unfilled slots
    assert res.unfilled_slots.get("Metal") == 3
    # Surplus tracks filled the deficit
    assert any("shortfall reallocation" in reason for reason in res.selection_reasons.values())


def test_multi_genre_tracks_allocation():
    """Tracks tagged with multiple genres should be prioritized to scarce categories without starving."""
    # Track with both Shoegaze and Indie
    t_multi = Track(id="1", uri="1", name="Nu Gaze", artists=["A"], primary_genre="Shoegaze", all_genres=["shoegaze", "indie"])
    t_indie = Track(id="2", uri="2", name="Indie Only", artists=["B"], primary_genre="Indie", all_genres=["indie"])

    # 1 Shoegaze slot, 1 Indie slot
    res = allocate_genre_quotas(
        [t_multi, t_indie],
        genre_quotas={"Shoegaze": 0.5, "Indie": 0.5},
        total_tracks_target=2
    )

    assert len(res.selected_tracks) == 2
    selected_ids = {t.id for t in res.selected_tracks}
    assert "1" in selected_ids and "2" in selected_ids


def test_repeated_source_occurrences():
    """Identical track IDs appearing multiple times in source pool can each occupy a slot."""
    t1 = Track(id="dup_1", uri="uri:1", name="Song", artists=["A"], primary_genre="Rock")
    t2 = Track(id="dup_1", uri="uri:1", name="Song", artists=["A"], primary_genre="Rock")

    res = allocate_genre_quotas(
        [t1, t2],
        genre_quotas={"Rock": 1.0},
        total_tracks_target=2
    )

    assert len(res.selected_tracks) == 2
