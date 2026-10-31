"""Domain models for Mixsmith."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Track:
    """Represents an enriched music track with human dimensions."""
    id: str
    uri: str
    name: str
    artists: list[str]
    primary_artist: str = ""
    album: str = ""
    album_type: str = "album"
    release_date: str = ""
    release_year: int | None = None
    duration_ms: int = 0
    popularity: int | None = None
    isrc: str = ""
    explicit: bool = False
    primary_genre: str = "Other / Unclassified"
    all_genres: list[str] = field(default_factory=list)
    theme: str = "Eclectic & Diverse"
    era: str = "Contemporary"
    decade: str = "2020s"
    language: str = "English"
    track_number: int = 1
    disc_number: int = 1
    added_at: str = ""
    added_by: str = ""
    spotify_url: str = ""
    metadata_confidence: dict[str, str] = field(default_factory=dict)
    metadata_provenance: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.primary_artist and self.artists:
            self.primary_artist = self.artists[0]
        if not self.uri and self.id:
            self.uri = f"spotify:track:{self.id}"
        if not self.spotify_url and self.id:
            self.spotify_url = f"https://open.spotify.com/track/{self.id}"

    @property
    def artist_display(self) -> str:
        """Formatted string of all artists."""
        return ", ".join(self.artists) if self.artists else self.primary_artist or "Unknown"

    @property
    def all_artists(self) -> list[str]:
        """List of all artists (primary and co-artists)."""
        return list(self.artists)

    @property
    def duration_formatted(self) -> str:
        """MM:SS formatted duration string."""
        mins = self.duration_ms // 60000
        secs = (self.duration_ms % 60000) // 1000
        return f"{mins}:{secs:02d}"

    @property
    def is_clean(self) -> bool:
        return not self.explicit

    @property
    def is_explicit(self) -> bool:
        return self.explicit

    def has_artist(self, artist_name: str, case_sensitive: bool = False) -> bool:
        """Checks if a given artist is in primary or co-artists."""
        target = artist_name if case_sensitive else artist_name.lower().strip()
        for a in self.artists:
            curr = a if case_sensitive else a.lower()
            if target in curr or curr in target:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Serializes track to dictionary format."""
        return {
            "id": self.id,
            "uri": self.uri,
            "name": self.name,
            "Track Name": self.name,
            "artists": self.artists,
            "Artist Name(s)": self.artist_display,
            "primary_artist": self.primary_artist,
            "album": self.album,
            "Album Name": self.album,
            "Album Type": self.album_type,
            "release_date": self.release_date,
            "Release Date": self.release_date,
            "release_year": self.release_year,
            "Release Year": self.release_year,
            "duration_ms": self.duration_ms,
            "Duration (ms)": self.duration_ms,
            "duration_formatted": self.duration_formatted,
            "Duration": self.duration_formatted,
            "popularity": self.popularity,
            "Popularity Score": self.popularity if self.popularity is not None else "",
            "isrc": self.isrc,
            "ISRC": self.isrc,
            "explicit": self.explicit,
            "Explicit": self.explicit,
            "is_clean": self.is_clean,
            "is_explicit": self.is_explicit,
            "primary_genre": self.primary_genre,
            "Primary Genre": self.primary_genre,
            "genres": self.all_genres,
            "All Genres": ", ".join(self.all_genres),
            "theme": self.theme,
            "Theme / Vibe": self.theme,
            "era": self.era,
            "Era / Decade": f"{self.era} ({self.decade})",
            "decade": self.decade,
            "language": self.language,
            "Language / Region": self.language,
            "track_number": self.track_number,
            "Track Number": self.track_number,
            "disc_number": self.disc_number,
            "Disc Number": self.disc_number,
            "added_at": self.added_at,
            "Added At": self.added_at,
            "added_by": self.added_by,
            "Added By": self.added_by,
            "spotify_url": self.spotify_url,
            "Spotify URL": self.spotify_url,
            "metadata_confidence": dict(self.metadata_confidence),
            "metadata_provenance": dict(self.metadata_provenance),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Track:
        """Constructs a Track instance from dictionary or legacy CSV row."""
        # Normalize ID & URI
        uri = data.get("uri") or data.get("Track URI") or ""
        track_id = data.get("id") or data.get("Track ID") or ""
        if not track_id and uri and uri.startswith("spotify:track:"):
            track_id = uri.split(":")[-1]

        # Normalize Name
        name = data.get("name") or data.get("Track Name") or "Unknown Track"

        # Normalize Artists
        raw_artists = data.get("artists") or data.get("Artist Name(s)") or []
        if isinstance(raw_artists, str):
            artists = [a.strip() for a in raw_artists.split(",") if a.strip()]
        elif isinstance(raw_artists, list):
            artists = [str(a).strip() for a in raw_artists if str(a).strip()]
        else:
            artists = []
        if not artists:
            artists = ["Unknown Artist"]

        primary_artist = data.get("primary_artist") or artists[0]

        # Normalize Duration
        dur_ms = data.get("duration_ms") or data.get("Duration (ms)") or 0
        try:
            dur_ms = int(dur_ms)
        except (ValueError, TypeError):
            dur_ms = 0

        # Normalize Popularity (distinguish None from 0)
        raw_pop = data.get("popularity")
        if raw_pop is None:
            raw_pop = data.get("Popularity Score")
        if raw_pop is None:
            raw_pop = data.get("Popularity")

        pop: int | None = None
        if raw_pop is not None and str(raw_pop).strip() != "":
            try:
                pop = int(raw_pop)
            except (ValueError, TypeError):
                pop = None

        # Normalize Release Year
        rel_date = str(data.get("release_date") or data.get("Release Date") or "")
        rel_year = data.get("release_year") or data.get("Release Year")
        if rel_year is not None:
            try:
                rel_year = int(rel_year)
            except (ValueError, TypeError):
                rel_year = None
        if rel_year is None and rel_date:
            m = re.match(r"^(\d{4})", rel_date)
            if m:
                rel_year = int(m.group(1))

        # Explicit / Clean
        explicit_val = data.get("explicit") or data.get("Explicit")
        if isinstance(explicit_val, str):
            explicit = explicit_val.strip().lower() in ("true", "1", "yes", "explicit")
        else:
            explicit = bool(explicit_val)

        # Genres
        genres = data.get("genres") or data.get("all_genres") or data.get("All Genres") or []
        if isinstance(genres, str):
            genres_list = [g.strip() for g in genres.split(",") if g.strip()]
        elif isinstance(genres, list):
            genres_list = [str(g).strip() for g in genres if str(g).strip()]
        else:
            genres_list = []

        return cls(
            id=track_id,
            uri=uri,
            name=name,
            artists=artists,
            primary_artist=primary_artist,
            album=data.get("album") or data.get("Album Name") or "",
            album_type=data.get("album_type") or data.get("Album Type") or "album",
            release_date=rel_date,
            release_year=rel_year,
            duration_ms=dur_ms,
            popularity=pop,
            isrc=data.get("isrc") or data.get("ISRC") or "",
            explicit=explicit,
            primary_genre=data.get("primary_genre") or data.get("Primary Genre") or "Other / Unclassified",
            all_genres=genres_list,
            theme=data.get("theme") or data.get("Theme / Vibe") or "Eclectic & Diverse",
            era=data.get("era") or "Contemporary",
            decade=data.get("decade") or "2020s",
            language=data.get("language") or data.get("Language / Region") or "English",
            track_number=int(data.get("track_number") or data.get("Track Number") or 1),
            disc_number=int(data.get("disc_number") or data.get("Disc Number") or 1),
            added_at=data.get("added_at") or data.get("Added At") or "",
            added_by=data.get("added_by") or data.get("Added By") or "",
            spotify_url=data.get("spotify_url") or data.get("Spotify URL") or "",
            metadata_confidence=dict(data.get("metadata_confidence") or {}),
            metadata_provenance=dict(data.get("metadata_provenance") or {})
        )


@dataclass
class Playlist:
    """Represents a music playlist."""
    id: str
    name: str
    description: str = ""
    owner: str = ""
    public: bool = False
    tracks: list[Track] = field(default_factory=list)
    total_tracks: int = 0
    url: str = ""

    def __post_init__(self):
        if not self.total_tracks:
            self.total_tracks = len(self.tracks)

    @property
    def total_duration_ms(self) -> int:
        return sum(t.duration_ms for t in self.tracks)

    @property
    def total_duration_formatted(self) -> str:
        total_seconds = self.total_duration_ms // 1000
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        if hours > 0:
            return f"{hours} hr {mins} min"
        return f"{mins} min"


@dataclass
class ConstraintResult:
    """Outcome of an evaluated sequencing or filtering constraint."""
    name: str
    satisfied: bool
    details: str
    severity: str = "info"  # "info", "warning", "error"


@dataclass
class CurationPlan:
    """Result of a playlist curation operation with verification and diff report."""
    playlist_name: str
    tracks: list[Track]
    initial_track_count: int
    final_track_count: int
    constraints_evaluated: list[ConstraintResult] = field(default_factory=list)
    diff_summary: str = ""
    explanation: Any | None = None

    @property
    def all_satisfied(self) -> bool:
        return all(c.satisfied for c in self.constraints_evaluated if c.severity == "error")


@dataclass
class DuplicateGroup:
    """A cluster of duplicate or variant recordings."""
    canonical_track: Track
    variants: list[Track]
    category: str  # "exact", "remaster", "live", "acoustic", "radio_edit", "deluxe"
    recommended_action: str = "keep_canonical"
