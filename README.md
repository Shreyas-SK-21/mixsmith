# Mixsmith

**Production-grade, constraint-based music curation engine.**

Describe what you want. Get the playlist.

---

## Overview

Mixsmith transforms personal music libraries and Spotify playlists into curated listening journeys. Rather than simple shuffle or basic genre tags, Mixsmith applies mathematical scheduling, multi-artist de-clumping, multi-constraint optimization, and intelligent deduplication to curate playlists that flow naturally.

Mixsmith operates platform-independently: its algorithmic core is decoupled from music streaming APIs, with full local support for CSV and Excel files.

---

## Features

- **Natural-Language Curation**: Prompt Mixsmith in plain English (e.g. *"Create a 2-hour late night drive with The Weeknd and Joji, no artist repeats within 5 tracks, moving from mellow to energetic"*).
- **Advanced Artist De-clumping**: Prevents consecutive artist repeats with multi-artist collaboration awareness and configurable $k$-spacing windows.
- **Pigeonhole Feasibility Analysis**: Automatically detects if requested artist spacing is mathematically possible and computes the maximum achievable threshold.
- **Multi-Constraint Engine**: Curate against simultaneous limits (max tracks per artist, target runtime, hard min/max duration bounds, genre distribution quotas, pinned tracks).
- **Energy Progression**: Sequences playlists smoothly along energy curves (`mellow_to_energetic` or `energetic_to_mellow`) derived from human themes and genres rather than popularity or deprecated audio features.
- **Listening Journeys**:
  - **Artist Evolution**: Chronological discography progression.
  - **Decade Journey**: Smooth era transitions ($60\text{s} \to 70\text{s} \to \dots \to 2020\text{s}$).
  - **Genre Flow**: Acoustically adjacent genre transitions.
  - **Nostalgia Mode**: Anchored around a golden decade with smooth era falloffs.
- **Intelligent Deduplication**: Distinguishes exact duplicates from remasters, live cuts, acoustic sessions, and radio edits.
- **Safe Mutation Protocol**: Dry-run previews, constraint audit reports, and automatic local JSON snapshots before modifying Spotify.
- **Styled Spreadsheets**: Exportify-compatible CSV and multi-sheet styled Excel workbooks with automated overview metrics.

---

## Architecture

```
src/mixsmith/
├── auth/           # OAuth2 PKCE, token refresh, and credential hierarchy
├── connectors/     # Spotify Web API client and rate-limit backoff
├── core/           # Pure, platform-independent curation algorithms
│   ├── declumper.py    # Multi-artist k-spacing and feasibility analyzer
│   ├── sequencing.py   # Multi-constraint curation engine
│   ├── journeys.py     # Era, artist evolution, and genre journeys
│   ├── dedup.py        # Version-aware duplicate detection
│   ├── manager.py      # Split, merge, diff, and snapshot manager
│   ├── filters.py      # AST boolean expression evaluator
│   └── models.py       # Track, Playlist, and Constraint models
├── ai/             # Natural-language prompt parsing and schema validation
├── exporters/      # Excel (multi-sheet styled) and CSV exporters
├── utils/          # Config resolution, structured logging, metadata
└── cli/            # Command-line interface
```

See [docs/architecture.md](docs/architecture.md) and [docs/algorithms.md](docs/algorithms.md) for in-depth technical documentation.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/Shreyas-SK-21/mixsmith.git
cd mixsmith
pip install -e .
```

### 2. Configure Credentials & OAuth (PKCE)

Mixsmith supports standard Authorization Code Flow with **Proof Key for Code Exchange (PKCE, RFC 7636)** and cryptographic CSRF state validation:

```bash
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID and optional SPOTIFY_CLIENT_SECRET
```

Log in via Spotify OAuth with local callback server and PKCE verification:
```bash
python -m mixsmith.cli auth login
```

---

## CLI Usage

### Natural Language Curation (Dry-Run Preview)

```bash
python -m mixsmith.cli curate \
  --from-excel "Liked_Songs.csv" \
  --prompt "Create a 2-hour late night session with no artist repeats within 4 tracks" \
  --dry-run
