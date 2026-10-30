"""Abstract base class for music streaming service connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mixsmith.core.models import Playlist, Track


class MusicConnectorBase(ABC):
    """Abstract interface defining required capabilities for any music service backend."""

    @abstractmethod
    def get_me(self) -> dict[str, Any]:
        """Fetches the current user profile."""

    @abstractmethod
    def list_playlists(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lists user playlists."""

    @abstractmethod
    def get_playlist(self, identifier: str) -> Playlist:
        """Retrieves full playlist metadata and enriched tracks."""

    @abstractmethod
    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        tracks: list[Track] | None = None
    ) -> Playlist:
        """Creates a new playlist on the music service."""

    @abstractmethod
    def delete_playlist(self, identifier: str) -> bool:
        """Deletes/unfollows a playlist."""
