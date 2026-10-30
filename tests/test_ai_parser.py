"""Tests for advanced natural language curation parsing and conflict detection."""

import pytest
from mixsmith.ai.parser import (
    OfflineHeuristicProvider,
    execute_natural_language_curation,
    parse_natural_language_heuristics,
    parse_natural_language_to_spec,
)
from mixsmith.ai.schema import (
    CurationSpecification,
    HardConstraints,
    SoftConstraints,
    Preferences,
)
from mixsmith.core.models import Track


def test_parse_tiered_constraints():
    prompt = (
        "Make a 90-minute playlist with shoegaze and indie rock. "
        "Include Slowdive and Alvvays, but exclude Coldplay. "
        "Max 2 songs per artist. Spacing of 3 tracks. Keep it clean only."
    )
    spec = parse_natural_language_to_spec(prompt)

    assert spec.soft_constraints.target_duration_minutes == 90
    assert "Shoegaze" in spec.hard_constraints.must_include_genres
    assert "Indie Rock" in spec.hard_constraints.must_include_genres
    assert "Slowdive" in spec.hard_constraints.must_include_artists
    assert "Alvvays" in spec.hard_constraints.must_include_artists
    assert "Coldplay" in spec.hard_constraints.must_exclude_artists
    assert spec.hard_constraints.max_tracks_per_artist == 2
    assert spec.hard_constraints.min_artist_spacing == 3
    assert spec.hard_constraints.clean_only is True
    assert len(spec.conflicts) == 0


def test_detect_conflict_clean_and_explicit():
    spec = CurationSpecification(
        hard_constraints=HardConstraints(clean_only=True, explicit_only=True)
    )
    conflicts = spec.validate_conflicts()
    assert len(conflicts) >= 1
    assert any(c.conflict_type == "mutually_exclusive_ratings" for c in conflicts)


def test_detect_conflict_artist_inclusion_and_exclusion():
    spec = CurationSpecification(
        hard_constraints=HardConstraints(
            must_include_artists=["Radiohead", "Blur"],
            must_exclude_artists=["Radiohead", "Oasis"]
        )
    )
    conflicts = spec.validate_conflicts()
    assert len(conflicts) >= 1
    assert any(c.conflict_type == "artist_inclusion_exclusion_clash" for c in conflicts)


def test_detect_conflict_duration_bounds():
    spec = CurationSpecification(
        hard_constraints=HardConstraints(
            min_duration_minutes=120,
            max_duration_minutes=60
        )
    )
    conflicts = spec.validate_conflicts()
    assert len(conflicts) >= 1
    assert any(c.conflict_type == "inverted_duration_bounds" for c in conflicts)


def test_offline_provider_interface():
    provider = OfflineHeuristicProvider()
    spec = provider.parse_instruction("A 2 hour workout mix with rock and hip-hop")
    assert spec.soft_constraints.target_duration_minutes == 120
    assert "Workout / Gym" in spec.soft_constraints.desired_themes
    assert "Rock" in spec.hard_constraints.must_include_genres


def test_execute_curation_raises_on_conflict(sample_tracks):
    spec = CurationSpecification(
        hard_constraints=HardConstraints(clean_only=True, explicit_only=True)
    )
    with pytest.raises(ValueError, match="Constraint conflict detected"):
        execute_natural_language_curation(sample_tracks, prompt="", spec_override=spec)
