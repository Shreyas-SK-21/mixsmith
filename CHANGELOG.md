# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
