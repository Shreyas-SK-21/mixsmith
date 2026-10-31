"""Tests for V0.3.2 feature correctness: energy progression, duration bounds, and metadata provenance."""

import pytest

from mixsmith.ai.schema import CurationSpecification, HardConstraints, SoftConstraints
from mixsmith.core.exceptions import InfeasibleConstraintError
from mixsmith.core.journeys import compute_track_energy, sequence_energy_progression
from mixsmith.core.models import Track
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints
from mixsmith.core.validation import PlaylistValidator
from mixsmith.utils.metadata import (
    MetadataConfidence,
    MetadataProvenance,
    infer_era_and_decade,
    infer_primary_genre,
    infer_theme,
)


def make_track(
    id: str,
    name: str = "Track",
    artist: str = "Artist",
    primary_genre: str = "Pop",
    theme: str = "Eclectic & Diverse",
    duration_ms: int = 180000,
    popularity: int | None = None
) -> Track:
    return Track(
        id=id,
        uri=f"spotify:track:{id}",
        name=name,
        artists=[artist],
        primary_artist=artist,
        primary_genre=primary_genre,
        theme=theme,
        duration_ms=duration_ms,
        popularity=popularity
    )


def test_energy_progression_mellow_to_energetic():
    """Verifies that sequence_energy_progression sequences tracks from low to high energy without using popularity."""
    t_chill = make_track("1", name="Morning Breeze", theme="Chill & Coffee Shop", primary_genre="Acoustic", popularity=90)
    t_drive = make_track("2", name="Midnight Cruiser", theme="Late Night Drive", primary_genre="Indie / Alternative", popularity=10)
    t_rave = make_track("3", name="Thunderstorm Remix", theme="Party & Club", primary_genre="Electronic / Dance", popularity=50)

    e1, _, _ = compute_track_energy(t_chill)
    e2, _, _ = compute_track_energy(t_drive)
    e3, _, _ = compute_track_energy(t_rave)

    assert e1 < e2 < e3

    tracks = [t_rave, t_chill, t_drive]
    ordered = sequence_energy_progression(tracks, direction="mellow_to_energetic")
    assert [t.id for t in ordered] == ["1", "2", "3"]

    reverse_ordered = sequence_energy_progression(tracks, direction="energetic_to_mellow")
    assert [t.id for t in reverse_ordered] == ["3", "2", "1"]


def test_duration_bounds_infeasible_specification_rejected():
    """Verifies that min_duration > max_duration raises an immediate InfeasibleConstraintError."""
    engine = ConstraintSequencingEngine()
    tracks = [make_track("t1", duration_ms=180000), make_track("t2", duration_ms=180000)]

    constraints = CurationConstraints(
        min_duration_minutes=60,
        max_duration_minutes=30
    )

    with pytest.raises(InfeasibleConstraintError) as exc_info:
        engine.curate(tracks, constraints)

    assert "cannot exceed max_duration_minutes" in str(exc_info.value)
    assert exc_info.value.constraint == "duration_bounds"


def test_duration_bounds_insufficient_library_rejected():
    """Verifies that requesting a minimum duration exceeding the entire available library raises an error."""
    engine = ConstraintSequencingEngine()
    # 2 tracks of 3 mins = 6 mins total
    tracks = [make_track("t1", duration_ms=180000), make_track("t2", duration_ms=180000)]

    constraints = CurationConstraints(
        min_duration_minutes=30
    )

    with pytest.raises(InfeasibleConstraintError) as exc_info:
        engine.curate(tracks, constraints)

    assert "less than required minimum" in str(exc_info.value)
    assert exc_info.value.constraint == "min_duration"


def test_duration_bounds_validation_hard_constraint():
    """Verifies that duration bounds are audited as hard constraints by PlaylistValidator."""
    # 2 tracks = 6 minutes total
    tracks = [make_track("t1", duration_ms=180000), make_track("t2", duration_ms=180000)]

    # Require between 10m and 30m
    report = PlaylistValidator.validate_playlist(
        original_tracks=tracks,
        final_tracks=tracks,
        min_duration_minutes=10,
        max_duration_minutes=30
    )

    assert report.is_valid is False
    bounds_result = next(r for r in report.results if r.name == "duration_bounds")
    assert bounds_result.satisfied is False
    assert bounds_result.severity == "error"
    assert "Duration bounds violation" in bounds_result.details


def test_spec_detects_duration_bounds_conflicts():
    """Verifies that CurationSpecification detects target duration clashes with hard min/max bounds."""
    spec = CurationSpecification(
        name="Clashing Bounds",
        hard_constraints=HardConstraints(min_duration_minutes=45, max_duration_minutes=60),
        soft_constraints=SoftConstraints(target_duration_minutes=30)
    )

    conflicts = spec.validate_conflicts()
    assert any(c.conflict_type == "target_duration_below_minimum" for c in conflicts)


def test_metadata_provenance_and_confidence():
    """Verifies that confidence-aware inference results are correctly computed and preserved."""
    genre_res = infer_primary_genre(["psychedelic rock", "space rock"])
    assert genre_res.confidence in (MetadataConfidence.HIGH, MetadataConfidence.MEDIUM)
    assert genre_res.provenance == MetadataProvenance.GENRE_ASSOCIATION
    assert genre_res.value == "Rock"

    era_res, decade_res, year = infer_era_and_decade("1973-03-01")
    assert decade_res.value == "70s"
    assert era_res.confidence == MetadataConfidence.HIGH
    assert year == 1973

    theme_res = infer_theme("Relaxing by the Fire", ["ambient", "drone"], "Ambient", 2021, None, 180000)
    assert theme_res.confidence in (MetadataConfidence.HIGH, MetadataConfidence.MEDIUM)
    assert theme_res.value in ("Chill & Coffee Shop", "Focus & Study", "Eclectic & Diverse")


def test_unrated_popularity_handled_safely():
    """Verifies that tracks with popularity=None do not crash curation algorithms."""
    engine = ConstraintSequencingEngine()
    tracks = [
        make_track(f"t{i}", artist=f"Artist_{i % 3}", popularity=None, duration_ms=180000)
        for i in range(12)
    ]

    constraints = CurationConstraints(
        min_artist_spacing=2,
        max_tracks_per_artist=3,
        target_duration_minutes=15
    )

    plan = engine.curate(tracks, constraints)
    assert plan.final_track_count > 0
    assert all(t.popularity is None for t in plan.tracks)
