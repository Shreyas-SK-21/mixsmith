"""Quota allocation engine using the Largest Remainder (Hamilton-Hare) method."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.quotas")


@dataclass
class QuotaAllocationResult:
    """Outcome of proportional quota allocation across categories."""
    selected_tracks: List[Track]
    allocated_counts: Dict[str, int]
    target_shares: Dict[str, float]
    actual_shares: Dict[str, float]
    selection_reasons: Dict[str, str] = field(default_factory=dict)
    exclusion_reasons: Dict[str, str] = field(default_factory=dict)


def allocate_largest_remainder(
    weights: Dict[str, float],
    total_slots: int
) -> Dict[str, int]:
    """
    Applies the Hamilton-Hare (Largest Remainder) method to guarantee exact integer allocation
    without rounding drift or off-by-one errors.
    
    Sum of allocated integer slots is guaranteed to equal total_slots.
    """
    if total_slots <= 0 or not weights:
        return {k: 0 for k in weights}

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return {k: 0 for k in weights}

    # 1. Normalized exact shares
    exact_shares = {k: (w / total_weight) * total_slots for k, w in weights.items()}

    # 2. Integer floors
    floors = {k: math.floor(share) for k, share in exact_shares.items()}

    # 3. Remainders
    remainders = {k: share - floors[k] for k, share in exact_shares.items()}

    # 4. Residual slots to distribute
    allocated_sum = sum(floors.values())
    residual = total_slots - allocated_sum

    # Distribute residual slots to categories with highest remainders
    sorted_remainders = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
    for i in range(residual):
        cat = sorted_remainders[i % len(sorted_remainders)][0]
        floors[cat] += 1

    return floors


def allocate_genre_quotas(
    tracks: List[Track],
    genre_quotas: Dict[str, float],
    total_tracks_target: Optional[int] = None
) -> QuotaAllocationResult:
    """
    Allocates tracks proportionally according to genre quotas using the Largest Remainder method.
    Multi-genre tracks are prioritized toward their most constrained matching category.
    """
    target_n = total_tracks_target or len(tracks)
    target_quotas = {k.strip(): v for k, v in genre_quotas.items() if v > 0}

    slot_targets = allocate_largest_remainder(target_quotas, target_n)

    # Group candidate tracks by primary genre and sub-genres
    genre_candidates: Dict[str, List[Track]] = defaultdict(list)
    for t in tracks:
        # Match primary genre or any sub-genre tag
        matched_any = False
        for g_target in target_quotas:
            tg_clean = g_target.lower()
            if (tg_clean in t.primary_genre.lower() or
                tg_clean.replace("-", " ") in t.primary_genre.lower() or
                any(tg_clean in tag.lower() for tag in t.all_genres)):
                genre_candidates[g_target].append(t)
                matched_any = True
        if not matched_any:
            genre_candidates["Unclassified / Other"].append(t)

    selected: List[Track] = []
    selected_ids: Set[str] = set()
    sel_reasons = {}
    ex_reasons = {}

    for g_name, quota in slot_targets.items():
        candidates = genre_candidates.get(g_name, [])
        # Sort candidates by popularity
        sorted_cand = sorted(candidates, key=lambda t: t.popularity, reverse=True)

        count = 0
        for t in sorted_cand:
            if t.id not in selected_ids and count < quota:
                selected.append(t)
                selected_ids.add(t.id)
                sel_reasons[t.id] = f"Selected under '{g_name}' quota ({quota} slots allocated)"
                count += 1

    # Remaining tracks not selected
    for t in tracks:
        if t.id not in selected_ids:
            ex_reasons[t.id] = f"Excluded: Genre quota filled or track genre ({t.primary_genre}) not in requested targets."

    # Compute actual achieved shares
    total_sel = len(selected)
    actual_counts = Counter(t.primary_genre for t in selected)
    actual_shares = {g: (actual_counts.get(g, 0) / total_sel) * 100.0 if total_sel > 0 else 0.0 for g in target_quotas}
    total_w = sum(target_quotas.values())
    target_shares = {g: (w / total_w) * 100.0 for g, w in target_quotas.items()}

    return QuotaAllocationResult(
        selected_tracks=selected,
        allocated_counts=slot_targets,
        target_shares=target_shares,
        actual_shares=actual_shares,
        selection_reasons=sel_reasons,
        exclusion_reasons=ex_reasons
    )
