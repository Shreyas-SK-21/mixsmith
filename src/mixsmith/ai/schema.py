"""Structured schema for natural language curation specifications with constraint tiering and conflict detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ConstraintConflict:
    """Represents a direct conflict between requested constraints."""
    conflict_type: str
    description: str
    conflicting_parameters: list[str]
    suggested_resolution: str


@dataclass
class Ambiguity:
    """Represents an ambiguous instruction requiring clarification or default interpretation."""
    parameter: str
    query: str
    default_interpretation: str


@dataclass
class HardConstraints:
    """Non-negotiable requirements that must be strictly satisfied."""
    must_include_artists: list[str] = field(default_factory=list)
    must_exclude_artists: list[str] = field(default_factory=list)
    must_include_genres: list[str] = field(default_factory=list)
    must_exclude_genres: list[str] = field(default_factory=list)
    must_include_decades: list[str] = field(default_factory=list)
    min_artist_spacing: int = 1
    max_tracks_per_artist: int | None = None
    min_duration_minutes: int | None = None
    max_duration_minutes: int | None = None
    clean_only: bool = False
    explicit_only: bool = False


@dataclass
class SoftConstraints:
    """Optimization goals to satisfy as closely as possible without failing."""
    desired_genres: dict[str, float] = field(default_factory=dict)
    desired_decades: dict[str, float] = field(default_factory=dict)
    desired_themes: list[str] = field(default_factory=list)
    target_duration_minutes: int | None = None
    duration_tolerance_minutes: int = 10


@dataclass
class Preferences:
    """Subjective ranking signals and listening journey styles."""
    popularity_preference: str | None = None  # "hidden_gems", "hits", "balanced"
    tempo_energy_preference: str | None = None  # "mellow_to_energetic", "energetic_to_mellow", "steady"
    sort_journey: str | None = "declump"  # "declump", "chronological", "decade", "genre", "nostalgia"
    nostalgia_anchor_decade: str | None = None


@dataclass
class CurationSpecification:
    """Comprehensive structured curation specification."""
    name: str = "Curated Mix"
    description: str = ""
    hard_constraints: HardConstraints = field(default_factory=HardConstraints)
    soft_constraints: SoftConstraints = field(default_factory=SoftConstraints)
    preferences: Preferences = field(default_factory=Preferences)
    conflicts: list[ConstraintConflict] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)

    def validate_conflicts(self) -> list[ConstraintConflict]:
        """Detects contradictions between constraints before executing algorithms."""
        found_conflicts: list[ConstraintConflict] = []

        # 1. Clean only vs Explicit only
        if self.hard_constraints.clean_only and self.hard_constraints.explicit_only:
            found_conflicts.append(ConstraintConflict(
                conflict_type="mutually_exclusive_ratings",
                description="Requested both clean-only and explicit-only simultaneously.",
                conflicting_parameters=["clean_only", "explicit_only"],
                suggested_resolution="Remove one rating filter or allow both."
            ))

        # 2. Artist inclusion vs exclusion
        common_artists = set(a.lower() for a in self.hard_constraints.must_include_artists) & set(
            a.lower() for a in self.hard_constraints.must_exclude_artists
        )
        if common_artists:
            found_conflicts.append(ConstraintConflict(
                conflict_type="artist_inclusion_exclusion_clash",
                description=f"Artist(s) {list(common_artists)} appear in both must-include and must-exclude lists.",
                conflicting_parameters=["must_include_artists", "must_exclude_artists"],
                suggested_resolution="Remove the conflicting artists from the exclude list."
            ))

        # 3. Genre inclusion vs exclusion
        common_genres = set(g.lower() for g in self.hard_constraints.must_include_genres) & set(
            g.lower() for g in self.hard_constraints.must_exclude_genres
        )
        if common_genres:
            found_conflicts.append(ConstraintConflict(
                conflict_type="genre_inclusion_exclusion_clash",
                description=f"Genre(s) {list(common_genres)} appear in both must-include and must-exclude lists.",
                conflicting_parameters=["must_include_genres", "must_exclude_genres"],
                suggested_resolution="Remove conflicting genres from the exclude list."
            ))

        # 4. Min duration > Max duration
        min_d = self.hard_constraints.min_duration_minutes
        max_d = self.hard_constraints.max_duration_minutes
        if min_d and max_d and min_d > max_d:
            found_conflicts.append(ConstraintConflict(
                conflict_type="inverted_duration_bounds",
                description=f"Minimum duration ({min_d}m) cannot exceed maximum duration ({max_d}m).",
                conflicting_parameters=["min_duration_minutes", "max_duration_minutes"],
                suggested_resolution=f"Set max duration >= {min_d}m."
            ))

        self.conflicts = found_conflicts
        return found_conflicts

    def to_flat_spec(self) -> NaturalLanguageCurationSpec:
        """Converts tiered specification back to backward-compatible flat spec."""
        return NaturalLanguageCurationSpec(
            name=self.name,
            description=self.description,
            target_duration_minutes=self.soft_constraints.target_duration_minutes,
            artists_included=list(self.hard_constraints.must_include_artists),
            artists_excluded=list(self.hard_constraints.must_exclude_artists),
            genres_included=list(self.hard_constraints.must_include_genres) or list(self.soft_constraints.desired_genres.keys()),
            decades_included=list(self.hard_constraints.must_include_decades) or list(self.soft_constraints.desired_decades.keys()),
            themes_included=list(self.soft_constraints.desired_themes),
            min_artist_spacing=self.hard_constraints.min_artist_spacing,
            max_tracks_per_artist=self.hard_constraints.max_tracks_per_artist,
            sort_mode=self.preferences.sort_journey or "declump",
            clean_only=self.hard_constraints.clean_only,
            explicit_only=self.hard_constraints.explicit_only,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def get_json_schema(cls) -> dict[str, Any]:
        """Returns JSON schema for LLM tool calling and structured output."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "hard_constraints": {
                    "type": "object",
                    "properties": {
                        "must_include_artists": {"type": "array", "items": {"type": "string"}},
                        "must_exclude_artists": {"type": "array", "items": {"type": "string"}},
                        "must_include_genres": {"type": "array", "items": {"type": "string"}},
                        "must_include_decades": {"type": "array", "items": {"type": "string"}},
                        "min_artist_spacing": {"type": "integer"},
                        "max_tracks_per_artist": {"type": ["integer", "null"]},
                        "clean_only": {"type": "boolean"},
                        "explicit_only": {"type": "boolean"}
                    }
                },
                "soft_constraints": {
                    "type": "object",
                    "properties": {
                        "target_duration_minutes": {"type": ["integer", "null"]},
                        "desired_genres": {"type": "object", "additionalProperties": {"type": "number"}},
                        "desired_themes": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "preferences": {
                    "type": "object",
                    "properties": {
                        "popularity_preference": {"type": ["string", "null"], "enum": ["hidden_gems", "hits", "balanced"]},
                        "sort_journey": {"type": ["string", "null"], "enum": ["declump", "chronological", "decade", "genre", "nostalgia"]}
                    }
                }
            },
            "required": ["name", "hard_constraints"]
        }


