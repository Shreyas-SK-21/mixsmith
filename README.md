# Mixsmith

**A music playlist curator, not just a sorter.**

Describe what you want. Get the playlist.

---

## What it does

Mixsmith connects to your Spotify library and lets you curate playlists using plain-English instructions. Tell it to pull all your 90s rock from liked songs, space artists so the same one never plays twice in a row, and gradually shift the mood from mellow to energetic — and it does exactly that.

It understands your music in human terms: genres, vibes, decades, languages, popularity tiers, and more.

---

## Features

- **Natural-language playlist creation** — describe what you want, get a playlist
- **Smart artist spacing** — no same artist back-to-back (declumping)
- **Genre & theme flow** — smooth transitions between moods and sounds
- **Chronological journeys** — trace a genre or artist through time
- **Cross-playlist intelligence** — find overlaps, orphans, near-duplicates
- **Excel export** — full metadata: genre, vibe, decade, language, popularity tier
- **Version control** — automatic snapshots before every modification

---

## Setup

### 1. Prerequisites

- Python 3.10+
- A Spotify account
- A Spotify Developer app ([create one here](https://developer.spotify.com/dashboard))

### 2. Install

```bash
git clone https://github.com/ShreyasSK21/mixsmith.git
cd mixsmith
pip install -r requirements.txt
```

### 3. Configure credentials

Copy the example env file and fill in your Spotify app details:

```bash
cp .env.example .env
```

Edit `.env`:

```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
```

### 4. Authenticate

On first run, Mixsmith opens a browser window for Spotify OAuth. After approving, it caches the token locally — you won't be asked again.

---

## Usage

```bash
# List your playlists
python -m mixsmith.cli list

# Export a playlist to Excel with full metadata
python -m mixsmith.cli export "My Playlist" --output my_playlist.xlsx

# Create a playlist from your liked songs filtered by genre
python -m mixsmith.cli create --source liked --filter genre=Shoegaze --name "Japanese Shoegaze"

# Sort a playlist with smart artist spacing
python -m mixsmith.cli sort "My Playlist" --method declump

# Find songs in your liked songs not in any playlist
python -m mixsmith.cli orphans
```

---

## Project structure

```
src/mixsmith/
├── connectors/     # Spotify API client & OAuth
├── core/           # Filtering, sorting, sequencing logic
├── ai/             # Natural-language interpretation (planned)
├── exporters/      # Excel & CSV export
├── utils/          # Language detection, genre mapping, metadata helpers
└── cli/            # Command-line interface
```

---

## Spotify API note

Mixsmith uses the official Spotify Web API. Apps in Development Mode are limited to 25 users. For broader use, your app must be reviewed by Spotify.

---

## Roadmap

- [ ] Natural-language playlist creation via Gemini
- [ ] Playlist DNA — human-readable profile of what's in a playlist
- [ ] Cross-playlist overlap & similarity map
- [ ] Version control with undo & diff
- [ ] Constraint-based generation (min/max per artist, duration targets, mood arc)
- [ ] Duplicate intelligence (remasters, live versions, alternate credits)
- [ ] Hidden Gems finder

---

## License

MIT
