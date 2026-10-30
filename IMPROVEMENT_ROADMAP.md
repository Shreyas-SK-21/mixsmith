# Mixsmith: Engineering Audit & Improvement Roadmap
**From AI-Prompted Spotify Script to Production-Grade Music Curation Engine**

---

## 1. Executive Summary

Mixsmith began as a rapid prototype created with AI prompting to solve personal playlist management frustrations: exporting playlists, categorising tracks by human dimensions (eras, vibes, genres, languages), sorting, and generating Spotify playlists.

While functional, the initial codebase exhibits common prototype-level weaknesses: a monolithic God Object (`SpotifyClient`) spanning 1,376 lines, tightly coupled network operations and domain algorithms, hardcoded absolute local paths, rudimentary greedy heuristics for artist spacing, lack of typed domain models, zero automated test coverage, and security/policy risks regarding Spotify API compliance.

This document presents a rigorous architectural audit of the current codebase and details a phased implementation roadmap to evolve Mixsmith into an open-source, modular, constraint-based music curation engine.

---

## 2. Codebase Audit & Identified Weaknesses

### 2.1 Architecture & Code Organization
- **Monolithic "God Object" (`SpotifyClient`)**: A single class handles:
  - Local disk credential reads/writes
  - OAuth HTTP callbacks and token refresh
  - Spotify REST API requests and rate-limiting
  - Heuristic music classification (genre, era, theme, language)
  - Playlist sequencing and artist de-clumping
  - AST-based expression evaluation
  - Openpyxl Excel workbook rendering and CSV generation
- **Tight Coupling**: Core curation and sequencing algorithms cannot be tested or run without instantiating `SpotifyClient`, which attempts network checks and file I/O on disk.
- **Hardcoded Absolute Paths**:
  - `Path.home() / ".gemini" / "config" / "plugins" / "spotify" / "credentials.json"` hardcoded as default.
  - `C:\Users\shrey\.gemini\antigravity\scratch\sorted playlists\Liked_Songs.csv` hardcoded as fallback in CLI.
- **Untyped Dictionaries**: Tracks and playlists are represented throughout as generic `Dict[str, Any]` without schemas, leading to fragile key lookups (`t.get("artists")` vs `t.get("Artist Name(s)")` vs `t.get("primary_artist")`).

### 2.2 Algorithmic Limitations & Edge Cases

#### A. Artist De-clumping (`declump_tracks_by_artist`)
- **Single-Artist Assumption**: The current de-clumper only extracts `primary_artist` (or the first element of `artists`). Collaborations, features, and dual-artist credits (e.g., *Artist A feat. Artist B*, *Artist B & Artist C*) cause immediate collisions.
- **Fixed Spacing $k=1$**: Only checks if the immediately preceding track was by the same artist. It cannot enforce wider buffers (e.g., minimum 3, 5, or 10 tracks between appearances).
- **No Mathematical Feasibility Check**: If an artist appears $C$ times in a playlist of $N$ tracks, enforcing a minimum gap $k$ requires:
  $$C \le \left\lceil \frac{N}{k} \right\rceil$$
  The current implementation does not test feasibility; when candidate buckets run dry, it collapses and piles remaining tracks of the same artist sequentially at the end.
- **Loss of Track Context**: Ties are broken arbitrarily by `max(candidates, key=len)`, discarding original playlist sequencing.

#### B. Deduplication
- Currently nonexistent. No distinction between:
  - Exact duplicates (same ISRC or title + artist)
  - Remasters (e.g., "Song - 2011 Remaster")
  - Live recordings (e.g., "Song - Live at Wembley")
  - Acoustic versions
  - Radio edits / clean cuts
  - Deluxe album re-releases

#### C. Constraint-Based Sequencing
- Currently, filtering and sorting are applied sequentially in a single pass (`filter_and_sort_tracks`).
- Cannot handle multi-constraint targets (e.g., 60% 90s rock, max 2 songs per artist, 120-minute target length, pinned intro and outro tracks).

### 2.3 Error Handling & Network Resilience
- **Generic Exceptions**: Functions raise raw `RuntimeError` or catch `Exception` and print to stderr.
- **Logging**: Uses raw `print()` statements and ANSI escape codes. Emoji characters (`🎤`, `🎸`) cause `UnicodeEncodeError` on Windows consoles with default code pages.
- **Transient Network Failures**: Only retries HTTP 429 and 401; does not handle connection timeouts, DNS drops, or HTTP 502/503 gateway errors.

### 2.4 Security & Spotify Developer Policy Compliance
- **Plaintext Credentials**: Tokens and secrets are stored in plaintext JSON without OS-level keychain integration or environment-first resolution.
- **Spotify Content & AI Policies**: Spotify's Developer Policy prohibits ingesting Spotify metadata into AI/ML models to train or derive algorithmic metrics without authorization. Mixsmith must keep the LLM interpretation layer decoupled: the LLM translates natural language into *constraints and criteria* (e.g. genre, decade, duration), while local deterministic code executes the queries and sequencing.
- **Mutation Safeguards**: Creating or altering playlists must have explicit dry-run previews, showing track counts and diffs before applying changes to Spotify.

---

## 3. Target Modular Architecture

