"""Pytest fixtures and synthetic track fixtures for Mixsmith."""

import pytest

from mixsmith.core.models import Track


@pytest.fixture
def make_track():
    """Factory fixture for creating synthetic Track instances."""
    def _create(
        id: str = "track_1",
        name: str = "Test Track",
        artists: list = None,
        primary_artist: str = None,
        album: str = "Test Album",
        album_type: str = "album",
        release_date: str = "2020-01-01",
        release_year: int = 2020,
        duration_ms: int = 200000,
        popularity: int = 60,
        isrc: str = "",
        explicit: bool = False,
        primary_genre: str = "Rock",
        all_genres: list = None,
        theme: str = "Late Night Drive",
        era: str = "Modern 2020s",
        decade: str = "2020s",
        language: str = "English"
    ) -> Track:
        art_list = artists if artists is not None else ["Artist A"]
        prim_art = primary_artist or art_list[0]
        genres = all_genres if all_genres is not None else [primary_genre.lower()]
        return Track(
            id=id,
            uri=f"spotify:track:{id}",
            name=name,
            artists=art_list,
            primary_artist=prim_art,
            album=album,
            album_type=album_type,
            release_date=release_date,
            release_year=release_year,
            duration_ms=duration_ms,
            popularity=popularity,
            isrc=isrc,
            explicit=explicit,
            primary_genre=primary_genre,
            all_genres=genres,
            theme=theme,
            era=era,
            decade=decade,
            language=language
        )
    return _create


@pytest.fixture
def sample_tracks(make_track):
    """Generates a diverse set of synthetic tracks across artists, genres, and decades."""
    tracks = [
        make_track(id="t1", name="Midnight Drive", artists=["The Weeknd"], primary_genre="R&B / Soul", all_genres=["r&b", "soul"], theme="Late Night Drive", decade="2020s", popularity=85),
        make_track(id="t2", name="Blinding Lights", artists=["The Weeknd"], primary_genre="Pop", all_genres=["pop", "synthpop"], theme="Late Night Drive", decade="2020s", popularity=90),
        make_track(id="t3", name="Starboy", artists=["The Weeknd", "Daft Punk"], primary_genre="R&B / Soul", all_genres=["r&b", "electronic"], theme="Party & Club", decade="2010s", popularity=80),
        make_track(id="t4", name="Glimpse of Us", artists=["Joji"], primary_genre="Indie / Alternative", all_genres=["indie", "lo-fi"], theme="Heartbreak & Melancholy", decade="2020s", popularity=75),
        make_track(id="t5", name="SLOW DANCING IN THE DARK", artists=["Joji"], primary_genre="Indie / Alternative", all_genres=["indie", "alternative"], theme="Late Night Drive", decade="2010s", popularity=82),
        make_track(id="t6", name="Do I Wanna Know?", artists=["Arctic Monkeys"], primary_genre="Rock", all_genres=["rock"], theme="Late Night Drive", decade="2010s", popularity=88),
        make_track(id="t7", name="505", artists=["Arctic Monkeys"], primary_genre="Indie / Alternative", all_genres=["indie", "alternative"], theme="Chill & Coffee Shop", decade="2000s", popularity=84),
        make_track(id="t8", name="Smells Like Teen Spirit", artists=["Nirvana"], primary_genre="Rock", all_genres=["rock", "grunge"], theme="High Voltage Rock", decade="90s", release_year=1991, popularity=82),
        make_track(id="t9", name="Come As You Are", artists=["Nirvana"], primary_genre="Rock", all_genres=["rock", "grunge"], theme="Chill & Coffee Shop", decade="90s", release_year=1991, popularity=78),
        make_track(id="t10", name="Lithium", artists=["Nirvana"], primary_genre="Rock", all_genres=["rock", "grunge"], theme="High Voltage Rock", decade="90s", release_year=1991, popularity=74),
    ]
    return tracks