# Backward-compatible alias
@dataclass
class NaturalLanguageCurationSpec:
    """Backward compatibility wrapper preserving flat spec accessors."""
    name: str = "Curated Mix"
    description: str = ""
    target_duration_minutes: int | None = None
    artists_included: list[str] = field(default_factory=list)
    artists_excluded: list[str] = field(default_factory=list)
    genres_included: list[str] = field(default_factory=list)
    decades_included: list[str] = field(default_factory=list)
    themes_included: list[str] = field(default_factory=list)
    min_artist_spacing: int = 1
    max_tracks_per_artist: int | None = None
    sort_mode: str | None = "declump"
    clean_only: bool = False
    explicit_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NaturalLanguageCurationSpec:
        return cls(
            name=data.get("name") or "Curated Mix",
            description=data.get("description") or "",
            target_duration_minutes=data.get("target_duration_minutes"),
            artists_included=data.get("artists_included") or [],
            artists_excluded=data.get("artists_excluded") or [],
            genres_included=data.get("genres_included") or [],
            decades_included=data.get("decades_included") or [],
            themes_included=data.get("themes_included") or [],
            min_artist_spacing=int(data.get("min_artist_spacing", 1)),
            max_tracks_per_artist=data.get("max_tracks_per_artist"),
            sort_mode=data.get("sort_mode") or "declump",
            clean_only=bool(data.get("clean_only", False)),
            explicit_only=bool(data.get("explicit_only", False))
        )

    def to_curation_spec(self) -> CurationSpecification:
        """Converts flat specification to tiered CurationSpecification."""
        hard = HardConstraints(
            must_include_artists=list(self.artists_included),
            must_exclude_artists=list(self.artists_excluded),
            must_include_genres=list(self.genres_included),
            must_include_decades=list(self.decades_included),
            min_artist_spacing=self.min_artist_spacing,
            max_tracks_per_artist=self.max_tracks_per_artist,
            clean_only=self.clean_only,
            explicit_only=self.explicit_only,
        )
        soft = SoftConstraints(
            desired_themes=list(self.themes_included),
            target_duration_minutes=self.target_duration_minutes,
        )
        prefs = Preferences(
            sort_journey=self.sort_mode or "declump",
        )
        spec = CurationSpecification(
            name=self.name,
            description=self.description,
            hard_constraints=hard,
            soft_constraints=soft,
            preferences=prefs,
        )
        spec.validate_conflicts()
        return spec

    @classmethod
    def get_json_schema(cls) -> dict[str, Any]:
        """Returns JSON schema for flat spec structured output or tool definitions."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "target_duration_minutes": {"type": ["integer", "null"]},
                "artists_included": {"type": "array", "items": {"type": "string"}},
                "artists_excluded": {"type": "array", "items": {"type": "string"}},
                "genres_included": {"type": "array", "items": {"type": "string"}},
                "decades_included": {"type": "array", "items": {"type": "string"}},
                "themes_included": {"type": "array", "items": {"type": "string"}},
                "min_artist_spacing": {"type": "integer"},
                "max_tracks_per_artist": {"type": ["integer", "null"]},
                "sort_mode": {
                    "type": ["string", "null"],
                    "enum": ["declump", "chronological", "newest", "decade", "genre", "nostalgia", "popularity", "gems"]
                },
                "clean_only": {"type": "boolean"},
                "explicit_only": {"type": "boolean"}
            },
            "required": ["name", "min_artist_spacing"]
        }
