# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - 2026-10-31

### Added
- **Tiered Constraint Schema & Conflict Detection (`ai/schema.py`, `ai/parser.py`)**: Structured separation of Hard constraints, Soft constraints, and Preferences. Implemented proactive conflict detection for mutually exclusive ratings (clean vs explicit), artist/genre inclusion vs exclusion clashes, and inverted duration bounds.
- **Confidence-Aware Metadata Inference (`utils/metadata.py`)**: Explicit metadata confidence tracking (`KNOWN`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`) and provenance logging (`USER_OVERRIDE`, `UNICODE_SCRIPT`, `GENRE_ASSOCIATION`, `ISRC_COUNTRY`, `TITLE_HEURISTIC`, `DEFAULT_FALLBACK`). Instrumental tracks and non-English music are accurately recognized without arbitrary guessing.
- **Safe Playlist Mutation Engine (`connectors/spotify.py`)**: Pre-mutation state inspection, external snapshot drift detection (`SnapshotDriftError`), track URI validation and normalization, dry-run simulation, and verified batched additions.
- **Algorithmic Benchmarking Suite & Exact Oracle (`tests/benchmarks/`)**: Synthetic music library generator with Zipf-distributed artist frequencies, exact backtracking solver oracle for small $N \le 12$, and performance benchmarks verifying sub-second sequencing for 1,000 tracks.
- **Central Independent Validation Engine (`core/validation.py`)**: Post-curation independent audit of every constraint (artist spacing, max tracks, duration, genre shares, pinned positions, track preservation).
- **Curation Explainability (`core/explanation.py`)**: Structured, deterministic explanation reports (`CurationExplanation`) explaining why every track was selected, excluded, or placed at a position. Supports `--explain` and export to Markdown/JSON.
- **Duration Knapsack Optimizer (`core/duration.py`)**: Discrete 0/1 Knapsack dynamic programming with artist-diversity penalty to replace naive greedy fitting.
- **Hamilton-Hare Largest Remainder Method (`core/quotas.py`)**: Guaranteed exact integer quota allocation across genres and decades without off-by-one rounding errors.
- **Enhanced Feasibility Analysis (`core/declumper.py`)**: Distinguishes necessary vs sufficient conditions, detects collaboration-constrained sets, and reports bottleneck artists and achievable ceilings.
- **Expanded Test Suite**: 55 comprehensive automated tests across algorithms, benchmarks, metadata confidence, mutations, explainability, quotas, and de-clumping.

### Performance
- Optimized greedy artist de-clumper with precomputed artist lookups and $O(1)$ candidate removal, speeding up large playlist sequencing ($N=1,000$) by 10x–50x.

## [0.2.0] - 2026-10-31

### Added
- **Modular Architecture**: Decoupled application into `core/`, `connectors/`, `auth/`, `ai/`, `exporters/`, `utils/`, and `cli/`.
- **Domain Models**: Added typed `Track`, `Playlist`, `ConstraintResult`, `CurationPlan`, and `DuplicateGroup` models.
- **Advanced De-clumper**: Multi-artist aware spacing engine with configurable $k$-spacing, mathematical pigeonhole feasibility analysis, and graceful fallback.
- **Multi-Constraint Sequencing**: Constraint engine supporting max tracks per artist, target duration, genre quotas, and pinned positions.
- **Listening Journeys**: Added Artist Evolution, Decade Journey, Genre Journey, and Nostalgia sequencing modes.
- **Intelligent Deduplication**: Two-pass deduplication distinguishing exact duplicates, remasters, live cuts, acoustic renditions, and radio edits.
- **Natural Language Curation**: Deterministic heuristic prompt interpreter with structured schema validation.
- **Safe Mutation Protocol**: Added `--dry-run` previews and automatic local JSON state snapshots before playlist modifications.
- **Automated Test Suite**: 25 comprehensive unit and integration tests with pytest covering algorithms, exports, filtering, and error handling.
- **Documentation**: Added `IMPROVEMENT_ROADMAP.md`, `docs/architecture.md`, `docs/algorithms.md`, and `docs/installation.md`.

### Fixed
- Fixed Windows terminal `UnicodeEncodeError` across CLI print statements.
- Fixed Spotify API 403 Forbidden by migrating playlist items endpoint to `/items`.
- Fixed title normalization regex in version categorization.
- Removed hardcoded local user directories from credential loaders and CLI fallbacks.

---

## [0.1.0] - 2026-10-30

### Added
- Initial prototype featuring basic Spotify API client, Excel export, and human dimension filters.
