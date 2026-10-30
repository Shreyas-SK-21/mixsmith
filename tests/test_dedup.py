"""Unit tests for the Intelligent Deduplication Engine."""

from mixsmith.core.dedup import (
    classify_track_variant,
    deduplicate_tracks,
    find_duplicates,
)


def test_classify_track_variants(make_track):
    """Tests categorization of track versions."""
    t_std = make_track(name="Creep", album="Pablo Honey")
    t_rem = make_track(name="Creep - 2021 Remaster", album="Pablo Honey")
    t_live = make_track(name="Creep (Live at Reading Festival)", album="Live Recordings")
    t_ac = make_track(name="Creep - Acoustic Version", album="Acoustic Sessions")
    t_dlx = make_track(name="Creep", album="Pablo Honey (Deluxe Edition)")

    assert classify_track_variant(t_std) == "standard"
    assert classify_track_variant(t_rem) == "remaster"
    assert classify_track_variant(t_live) == "live"
    assert classify_track_variant(t_ac) == "acoustic"
    assert classify_track_variant(t_dlx) == "deluxe"


def test_find_exact_duplicates_by_isrc(make_track):
    """Tests grouping by identical ISRC code."""
    t1 = make_track(id="t1", name="Heroes", isrc="GBAYE7700030")
    t2 = make_track(id="t2", name="Heroes", isrc="GBAYE7700030")

    groups = find_duplicates([t1, t2])
    assert len(groups) == 1
    assert groups[0].category == "exact"
    assert groups[0].canonical_track.id == "t1"
    assert groups[0].variants[0].id == "t2"


def test_deduplicate_exact_only_preserves_live_and_acoustic(make_track):
    """Verifies that 'exact_only' strategy keeps artistic variants (live, acoustic, remasters)."""
    t_studio1 = make_track(id="s1", name="Hotel California", isrc="USEE123")
    t_studio2 = make_track(id="s2", name="Hotel California", isrc="USEE123")  # exact duplicate
    t_live = make_track(id="l1", name="Hotel California - Live", isrc="USEE456")
    t_acoustic = make_track(id="a1", name="Hotel California (Acoustic)", isrc="USEE789")

    deduped, groups = deduplicate_tracks([t_studio1, t_studio2, t_live, t_acoustic], strategy="exact_only")

    # t_studio2 dropped; t_studio1, t_live, and t_acoustic retained
    assert len(deduped) == 3
    retained_ids = [t.id for t in deduped]
    assert "s1" in retained_ids
    assert "l1" in retained_ids
    assert "a1" in retained_ids
    assert "s2" not in retained_ids


def test_deduplicate_keep_original(make_track):
    """Verifies that 'keep_original' discards remasters and live cuts in favor of standard cut."""
    t_studio = make_track(id="s1", name="Comfortably Numb", popularity=70)
    t_rem = make_track(id="r1", name="Comfortably Numb - 2011 Remaster", popularity=80)
    t_live = make_track(id="l1", name="Comfortably Numb (Live)", popularity=65)

    deduped, groups = deduplicate_tracks([t_rem, t_studio, t_live], strategy="keep_original")

    assert len(deduped) == 1
    assert deduped[0].id == "s1"