```
mixsmith/
├── src/
│   └── mixsmith/
│       ├── __init__.py
│       ├── auth/                 # OAuth PKCE, TokenManager, CredentialStore
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   └── storage.py
│       ├── connectors/           # External API clients (pure data providers)
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── spotify.py
│       ├── core/                 # Platform-agnostic curation engine
│       │   ├── __init__.py
│       │   ├── models.py         # Track, Artist, Album, Playlist, Constraint models
│       │   ├── exceptions.py     # Typed domain exceptions
│       │   ├── declumper.py      # Multi-artist, k-spacing, priority-queue de-clumper
│       │   ├── sequencing.py     # Multi-constraint playlist sequencing engine
│       │   ├── journeys.py       # Listening journeys (chronological, era, energy)
│       │   ├── dedup.py          # Intelligent duplicate & version detector
│       │   ├── manager.py        # Playlist split, merge, diff, and snapshot engine
│       │   └── filters.py        # AST and predicate expression evaluator
│       ├── ai/                   # Natural-language curation layer
│       │   ├── __init__.py
│       │   ├── schema.py         # Pydantic/dataclass curation specification
│       │   ├── parser.py         # NL -> Structured CurationSpec generator
│       │   └── validator.py      # Feasibility & contradiction checker
│       ├── exporters/            # Spreadsheet and file exporters
│       │   ├── __init__.py
│       │   ├── excel.py          # Styled, multi-sheet Excel exporter
│       │   └── csv.py            # Exportify-compatible CSV exporter
│       ├── utils/                # Cross-cutting utilities
│       │   ├── __init__.py
│       │   ├── config.py         # AppConfig, env resolution, path resolution
│       │   ├── logging.py        # Structured logging with Windows safe-strings
│       │   └── metadata.py       # Genre mapping, era detection, language inference
│       └── cli/                  # Command-line interface
│           ├── __init__.py
│           ├── main.py           # Command router (backward compatible)
│           └── commands/         # Subcommand handlers
├── tests/                        # Automated unit & integration tests
│   ├── conftest.py
│   ├── test_declumper.py
│   ├── test_sequencing.py
│   ├── test_dedup.py
│   ├── test_filters.py
│   ├── test_exporters.py
│   ├── test_ai_schema.py
│   └── test_spotify_mock.py
├── docs/                         # Documentation
│   ├── architecture.md
│   ├── algorithms.md
│   └── installation.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 4. Phased Implementation Roadmap

| Phase | Milestone | Priority | Status |
|---|---|---|---|
| **Phase 1** | Comprehensive Audit & Improvement Roadmap | Critical | Completed |
| **Phase 2** | Core Domain Models & Modular Decoupling | Critical | In Progress |
| **Phase 3** | Advanced Algorithmic Engine (De-clumper, Constraints, Dedup) | High | Planned |
| **Phase 4** | Automated Unit & Integration Testing Suite | High | Planned |
| **Phase 5** | Exporter Modernization (Excel & CSV) | Medium | Planned |
| **Phase 6** | Natural Language Curation Layer (Deterministic execution) | High | Planned |
| **Phase 7** | Playlist Management (Split, Merge, Diff, Snapshots) | Medium | Planned |
| **Phase 8** | Security, Documentation, and Open-Source Polish | High | Planned |

---

## 5. Algorithmic Specifications

### 5.1 Advanced Multi-Artist $k$-Spacing De-clumper
- **Artist Representation**: Every track has a `primary_artist` and a set of `all_artists` (including featured performers and co-writers).
- **Distance Constraint**: For any two tracks $T_i$ and $T_j$ at indices $i, j$ with $|i - j| \le k$:
  $$\text{artists}(T_i) \cap \text{artists}(T_j) = \emptyset$$
- **Feasibility Verification**:
  $$\forall a \in \text{Artists}, \quad \text{count}(a) \le \left\lceil \frac{N}{k+1} \right\rceil$$
  When $C > \lceil N/(k+1) \rceil$, the algorithm computes the maximum achievable spacing $k^* < k$ or identifies the excess tracks and reports a feasibility warning before falling back gracefully.
- **Algorithm**: Max-frequency priority queue (max-heap) with a cooldown queue of length $k$. Tracks from artist $a$ remain in the cooldown queue for $k$ placements before being returned to the available heap.

### 5.2 Intelligent Deduplication Matrix
Tracks are compared across multiple similarity dimensions:
1. **Exact Duplicate**: Same ISRC or normalized title match with identical primary artist and duration within $\pm 2$ seconds.
2. **Remaster**: Title contains regex `r"(?i)\b(\d{4}\s+)?remaster(ed)?\b"`.
3. **Live Version**: Title contains regex `r"(?i)\b(live|recorded live|in concert)\b"`.
4. **Acoustic Version**: Title contains regex `r"(?i)\b(acoustic|unplugged)\b"`.
5. **Radio / Clean Edit**: Title contains `r"(?i)\b(radio edit|clean version)\b"`.
6. **Deluxe Edition**: Album name contains `r"(?i)\b(deluxe|expanded|special)\b"`.

### 5.3 Safe Playlist Mutation Protocol
Every command modifying Spotify (`create`, `reorder`, `dedup`, `delete`) must conform to the **Safe Mutation Protocol**:
1. **Dry-Run Preview**: Compute and display track count, duration, diff summary, and constraint satisfaction.
2. **Snapshot**: Capture current playlist state (track IDs, positions, timestamps) in a local snapshot cache before applying modifications.
3. **User Confirmation**: Require explicit `--confirm` flag or interactive prompt before mutating Spotify.
