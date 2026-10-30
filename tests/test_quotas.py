"""Unit tests for the Hamilton-Hare Largest Remainder Quota Allocation engine."""

from mixsmith.core.quotas import allocate_genre_quotas, allocate_largest_remainder


def test_largest_remainder_exact_sum():
    """Verifies that integer slots sum EXACTLY to total_slots across awkward percentages."""
    weights = {"Rock": 0.3333, "Pop": 0.3333, "Indie": 0.3334}
    total_slots = 100

    allocation = allocate_largest_remainder(weights, total_slots)

    assert sum(allocation.values()) == total_slots
    assert allocation["Rock"] in (33, 34)
    assert allocation["Pop"] in (33, 34)
    assert allocation["Indie"] in (33, 34)


def test_largest_remainder_small_integers():
    """Verifies allocation when total slots is small."""
    weights = {"A": 1.0, "B": 2.0, "C": 3.0}
    total = 7

    alloc = allocate_largest_remainder(weights, total)
    assert sum(alloc.values()) == total
    assert alloc["C"] >= alloc["B"] >= alloc["A"]


def test_allocate_genre_quotas_multi_genre(make_track):
    """Verifies quota allocation distributes multi-genre tracks properly."""
    tracks = [
        make_track(id=f"r{i}", primary_genre="Rock", all_genres=["rock", "alternative"]) for i in range(10)
    ] + [
        make_track(id=f"p{i}", primary_genre="Pop", all_genres=["pop", "dance"]) for i in range(10)
    ]

    res = allocate_genre_quotas(tracks, {"Rock": 0.7, "Pop": 0.3}, total_tracks_target=10)

    assert len(res.selected_tracks) == 10
    assert res.allocated_counts["Rock"] == 7
    assert res.allocated_counts["Pop"] == 3
