"""Unit tests for Constraint-Based Playlist Sequencing Engine."""

import pytest
from mixsmith.core.journeys import (
    sequence_artist_evolution,
    sequence_decade_journey,
    sequence_genre_journey,
    sequence_nostalgia_mode,
)
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints


def test_max_tracks_per_artist_constraint(sample_tracks):
    """Tests capping tracks per artist at a specified limit."""
    engine = ConstraintSequencingEngine()
    constraints = CurationConstraints(max_tracks_per_artist=1, min_artist_spacing=0)

    plan = engine.curate(sample_tracks, constraints)

    # In sample_tracks, The Weeknd had 3, Joji had 2, Arctic Monkeys had 2, Nirvana had 3 (4 distinct artists)
    assert plan.final_track_count == 4
    artists = [t.primary_artist for t in plan.tracks]
    assert len(artists) == len(set(artists))


def test_pinned_track_positions(sample_tracks):
    """Tests pinning specific tracks to requested indices."""
    engine = ConstraintSequencingEngine()
    # Pin t8 ("Smells Like Teen Spirit") to first position (0) and t1 to last position (-1)
    constraints = CurationConstraints(
        pinned_positions={0: "t8", -1: "t1"},
        min_artist_spacing=0
    )

    plan = engine.curate(sample_tracks, constraints)

    assert plan.tracks[0].id == "t8"
    assert plan.tracks[-1].id == "t1"


def test_artist_evolution_journey(make_track):
    """Tests chronological artist discography progression."""
    t1 = make_track(name="Album 1", release_year=2002)
    t2 = make_track(name="Album 2", release_year=2006)
    t3 = make_track(name="Album 3", release_year=2013)

    journey = sequence_artist_evolution([t3, t1, t2])
    years = [t.release_year for t in journey]
    assert years == [2002, 2006, 2013]


def test_decade_journey(make_track):
    """Tests sequencing tracks smoothly across eras."""
    t_70s = make_track(decade="70s", release_year=1975)
    t_90s = make_track(decade="90s", release_year=1994)
    t_2010s = make_track(decade="2010s", release_year=2015)

    journey = sequence_decade_journey([t_2010s, t_70s, t_90s])
    decades = [t.decade for t in journey]
    assert decades == ["70s", "90s", "2010s"]
