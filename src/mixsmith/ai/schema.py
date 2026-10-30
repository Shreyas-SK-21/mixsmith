"""Structured schema for natural language curation specifications."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NaturalLanguageCurationSpec:
    """Structured specification produced from natural-language instructions."""
    name: str = "Curated Mix"
    description: str = ""
    target_duration_minutes: Optional[int] = None
    artists_included: List[str] = field(default_factory=list)
    artists_excluded: List[str] = field(default_factory=list)
    genres_included: List[str] = field(default_factory=list)
    decades_included: List[str] = field(default_factory=list)
    themes_included: List[str] = field(default_factory=list)
    min_artist_spacing: int = 1
    max_tracks_per_artist: Optional[int] = None
    sort_mode: Optional[str] = "declump"
    clean_only: bool = False
    explicit_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NaturalLanguageCurationSpec:
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

    @classmethod
    def get_json_schema(cls) -> Dict[str, Any]:
        """Returns JSON schema for LLM structured output or tool definitions."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short, creative title for the generated playlist."
                },
                "description": {
                    "type": "string",
                    "description": "Short description of the playlist vibe or journey."
                },
                "target_duration_minutes": {
                    "type": ["integer", "null"],
                    "description": "Target runtime in minutes (e.g. 120 for 2 hours)."
                },
                "artists_included": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Artist names explicitly requested by user."
                },
                "artists_excluded": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Artist names to filter out."
                },
                "genres_included": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Genres requested (e.g., Rock, Shoegaze, Hip-Hop, Pop, Indie)."
                },
                "decades_included": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Decades requested (e.g., 90s, 80s, 2000s, 2010s, 2020s)."
                },
                "themes_included": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Themes/vibes (e.g., Late Night Drive, Workout, Chill & Coffee Shop, Party)."
                },
                "min_artist_spacing": {
                    "type": "integer",
                    "description": "Minimum tracks between appearances of the same artist (default: 1)."
                },
                "max_tracks_per_artist": {
                    "type": ["integer", "null"],
                    "description": "Maximum number of tracks allowed for any single artist."
                },
                "sort_mode": {
                    "type": ["string", "null"],
                    "enum": [
                        "declump",
                        "chronological",
                        "newest",
                        "decade",
                        "genre",
                        "nostalgia",
                        "popularity",
                        "gems"
                    ],
                    "description": "Sequencing style to apply."
                },
                "clean_only": {"type": "boolean"},
                "explicit_only": {"type": "boolean"}
            },
            "required": ["name", "min_artist_spacing"]
        }
