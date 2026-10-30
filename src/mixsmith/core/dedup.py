"""Intelligent music deduplication and alternative version detection."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from mixsmith.core.models import DuplicateGroup, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.dedup")

# Regex patterns for music version categorization
REMASTER_PATTERN = re.compile(r"\b(\d{4}\s+)?remaster(ed)?(\s+version)?\b|\b\d{4}\s+mix\b", re.IGNORECASE)
LIVE_PATTERN = re.compile(r"\b(live|recorded live|in concert|live at|live from)\b", re.IGNORECASE)
ACOUSTIC_PATTERN = re.compile(r"\b(acoustic|unplugged|stripped)\b", re.IGNORECASE)
RADIO_EDIT_PATTERN = re.compile(r"\b(radio edit|single edit|clean version|clean edit)\b", re.IGNORECASE)
DELUXE_PATTERN = re.compile(r"\b(deluxe|expanded|anniversary|collector|special edition)\b", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Strips parenthetical metadata, punctuation, and whitespace for fuzzy comparison."""
    # Remove contents inside parentheses/brackets that denote versions
    t = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title)
    # Remove hyphenated version suffixes (e.g. " - 2011 Remaster", " - Live at ...")
    t = re.sub(
        r"\s*-\s*(.*?(?:remaster|live|acoustic|radio|deluxe|version|edit|mix|mono|stereo)).*$",
        "",
        t,
        flags=re.IGNORECASE
    )
    # Remove feat/ft
    t = re.sub(r"\b(feat|ft)\.?\s+.*$", "", t, flags=re.IGNORECASE)
    # Remove punctuation
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.lower().split())


def classify_track_variant(track: Track) -> str:
    """Classifies what kind of version/variant this track is."""
    name = track.name
    album = track.album

    if LIVE_PATTERN.search(name):
        return "live"
    if ACOUSTIC_PATTERN.search(name):
        return "acoustic"
    if REMASTER_PATTERN.search(name):
        return "remaster"
    if RADIO_EDIT_PATTERN.search(name):
        return "radio_edit"
    if DELUXE_PATTERN.search(album):
        return "deluxe"
    return "standard"


def find_duplicates(tracks: List[Track]) -> List[DuplicateGroup]:
    """
    Identifies all duplicate clusters in a playlist, distinguishing between exact
    duplicates, remasters, live cuts, acoustic renditions, and radio edits.
    """
    groups: List[DuplicateGroup] = []

    # 1. First pass: group by ISRC if available (exact recording match)
    isrc_buckets: Dict[str, List[Track]] = defaultdict(list)
    remaining_tracks = []

    for t in tracks:
        if t.isrc:
            isrc_buckets[t.isrc.strip().upper()].append(t)
        else:
            remaining_tracks.append(t)

    consumed_ids: Set[str] = set()

    for isrc, cluster in isrc_buckets.items():
        if len(cluster) > 1:
            canonical = cluster[0]
            variants = cluster[1:]
            groups.append(DuplicateGroup(
                canonical_track=canonical,
                variants=variants,
                category="exact"
            ))
            for tr in cluster:
                consumed_ids.add(tr.id)
        else:
            remaining_tracks.extend(cluster)

    # 2. Second pass: fuzzy match by normalized title + primary artist
    title_artist_buckets: Dict[Tuple[str, str], List[Track]] = defaultdict(list)
    for t in remaining_tracks:
        if t.id in consumed_ids:
            continue
        norm_title = normalize_title(t.name)
        norm_artist = t.primary_artist.lower().strip() if t.primary_artist else ""
        if norm_title and norm_artist:
            title_artist_buckets[(norm_title, norm_artist)].append(t)

    for (norm_title, norm_artist), cluster in title_artist_buckets.items():
        if len(cluster) > 1:
            # Choose canonical: prefer standard studio version with highest popularity
            def rank_track(item: Track) -> Tuple[int, int]:
                variant = classify_track_variant(item)
                scores = {"standard": 5, "remaster": 4, "deluxe": 3, "radio_edit": 2, "acoustic": 1, "live": 0}
                return (scores.get(variant, 0), item.popularity)

            sorted_cluster = sorted(cluster, key=rank_track, reverse=True)
            canonical = sorted_cluster[0]
            variants = sorted_cluster[1:]

            primary_category = "variant"
            if all(classify_track_variant(v) == "exact" or (abs(v.duration_ms - canonical.duration_ms) < 3000 and classify_track_variant(v) == "standard") for v in variants):
                primary_category = "exact"
            elif any(classify_track_variant(v) == "remaster" for v in variants):
                primary_category = "remaster"
            elif any(classify_track_variant(v) == "live" for v in variants):
                primary_category = "live"
            elif any(classify_track_variant(v) == "acoustic" for v in variants):
                primary_category = "acoustic"

            groups.append(DuplicateGroup(
                canonical_track=canonical,
                variants=variants,
                category=primary_category
            ))

    return groups


def deduplicate_tracks(
    tracks: List[Track],
    strategy: str = "exact_only"
) -> Tuple[List[Track], List[DuplicateGroup]]:
    """
    Applies deduplication strategy:
    - 'exact_only': Discards only identical recordings/ISRCs, preserving live/acoustic/remastered alternatives.
    - 'keep_original': Keeps standard original studio cut, dropping remasters, live, acoustic, radio edits.
    - 'keep_remaster': Prefers newest remastered cuts.
    - 'keep_all': Drops nothing, returns identified duplicate groups for review.
    """
    duplicate_groups = find_duplicates(tracks)

    if strategy == "keep_all" or not duplicate_groups:
        return list(tracks), duplicate_groups

    tracks_to_remove: Set[str] = set()

    for g in duplicate_groups:
        if strategy == "exact_only":
            if g.category == "exact":
                for v in g.variants:
                    tracks_to_remove.add(v.id)
        elif strategy == "keep_original":
            for v in g.variants:
                tracks_to_remove.add(v.id)
        elif strategy == "keep_remaster":
            remasters = [t for t in [g.canonical_track] + g.variants if classify_track_variant(t) == "remaster"]
            if remasters:
                chosen = max(remasters, key=lambda t: t.release_year or 0)
                all_in_group = [g.canonical_track] + g.variants
                for t in all_in_group:
                    if t.id != chosen.id:
                        tracks_to_remove.add(t.id)
            else:
                for v in g.variants:
                    tracks_to_remove.add(v.id)

    deduped = [t for t in tracks if t.id not in tracks_to_remove]
    logger.info(f"Deduplication ({strategy}): removed {len(tracks_to_remove)} tracks from {len(tracks)} total.")
    return deduped, duplicate_groups
