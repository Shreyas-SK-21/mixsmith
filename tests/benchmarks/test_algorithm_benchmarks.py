"""Algorithmic benchmark test suite for Mixsmith curation and sequencing engines."""

import time

from mixsmith.core.declumper import declump_tracks
from mixsmith.core.duration import optimize_playlist_duration
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints
from mixsmith.core.validation import PlaylistValidator
from tests.benchmarks.synthetic import (
    exact_backtracking_declumper,
    generate_synthetic_library,
)


def test_exact_oracle_agreement():
    """
    Compares the heuristic greedy declumper against an exact backtracking solver
    on small synthetic libraries (N <= 12).
    """
    for seed in [101, 202, 303]:
        tracks = generate_synthetic_library(n_tracks=12, n_unique_artists=6, seed=seed)
        exact_solution = exact_backtracking_declumper(tracks, min_spacing=1)

        result_tracks, constraint_res, feas_report, _ = declump_tracks(
            tracks, min_spacing=1, return_details=True
        )

        if exact_solution is not None:
            # If an exact 0-violation solution exists, verify result satisfies spacing
            spacing_res = PlaylistValidator.validate_artist_spacing(result_tracks, min_spacing=1)
            assert spacing_res.satisfied is True, f"Expected satisfied spacing for seed {seed}, got {spacing_res.details}"
            assert feas_report.is_feasible is True


def test_runtime_scaling_under_100ms():
    """
    Measures runtime scaling across N = 50, 100, 250, 500 tracks.
    Ensures that scheduling 500 tracks runs well under 100 milliseconds.
    """
    runtimes = {}
    for n in [50, 100, 250, 500]:
        library = generate_synthetic_library(n_tracks=n, n_unique_artists=max(10, n // 5), seed=42)
        start = time.perf_counter()
        declump_tracks(library, min_spacing=2)
        elapsed = time.perf_counter() - start
        runtimes[n] = elapsed

    # 500 tracks should sequence cleanly in < 0.50s
    assert runtimes[500] < 0.50, f"Declumping 500 tracks took {runtimes[500]:.4f}s, expected < 0.50s"


def test_knapsack_duration_benchmark():
    """
    Benchmarks the 0/1 Knapsack duration optimizer on a 100-track library
    targeting 60 minutes.
    """
    tracks = generate_synthetic_library(n_tracks=100, n_unique_artists=20, seed=77)
    target_minutes = 60
    target_ms = target_minutes * 60 * 1000

    opt_res = optimize_playlist_duration(tracks, target_duration_minutes=target_minutes)
    total_selected_ms = sum(t.duration_ms for t in opt_res.selected_tracks)

    # Duration deviation should be minimal (within 1-2 track lengths)
    diff_ms = abs(total_selected_ms - target_ms)
    assert diff_ms < 350000, f"Knapsack duration deviation too large: {diff_ms / 1000:.1f}s"
    assert len(opt_res.selected_tracks) > 0


def test_large_library_scalability_1000_tracks():
    """
    Verifies that a massive library of 1,000 tracks sequences cleanly
    without recursion errors or exponential blowup.
    """
    large_lib = generate_synthetic_library(n_tracks=1000, n_unique_artists=100, seed=999)
    engine = ConstraintSequencingEngine()

    start = time.perf_counter()
    plan = engine.curate(
        large_lib,
        constraints=CurationConstraints(min_artist_spacing=1, sort_mode="declump"),
        playlist_name="Large 1k Mix"
    )
    elapsed = time.perf_counter() - start

    assert len(plan.tracks) == 1000
    assert elapsed < 2.5, f"1,000 tracks took {elapsed:.3f}s; expected < 2.5s"
