"""Synthetic library generation and exact backtracking oracle for algorithm benchmarking."""

from __future__ import annotations

import math
import random

from mixsmith.core.models import Track


def generate_synthetic_library(
    n_tracks: int,
    n_unique_artists: int = 15,
    zipf_param: float = 1.3,
    collaboration_rate: float = 0.25,
    seed: int = 42
) -> list[Track]:
    """
    Generates a realistic synthetic music library with Zipf-distributed artist frequencies
    and multi-artist collaborations.
    """
    rng = random.Random(seed)
    artist_pool = [f"Artist_{i:02d}" for i in range(1, n_unique_artists + 1)]

    # Zipf weights for artists: w_k = 1 / (k ^ zipf_param)
    weights = [1.0 / (math.pow(i + 1, zipf_param)) for i in range(n_unique_artists)]
    total_w = sum(weights)
    prob_dist = [w / total_w for w in weights]

    genres_pool = [
        "Rock", "Indie / Alternative", "Pop", "Hip-Hop / Rap",
        "Electronic / Dance", "R&B / Soul", "Shoegaze / Dream Pop"
    ]

    tracks: list[Track] = []
    for idx in range(1, n_tracks + 1):
        # Pick primary artist according to Zipf distribution
        primary = rng.choices(artist_pool, weights=prob_dist, k=1)[0]
        artists = [primary]

        # Collaboration multi-artist check
        if rng.random() < collaboration_rate:
            co_artist = rng.choice([a for a in artist_pool if a != primary])
            artists.append(co_artist)

        # Durations around 210s (3.5 mins) with variance
        duration_s = max(60, int(rng.gauss(210, 45)))
        primary_genre = rng.choice(genres_pool)
        year = rng.randint(1990, 2024)

        track = Track(
            id=f"syn_track_{idx:04d}",
            uri=f"spotify:track:syn{idx:04d}",
            name=f"Synthetic Track #{idx}",
            artists=artists,
            primary_artist=primary,
            album=f"Album by {primary}",
            release_date=f"{year}-06-15",
            release_year=year,
            duration_ms=duration_s * 1000,
            popularity=rng.randint(10, 95),
            primary_genre=primary_genre,
            all_genres=[primary_genre.lower()],
            isrc=f"USSYN{year % 100}{idx:05d}"
        )
        tracks.append(track)

    return tracks


def exact_backtracking_declumper(
    tracks: list[Track],
    min_spacing: int = 1
) -> list[Track] | None:
    """
    Exact backtracking solver oracle for small track sets (N <= 15).
    Guarantees finding a zero-violation schedule if one mathematically exists.
    Returns None if no valid permutation satisfies the requested spacing.
    """
    n = len(tracks)
    if n <= 1:
        return list(tracks)

    used = [False] * n
    current_schedule: list[Track] = []

    def can_place(track: Track, pos: int) -> bool:
        start_check = max(0, pos - min_spacing)
        track_artists = set(a.lower() for a in track.all_artists)
        for prev_track in current_schedule[start_check:pos]:
            prev_artists = set(a.lower() for a in prev_track.all_artists)
            if track_artists & prev_artists:
                return False
        return True

    def backtrack(pos: int) -> bool:
        if pos == n:
            return True

        for i in range(n):
            if not used[i]:
                candidate = tracks[i]
                if can_place(candidate, pos):
                    used[i] = True
                    current_schedule.append(candidate)
                    if backtrack(pos + 1):
                        return True
                    current_schedule.pop()
                    used[i] = False
        return False

    if backtrack(0):
        return current_schedule
    return None
