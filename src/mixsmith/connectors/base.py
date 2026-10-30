"""Abstract base class for music streaming service connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from mixsmith.core.models import Playlist, Track


class MusicConnectorBase(ABC):
    """Abstract interface defining required capabilities for any music service backend."""

    @abstractmethod
    def get_me(self) -> Dict[str, Any]:
        """Fetches the current user profile."""
        pass

    @abstractmethod
    def list_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists user playlists."""
        pass

    @abstractmethod
    def get_playlist(self, identifier: str) -> Playlist:
        """Retrieves full playlist metadata and enriched tracks."""
        pass

    @abstractmethod
    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        tracks: Optional[List[Track]] = None
    ) -> Playlist:
        """Creates a new playlist on the music service."""
        pass

    @abstractmethod
    def delete_playlist(self, identifier: str) -> bool:
        """Deletes/unfollows a playlist."""
        pass
