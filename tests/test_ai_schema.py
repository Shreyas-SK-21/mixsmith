"""Unit tests for Natural Language Curation Schema and Parser."""

import pytest
from mixsmith.ai.parser import parse_natural_language_heuristics
from mixsmith.ai.schema import NaturalLanguageCurationSpec


def test_schema_serialization():
    """Verifies dataclass to dict and from dict conversion."""
    spec = NaturalLanguageCurationSpec(
        name="Night Ride",
        target_duration_minutes=120,
        artists_included=["The Weeknd", "Joji"],
        min_artist_spacing=5,
        themes_included=["Late Night Drive"]
    )
    d = spec.to_dict()
    assert d["name"] == "Night Ride"
    assert d["target_duration_minutes"] == 120
    assert d["min_artist_spacing"] == 5

    spec_restored = NaturalLanguageCurationSpec.from_dict(d)
    assert spec_restored.name == spec.name
    assert spec_restored.min_artist_spacing == spec.min_artist_spacing


def test_json_schema_validity():
    """Verifies that the generated JSON schema has required structure."""
    schema = NaturalLanguageCurationSpec.get_json_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "min_artist_spacing" in schema["properties"]
    assert "target_duration_minutes" in schema["properties"]


def test_parse_natural_language_heuristics():
    """Tests deterministic heuristic extraction on user example."""
    prompt = (
        "Create a two-hour late-night driving playlist with The Weeknd, Joji and Arctic Monkeys. "
        "Avoid repeating artists within five tracks. Start mellow and gradually become more energetic."
    )
    spec = parse_natural_language_heuristics(prompt)

    assert spec.target_duration_minutes == 120
    assert "Late Night Drive" in spec.themes_included
    assert spec.min_artist_spacing == 5
    assert spec.sort_mode in ("gems", "declump")
