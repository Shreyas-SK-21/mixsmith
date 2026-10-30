"""Unit tests for track filtering and AST expression evaluation."""

import pytest

from mixsmith.core.exceptions import FilterSyntaxError
from mixsmith.core.filters import evaluate_filter_expression, filter_tracks


def test_filter_by_artist(sample_tracks):
    """Tests filtering by primary or co-artist."""
    weeknd_tracks = filter_tracks(sample_tracks, artist_filter="The Weeknd")
    assert len(weeknd_tracks) == 3
    for t in weeknd_tracks:
        assert "The Weeknd" in t.artists


def test_filter_by_genre(sample_tracks):
    """Tests filtering by primary or sub-genres."""
    rock_tracks = filter_tracks(sample_tracks, genre_filter="Rock")
    # Nirvana (3) + Arctic Monkeys t6 (1)
    assert len(rock_tracks) == 4
    for t in rock_tracks:
        assert "rock" in t.primary_genre.lower() or "rock" in [g.lower() for g in t.all_genres]


def test_filter_by_decade(sample_tracks):
    """Tests filtering by decade."""
    nineties = filter_tracks(sample_tracks, decade_filter="90s")
    assert len(nineties) == 3
    for t in nineties:
        assert t.decade == "90s"


def test_ast_boolean_expression(make_track):
    """Tests AST boolean expression evaluation."""
    t1 = make_track(primary_genre="Rock", release_year=1991, popularity=85, explicit=False)
    t2 = make_track(primary_genre="Pop", release_year=2021, popularity=40, explicit=True)

    # Complex boolean expressions
    assert evaluate_filter_expression(t1, "genre == 'rock' and year == 1991") is True
    assert evaluate_filter_expression(t2, "genre == 'rock' and year == 1991") is False
    assert evaluate_filter_expression(t2, "genre == 'pop' and popularity < 50") is True
    assert evaluate_filter_expression(t1, "clean and popularity >= 80") is True
    assert evaluate_filter_expression(t2, "is_explicit") is True


def test_ast_filter_syntax_error(make_track):
    """Tests that invalid variables or malformed expressions raise FilterSyntaxError."""
    t = make_track()
    with pytest.raises(FilterSyntaxError):
        evaluate_filter_expression(t, "non_existent_column > 5")
