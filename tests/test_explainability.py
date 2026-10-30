"""Unit tests for Curation Explainability Engine."""

import json
import pytest
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints


def test_curation_explanation_generation(sample_tracks):
    """Verifies that curation produces a complete, deterministic explanation report."""
    engine = ConstraintSequencingEngine()
    constraints = CurationConstraints(
        min_artist_spacing=1,
        max_tracks_per_artist=2,
        sort_mode="declump"
    )

    plan = engine.curate(sample_tracks, constraints, playlist_name="Explainability Test")

    assert plan.explanation is not None
    exp = plan.explanation

    assert exp.playlist_name == "Explainability Test"
    assert exp.source_track_count == len(sample_tracks)
    assert exp.final_track_count == len(plan.tracks)
    assert len(exp.constraint_audits) > 0
    assert len(exp.track_decisions) == len(sample_tracks)

    # Test Markdown formatting
    md = exp.to_markdown()
    assert "# Curation Explanation Report: Explainability Test" in md
    assert "Independent Constraint Audits" in md
    assert "Track Sequencing Decisions" in md

    # Test JSON serialization
    json_str = exp.to_json()
    parsed = json.loads(json_str)
    assert parsed["playlist_name"] == "Explainability Test"
    assert "track_decisions" in parsed
    assert len(parsed["track_decisions"]) == len(sample_tracks)