```

### Advanced De-clumping & Artist Spacing

```bash
python -m mixsmith.cli curate \
  --playlist "your_playlist_id" \
  --spacing 3 \
  --max-per-artist 2 \
  --sort declump
```

### Energy Progression & Duration Bounds

```bash
python -m mixsmith.cli curate \
  --from-excel "Library.xlsx" \
  --sort energy \
  --min-duration 45 \
  --max-duration 75 \
  --output "EveningFlow.xlsx"
```

### Intelligent Deduplication

```bash
# Preview duplicates without removing
python -m mixsmith.cli dedup --input "Liked_Songs.csv" --dry-run

# Deduplicate keeping only exact recordings, preserving live & acoustic versions
python -m mixsmith.cli dedup --input "Liked_Songs.csv" --strategy exact_only --output "Cleaned.xlsx"
```

### Compare Playlists

```bash
python -m mixsmith.cli compare --playlist-1 "id_1" --playlist-2 "id_2"
```

### Export to Styled Excel with Musical DNA Overview

```bash
python -m mixsmith.cli export --playlist "liked" --output "My_Liked_Songs.xlsx"
```

---

## Testing

Mixsmith includes a comprehensive pytest suite covering all algorithms, exports, schema parsing, and API error scenarios:

```bash
python -m pytest tests -v
```

### Enforcing Constraints & Force Override

Mixsmith independently validates every playlist against all requested hard and soft constraints. If any hard constraint fails (e.g. impossible artist spacing or exceeding per-artist quotas), Mixsmith blocks playlist creation to protect curation integrity. You can force playlist creation with the `--force` flag:

```bash
python -m mixsmith.cli curate \
  --playlist "your_playlist_id" \
  --spacing 4 \
  --force
```

---

## Spotify API & Developer Policy Boundaries

Mixsmith maintains an intentional, architectural separation between its **platform-independent curation core** and optional **Spotify API connectors**:

- **Platform-Independent Engine**: All combinatorial scheduling algorithms, multi-artist de-clumping, 0/1 knapsack duration solvers, Hamilton-Hare quota allocators, and confidence-aware metadata classifiers operate 100% offline. They can be fully utilized with local CSV and Excel collections without connecting to Spotify.
- **February 2026 Web API Compatibility**: The Spotify connector has been migrated to Spotify's February 2026 API contract (`playlist.items.items[].item`, `items.total`, removal of bulk `/artists?ids=...`, and non-assumption of `popularity` metrics).
- **Policy Boundaries (Sections III.13 & III.14)**:
  - Mixsmith does **not** make blanket claims of official Spotify compliance or certification.
  - Section III.13 restricts creating derivative statistics, listening profiles, or metrics from Spotify Content. Local curation reduces privacy risks but formal policy clearance remains pending.
  - Section III.14 prohibits training or ingesting Spotify Content into AI/ML models. Mixsmith strictly complies by parsing only user prompt strings—never passing track content or metadata to external LLMs.
  - Detailed legal analysis and architectural boundaries are documented in [docs/spotify-policy-review.md](docs/spotify-policy-review.md).
- **Development Mode Realities**:
  - Requires user-supplied Spotify Developer credentials (`SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`).
  - App owner must hold an active **Spotify Premium** subscription.
  - Limited to **5 explicit authorized test users** and shares global rate limits across a max of 25 Client IDs.
- **Safe Mutation Safeguards**:
  - Mutations are non-destructive and opt-in (`--dry-run` by default).
  - Snapshot drift detection validates that external tracks have not changed before execution.
  - Non-atomic batch insertion errors are caught and surfaced via `PartialMutationError`, preventing silent truncation or corrupt ordering.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
