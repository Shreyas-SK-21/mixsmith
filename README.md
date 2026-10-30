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
- **Multi-Constraint Engine**: Curate against simultaneous limits (max tracks per artist, target runtime, genre distribution quotas, pinned tracks).
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

## Spotify API & Developer Policy Compliance

Mixsmith is designed in strict compliance with the **Spotify Developer Terms of Service and Policy**:

- **Decoupled Algorithmic Processing**: Mixsmith's categorization, sequencing, and curation algorithms run entirely locally. All genre inferences, era attributions, and thematic vibe classifications are computed via platform-independent heuristics, lexical tokenization, and ISRC registry codes—completely decoupled from Spotify streaming endpoints or proprietary recommendation models.
- **No Unauthorized Ingestion or AI Training**: Mixsmith never transmits Spotify metadata, catalog details, or user playlists to external LLM services or third-party APIs for training, indexing, or profiling. Natural language curation queries are parsed locally into structured constraint schemas.
- **Standard Permitted OAuth Scopes**: Mixsmith requests only standard, minimal user permissions (`playlist-modify-private`, `playlist-read-private`, `user-library-read`).
- **Cryptographic Auth Security (RFC 7636 PKCE)**: Authorization employs SHA-256 code challenge generation and random cryptographic CSRF state validation against unauthorized interception.
- **Safe Mutation Protocol**: Mutations are strictly opt-in. Mixsmith requires explicit interactive confirmation or the `--confirm` flag, inspects pre-mutation snapshots for external drift, validates Spotify URIs, and executes track modifications in atomic batches.
- **No Stream Ripping or Audio Redistribution**: Mixsmith manages metadata and playlist track references only. It does not stream, cache, reverse-engineer, or store audio files.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
