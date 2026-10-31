"""Quota allocation engine using the Largest Remainder (Hamilton-Hare) method."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.quotas")


@dataclass
class QuotaAllocationResult:
    """Outcome of proportional quota allocation across categories."""
    selected_tracks: list[Track]
    allocated_counts: dict[str, int]
    target_shares: dict[str, float]
    actual_shares: dict[str, float]
    unfilled_slots: dict[str, int] = field(default_factory=dict)
    reallocated_slots: dict[str, int] = field(default_factory=dict)
    selection_reasons: dict[str, str] = field(default_factory=dict)
    exclusion_reasons: dict[str, str] = field(default_factory=dict)


def validate_quota_weights(weights: dict[str, float]) -> None:
    """Validates that quota weights are non-negative, finite, and strictly positive in sum."""
    if not weights:
        raise ValueError("Quota weights dictionary cannot be empty.")
    for k, w in weights.items():
        if math.isnan(w) or math.isinf(w):
            raise ValueError(f"Quota weight for '{k}' cannot be NaN or infinite: {w}")
        if w < 0:
            raise ValueError(f"Quota weight for '{k}' cannot be negative: {w}")
    if sum(weights.values()) <= 0:
        raise ValueError("Sum of quota weights must be strictly positive.")


def allocate_largest_remainder(
    weights: dict[str, float],
    total_slots: int
) -> dict[str, int]:
    """
    Applies the Hamilton-Hare (Largest Remainder) method to guarantee exact integer allocation
    without rounding drift or off-by-one errors.

    Sum of allocated integer slots is guaranteed to equal total_slots.
    """
    if total_slots <= 0 or not weights:
        return {k: 0 for k in weights}

    validate_quota_weights(weights)
    total_weight = sum(weights.values())

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
    tracks: list[Track],
    genre_quotas: dict[str, float],
    total_tracks_target: int | None = None,
    reallocate_unfilled: bool = True
) -> QuotaAllocationResult:
    """
    Allocates tracks proportionally according to genre quotas using the Largest Remainder method.

    Guarantees:
      - Validates quota weights.
      - Supports repeated track occurrences without treating duplicate IDs as a single slot.
      - Handles multi-genre tracks by prioritizing scarce categories first.
      - Reallocates unfilled quota slots when categories have insufficient tracks, reporting shortages.
    """
    if not tracks:
        return QuotaAllocationResult(
            selected_tracks=[],
            allocated_counts={k: 0 for k in genre_quotas},
            target_shares={k: 0.0 for k in genre_quotas},
            actual_shares={k: 0.0 for k in genre_quotas}
        )

    target_n = min(total_tracks_target or len(tracks), len(tracks))
    target_quotas = {k.strip(): v for k, v in genre_quotas.items() if v > 0}
    validate_quota_weights(target_quotas)

    slot_targets = allocate_largest_remainder(target_quotas, target_n)

    # 1. Index candidate tracks by original list index to preserve repeated occurrences
    genre_candidates: dict[str, list[tuple[int, Track]]] = defaultdict(list)
    for idx, t in enumerate(tracks):
        matched_any = False
        t_all_genres = [g.lower() for g in t.all_genres]
        t_primary = t.primary_genre.lower()
        for g_target in target_quotas:
            tg_clean = g_target.lower()
            if (tg_clean in t_primary or
                tg_clean.replace("-", " ") in t_primary or
                any(tg_clean in tag for tag in t_all_genres)):
                genre_candidates[g_target].append((idx, t))
                matched_any = True
        if not matched_any:
            genre_candidates["Unclassified / Other"].append((idx, t))

    # 2. Prioritize categories by constraint pressure (fewest candidates per requested slot first)
    # This prevents multi-genre tracks from being greedily monopolized by large categories
    def category_scarcity(g_name: str) -> float:
        q = slot_targets.get(g_name, 0)
        c_count = len(genre_candidates.get(g_name, []))
        return (c_count / q) if q > 0 else float("inf")

    prioritized_genres = sorted(slot_targets.keys(), key=category_scarcity)

    selected_indices: set[int] = set()
    selected_tracks: list[Track] = []
    unfilled_slots: dict[str, int] = defaultdict(int)
    reallocated_slots: dict[str, int] = defaultdict(int)
    sel_reasons: dict[str, str] = {}
    ex_reasons: dict[str, str] = {}

    for g_name in prioritized_genres:
        quota = slot_targets[g_name]
        candidates = genre_candidates.get(g_name, [])
        # Sort candidates by popularity
        sorted_cand = sorted(candidates, key=lambda item: (item[1].popularity if item[1].popularity is not None else 50), reverse=True)

        count = 0
        for orig_idx, t in sorted_cand:
            if orig_idx not in selected_indices and count < quota:
                selected_tracks.append(t)
                selected_indices.add(orig_idx)
                sel_reasons[t.id] = f"Selected under '{g_name}' quota ({quota} slots allocated)"
                count += 1

        deficit = quota - count
        if deficit > 0:
            unfilled_slots[g_name] = deficit

    # 3. Reallocate unfilled slots to categories with surplus candidates if requested
    total_deficit = sum(unfilled_slots.values())
    if reallocate_unfilled and total_deficit > 0:
        surplus_candidates: list[tuple[int, Track, str]] = []
        for g_name, candidates in genre_candidates.items():
            for orig_idx, t in candidates:
                if orig_idx not in selected_indices:
                    surplus_candidates.append((orig_idx, t, g_name))

        surplus_candidates.sort(key=lambda item: (item[1].popularity if item[1].popularity is not None else 50), reverse=True)

        reallocated_count = 0
        for orig_idx, t, g_name in surplus_candidates:
            if reallocated_count >= total_deficit or len(selected_tracks) >= target_n:
                break
            if orig_idx not in selected_indices:
                selected_tracks.append(t)
                selected_indices.add(orig_idx)
                reallocated_slots[g_name] += 1
                sel_reasons[t.id] = f"Selected via quota shortfall reallocation from '{g_name}'"
                reallocated_count += 1

    # 4. Exclusion reasons
    for idx, t in enumerate(tracks):
        if idx not in selected_indices:
            ex_reasons[t.id] = (
                f"Excluded: Genre quota filled or track genre ({t.primary_genre}) "
                f"not prioritized in requested targets."
            )

    # 5. Compute actual achieved shares
    total_sel = len(selected_tracks)
    actual_counts = Counter(t.primary_genre for t in selected_tracks)
    actual_shares = {
        g: (actual_counts.get(g, 0) / total_sel) * 100.0 if total_sel > 0 else 0.0
        for g in target_quotas
    }
    total_w = sum(target_quotas.values())
    target_shares = {g: (w / total_w) * 100.0 for g, w in target_quotas.items()}

    return QuotaAllocationResult(
        selected_tracks=selected_tracks,
        allocated_counts=slot_targets,
        target_shares=target_shares,
        actual_shares=actual_shares,
        unfilled_slots=dict(unfilled_slots),
        reallocated_slots=dict(reallocated_slots),
        selection_reasons=sel_reasons,
        exclusion_reasons=ex_reasons
    )
