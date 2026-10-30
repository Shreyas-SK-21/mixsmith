"""Tests for natural language parser execution safety and filter failure safeguards."""

import pytest

from mixsmith.ai.parser import (
    execute_natural_language_curation,
    parse_natural_language_to_spec,
)
from mixsmith.core.exceptions import FilterMatchError
from mixsmith.core.models import Track


def test_zero_match_filter_raises_error():
    """When requested constraints match 0 tracks, it must raise FilterMatchError, never silently replace."""
    tracks = [
        Track(id="1", uri="1", name="Rock Song", artists=["AC/DC"], primary_genre="Rock"),
        Track(id="2", uri="2", name="Metal Song", artists=["Metallica"], primary_genre="Metal"),
    ]

    # User asks for K-Pop (0 matches)
    prompt = "Create a 30-minute K-pop playlist with BTS"
    with pytest.raises(FilterMatchError, match="matched 0 tracks"):
        execute_natural_language_curation(tracks, prompt)


def test_energy_progression_distinct_from_popularity():
    """Energy progression must not be conflated with popularity or set to 'gems'."""
    prompt = "Curate a 90-minute indie rock session that starts mellow and gradually builds energy"
    spec = parse_natural_language_to_spec(prompt)

    # Tempo energy preference should be set
    assert spec.preferences.tempo_energy_preference == "mellow_to_energetic"
    # sort_journey must NOT be set to 'gems' (popularity)
    assert spec.preferences.sort_journey != "gems"
    # Popularity preference should remain unset
    assert spec.preferences.popularity_preference is None
