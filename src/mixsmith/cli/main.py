#!/usr/bin/env python3
# /// script
# dependencies = ["requests", "openpyxl"]
# ///
"""
Spotify Playlist Manager CLI - Human-Centric Music Curation
Filter, sort, and organize playlists using human terms:
Artists, Genres, Themes & Vibes, Eras & Decades, Languages & Regions, Clean vs Explicit,
and Smart Artist Spacing (De-clumper).
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Fix Windows console UTF-8 encoding for emojis and international scripts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from spotify_client import SpotifyClient, DEFAULT_CREDENTIALS_PATH


def handle_auth(args):
    client = SpotifyClient()

    if args.auth_cmd == "status":
        print(f"Credentials file: {client.credentials_path}")
        if not client.is_authenticated():
            print("Status: NOT AUTHENTICATED.")
            print("\nRun 'spotify_cli.py auth setup' or set SPOTIFY_ACCESS_TOKEN.")
            return

        try:
            me = client.get_me()
            print(f"Status: AUTHENTICATED")
            print(f"User: {me.get('display_name')} (ID: {me.get('id')})")
            print(f"Email: {me.get('email', 'N/A')}")
            print(f"Country: {me.get('country', 'N/A')}")
            print(f"Profile URL: {me.get('external_urls', {}).get('spotify')}")
        except Exception as e:
            print(f"Status: ERROR verifying credentials - {e}")

    elif args.auth_cmd == "setup":
        print("=== Spotify Developer App Setup ===")
        print("1. Go to https://developer.spotify.com/dashboard and log in.")
        print("2. Click 'Create app'.")
        print("3. In Redirect URIs, add: http://127.0.0.1:8888/callback")
        print("4. Check 'Web API' and save.")
        print("5. Go to App Settings and copy your Client ID and Client Secret.\n")

        client_id = input("Enter Spotify Client ID: ").strip()
        client_secret = input("Enter Spotify Client Secret: ").strip()
        if not client_id or not client_secret:
            print("Error: Client ID and Secret cannot be empty.", file=sys.stderr)
            return

        client.save_credentials({
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "http://127.0.0.1:8888/callback"
        })
        print(f"Credentials saved to {client.credentials_path}.")
        print("Starting interactive login...")
        client.authorize_interactive()

    elif args.auth_cmd == "login":
        client.authorize_interactive()

    elif args.auth_cmd == "set-token":
        token = args.token.strip()
        if not token:
            print("Error: Token cannot be empty.", file=sys.stderr)
            return
        client.save_credentials({"access_token": token})
        print(f"Access token saved. Verifying...")
        try:
            me = client.get_me()
            print(f"Successfully authenticated as {me.get('display_name')} ({me.get('id')})!")
        except Exception as e:
            print(f"Warning: Failed to verify token: {e}", file=sys.stderr)


def handle_list_playlists(args):
    client = SpotifyClient()
    playlists = client.list_user_playlists(limit=args.limit)
    print(f"\nFound {len(playlists)} playlists for your account:\n")
    print(f"{'#':<4} {'Name':<35} {'Tracks':<8} {'Visibility':<10} {'Playlist ID / URL'}")
    print("-" * 90)
    for idx, p in enumerate(playlists, 1):
        visibility = "Public" if p["public"] else "Private"
        name = (p["name"][:32] + "...") if len(p["name"]) > 35 else p["name"]
        print(f"{idx:<4} {name:<35} {p['tracks_count']:<8} {visibility:<10} {p['id']}")
    print("\nTip: Use 'export --playlist <ID>' to export any playlist to Excel.\n")


def handle_export(args):
    client = SpotifyClient()
    output_path = args.output
    fmt = (args.format or ("csv" if output_path.lower().endswith(".csv") else "excel")).lower()

    if fmt == "csv" and not output_path.lower().endswith(".csv"):
        output_path += ".csv"
    elif fmt != "csv" and not output_path.lower().endswith(".xlsx"):
        output_path += ".xlsx"

    print(f"Fetching playlist '{args.playlist}' and enriching with genres, themes, and eras...")
    playlist_data = client.get_playlist(args.playlist)
    
    if fmt == "csv":
        saved_path = client.export_to_csv(playlist_data, output_path)
        print(f"\n[SUCCESS] Successfully exported {len(playlist_data['tracks'])} songs to CSV (Exportify compatible)!")
    else:
        saved_path = client.export_to_excel(playlist_data, output_path)
        print(f"\n[SUCCESS] Successfully exported {len(playlist_data['tracks'])} songs to Excel workbook!")
    print(f"File location: {saved_path}")


def handle_export_all(args):
    client = SpotifyClient()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = (args.format or "excel").lower()
    ext = ".csv" if fmt == "csv" else ".xlsx"

    print(f"Fetching list of all playlists...")
    playlists = client.list_user_playlists(limit=100)
    print(f"Found {len(playlists)} playlists to export.")

    if args.include_liked:
        playlists.insert(0, {
            "id": "liked",
            "name": "Liked Songs",
            "tracks_count": "All",
            "public": False
        })

    def sanitize_filename(name: str) -> str:
        s = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        return s or "playlist"

    for idx, p in enumerate(playlists, 1):
        safe_name = sanitize_filename(p["name"])
        target_file = out_dir / f"{idx:02d}_{safe_name}{ext}"
        print(f"\n[{idx}/{len(playlists)}] Exporting '{p['name']}'...")
        try:
            data = client.get_playlist(p["id"])
            if fmt == "csv":
                client.export_to_csv(data, target_file)
            else:
                client.export_to_excel(data, target_file)
            print(f"  -> Saved {len(data['tracks'])} tracks to {target_file.name}")
        except Exception as e:
            print(f"  -> Warning: Failed to export '{p['name']}': {e}", file=sys.stderr)

    print(f"\n[SUCCESS] All {len(playlists)} playlists backed up to directory: {out_dir}")


def load_tracks_from_source(client: SpotifyClient, excel_input: Optional[str], playlist_input: Optional[str]):
    """Helper to load tracks from either an Excel file, CSV file, or live Spotify playlist."""
    default_csv = Path(r"C:\Users\shrey\.gemini\antigravity\scratch\sorted playlists\Liked_Songs.csv")
    if not excel_input and not playlist_input and default_csv.exists():
        excel_input = str(default_csv)

    if excel_input:
        input_path = Path(excel_input).resolve()
        if input_path.suffix.lower() == ".csv":
            import csv
            tracks = []
            with open(input_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uri = row.get("Track URI", "")
                    track_id = row.get("Track ID") or (uri.split(":")[-1] if uri else "") or row.get("id", "")
                    title = row.get("Track Name") or row.get("name", "")
                    artists = row.get("Artist Name(s)") or row.get("artists", "")
                    artist_list = [a.strip() for a in artists.split(",") if a.strip()]
                    primary_artist = artist_list[0] if artist_list else "Unknown"
                    genres = [g.strip() for g in (row.get("Genres") or row.get("All Genres") or row.get("genres_str") or "").split(",") if g.strip()]
                    rel_date = row.get("Release Date") or row.get("release_date", "")
                    isrc = row.get("ISRC", "")
                    pop = int(row.get("Popularity Score") or row.get("Popularity") or 0)
                    dur_ms = int(row.get("Duration (ms)") or row.get("duration_ms") or 0)
                    minutes = dur_ms // 60000
                    seconds = (dur_ms % 60000) // 1000
                    dur_fmt = row.get("Duration") or f"{minutes}:{seconds:02d}"
                    is_exp = str(row.get("Explicit", "")).lower() in ("true", "yes", "1") or row.get("Rating") == "Explicit"
                    album_name = row.get("Album Name") or row.get("album", "")
                    album_type = (row.get("Album Type") or row.get("album_type", "Album")).capitalize()

                    p_genre = row.get("Primary Genre") or client.classify_primary_genre(genres)
                    year, decade, era = client.detect_era_and_decade(rel_date)
                    lang = row.get("Language / Region") or client.detect_language_and_region(isrc, genres, title, artists)
                    theme = row.get("Theme / Vibe") or client.detect_theme(title, genres, p_genre, year, pop, dur_ms)
                    pop_tier = row.get("Popularity Tier") or client.classify_popularity_tier(pop)
                    len_cat = row.get("Length Category") or client.classify_length_category(dur_ms)

                    tracks.append({
                        "name": title,
                        "artists": artists,
                        "primary_artist": primary_artist,
                        "artist_list": artist_list,
                        "album": album_name,
                        "album_type": album_type,
                        "primary_genre": p_genre,
                        "genres": genres,
                        "genres_str": ", ".join(genres[:4]) if genres else p_genre,
                        "theme": theme,
                        "decade": decade,
                        "era": era,
                        "release_year": year,
                        "release_date": rel_date,
                        "language": lang,
                        "popularity": pop,
                        "popularity_tier": pop_tier,
                        "duration_ms": dur_ms,
                        "duration_formatted": dur_fmt,
                        "length_category": len_cat,
                        "explicit": "Explicit" if is_exp else "Clean",
                        "is_clean": not is_exp,
                        "is_explicit": is_exp,
                        "url": row.get("Spotify URL") or f"https://open.spotify.com/track/{track_id}",
                        "uri": uri or f"spotify:track:{track_id}",
                        "id": track_id,
                        "isrc": isrc,
                        "added_at": row.get("Added At", ""),
                        "added_by": row.get("Added By", "")
                    })
            return tracks, input_path.stem
        else:
            import openpyxl
            wb = openpyxl.load_workbook(input_path, data_only=True)
            ws = wb["Tracks"]
            tracks = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[1]:
                    continue
                tracks.append({
                    "name": row[1],
                    "artists": row[2],
                    "primary_artist": (row[2] or "").split(",")[0].strip(),
                    "album": row[3],
                    "album_type": row[4] if len(row) > 4 else "Album",
                    "primary_genre": row[5] if len(row) > 5 else "Pop",
                    "theme": row[6] if len(row) > 6 else "Feel-Good",
                    "decade": row[7] if len(row) > 7 else "Modern",
                    "release_year": row[8] if len(row) > 8 else 2020,
                    "language": row[9] if len(row) > 9 else "English",
                    "popularity_tier": row[10] if len(row) > 10 else "Moderate",
                    "duration_formatted": row[11] if len(row) > 11 else "3:30",
                    "length_category": row[12] if len(row) > 12 else "Standard",
                    "explicit": row[13] if len(row) > 13 else "Clean",
                    "is_clean": row[13] == "Clean" if len(row) > 13 else True,
                    "is_explicit": row[13] == "Explicit" if len(row) > 13 else False,
                    "genres_str": row[14] if len(row) > 14 else "",
                    "genres": [g.strip() for g in (row[14] or "").split(",") if g.strip()] if len(row) > 14 else [],
                    "url": row[18] if len(row) > 18 else "",
                    "uri": row[19] if len(row) > 19 else "",
                    "id": row[20] if len(row) > 20 else "",
                    "added_at": row[17] if len(row) > 17 else ""
                })
            return tracks, input_path.stem
    elif playlist_input:
        data = client.get_playlist(playlist_input)
        return data["tracks"], data["name"]
    else:
        raise ValueError("Must specify either --input <excel_file> or --playlist <id>")


def handle_analyze(args):
    client = SpotifyClient()
    tracks, playlist_name = load_tracks_from_source(client, args.input, args.playlist)

    from collections import defaultdict
    genre_counts = defaultdict(int)
    theme_counts = defaultdict(int)
    decade_counts = defaultdict(int)
    lang_counts = defaultdict(int)
    artist_counts = defaultdict(int)
    clean_count = sum(1 for t in tracks if t.get("is_clean"))
    explicit_count = sum(1 for t in tracks if t.get("is_explicit"))

    for t in tracks:
        genre_counts[t.get("primary_genre") or "Other"] += 1
        theme_counts[t.get("theme") or "Other"] += 1
        decade_counts[t.get("decade") or "Other"] += 1
        lang_counts[t.get("language") or "Other"] += 1
        for a in t.get("artist_list", [t.get("primary_artist", "Unknown")]):
            artist_counts[a] += 1

    print(f"\n{'='*70}")
    print(f"🎵 Human Analysis: {playlist_name} ({len(tracks)} songs)")
    print(f"{'='*70}")

    print("\n🎧 Top Genres:")
    for g, c in sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6]:
        pct = round((c / len(tracks)) * 100)
        bar = "█" * (pct // 5)
        print(f"  • {g:<22} {c:>3} songs ({pct:>2}%) {bar}")

    print("\n🌟 Themes & Vibes:")
    for th, c in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:6]:
        pct = round((c / len(tracks)) * 100)
        print(f"  • {th:<22} {c:>3} songs ({pct:>2}%)")

    print("\n🕰️ Eras & Decades:")
    for d, c in sorted(decade_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {d:<15} {c:>3} songs")

    print("\n🌍 Languages & Cultural Regions:")
    for l, c in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  • {l:<22} {c:>3} songs")

    print("\n🎤 Top Artists:")
    for a, c in sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:6]:
        print(f"  • {a:<24} {c} songs")

    print(f"\n🛡️ Content Advisory: {clean_count} Clean | {explicit_count} Explicit")
    print(f"{'='*70}\n")


def handle_filter(args):
    client = SpotifyClient()
    tracks, playlist_name = load_tracks_from_source(client, args.input, args.playlist)

    filtered = client.filter_and_sort_tracks(
        tracks=tracks,
        filter_expr=args.filter,
        artist_filter=args.artist,
        genre_filter=args.genre,
        theme_filter=args.theme,
        decade_filter=args.decade,
        language_filter=args.language,
        clean_only=args.clean,
        explicit_only=args.explicit,
        sort_by=args.sort
    )

    print(f"\nFiltered down to {len(filtered)} out of {len(tracks)} songs.")
    if args.artist: print(f"  • Artist match: {args.artist}")
    if args.genre: print(f"  • Genre match: {args.genre}")
    if args.theme: print(f"  • Theme match: {args.theme}")
    if args.decade: print(f"  • Decade match: {args.decade}")
    if args.language: print(f"  • Language match: {args.language}")
    if args.clean: print("  • Rating: Clean only")
    if args.explicit: print("  • Rating: Explicit only")
    if args.sort: print(f"  • Sorted by: {args.sort}")

    print(f"\n{'#':<4} {'Song Title':<28} {'Artist':<22} {'Genre':<18} {'Theme / Vibe':<20} {'Decade':<8}")
    print("-" * 105)
    for idx, t in enumerate(filtered[:args.limit], 1):
        name = (t["name"][:25] + "...") if len(t["name"]) > 28 else t["name"]
        artist = (t["artists"][:19] + "...") if len(t["artists"]) > 22 else t["artists"]
        genre = (t.get("primary_genre") or "Pop")[:18]
        theme = (t.get("theme") or "Feel-Good")[:20]
        decade = t.get("decade") or "Modern"
        print(f"{idx:<4} {name:<28} {artist:<22} {genre:<18} {theme:<20} {decade:<8}")

    if len(filtered) > args.limit:
        print(f"... and {len(filtered) - args.limit} more songs.")

    if args.output:
        playlist_data = {
            "name": f"Filtered ({args.genre or args.theme or args.artist or 'Custom'})",
            "description": f"Curated by Spotify Playlist Manager (Sort: {args.sort or 'Default'})",
            "owner": "Spotify Playlist Manager",
            "tracks": filtered
        }
        saved_path = client.export_to_excel(playlist_data, args.output)
        print(f"\nSaved filtered results to Excel: {saved_path}")


def handle_create_playlist(args):
    client = SpotifyClient()
    tracks, playlist_name = load_tracks_from_source(client, args.from_excel, args.playlist)

    filtered = client.filter_and_sort_tracks(
        tracks=tracks,
        filter_expr=args.filter,
        artist_filter=args.artist,
        genre_filter=args.genre,
        theme_filter=args.theme,
        decade_filter=args.decade,
        language_filter=args.language,
        clean_only=args.clean,
        explicit_only=args.explicit,
        sort_by=args.sort
    )

    if not filtered:
        print("No songs matched the filter criteria! Playlist creation cancelled.")
        return

    track_uris = [t["uri"] for t in filtered if t.get("uri")]
    if not track_uris:
        track_uris = [f"spotify:track:{t['id']}" for t in filtered if t.get("id")]

    print(f"\nPreparing to create new Spotify playlist '{args.name}' with {len(track_uris)} songs.")
    if args.artist: print(f"  • Artist: {args.artist}")
    if args.genre: print(f"  • Genre: {args.genre}")
    if args.theme: print(f"  • Theme: {args.theme}")
    if args.decade: print(f"  • Decade: {args.decade}")
    if args.language: print(f"  • Language: {args.language}")
    if args.sort: print(f"  • Sort: {args.sort}")

    desc = args.description or f"Curated playlist: {args.genre or args.theme or 'Filtered songs'} (Sorted by: {args.sort or 'Natural'})"
    res = client.create_playlist(
        name=args.name,
        description=desc,
        public=args.public,
        track_uris=track_uris
    )

    print("\n[SUCCESS] New Spotify playlist created!")
    print(f"Name: {res['name']}")
    print(f"Total Songs: {res['total_tracks']}")
    print(f"Spotify URL: {res['url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Spotify Playlist Manager - Human-centric music filtering, smart sorting, Excel export, and playlist generation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: auth
    p_auth = subparsers.add_parser("auth", help="Manage Spotify API authentication")
    p_auth_sub = p_auth.add_subparsers(dest="auth_cmd", required=True)
    p_auth_sub.add_parser("status", help="Check current authentication status and user details")
    p_auth_sub.add_parser("setup", help="Configure Spotify Client ID & Secret and start login")
    p_auth_sub.add_parser("login", help="Open browser to log in via Spotify OAuth")
    p_set_token = p_auth_sub.add_parser("set-token", help="Directly set an OAuth access token")
    p_set_token.add_argument("token", help="Spotify Bearer token")

    # Subcommand: list-playlists
    p_list = subparsers.add_parser("list-playlists", help="List user's Spotify playlists")
    p_list.add_argument("--limit", type=int, default=50, help="Max playlists to retrieve (default: 50)")

    # Subcommand: export
    p_export = subparsers.add_parser("export", help="Scrape playlist and export to formatted Excel or CSV (Exportify compatible)")
    p_export.add_argument("--playlist", required=True, help="Playlist ID, URI, 'liked', or open.spotify.com URL")
    p_export.add_argument("--output", default="spotify_playlist.xlsx", help="Destination file path (.xlsx or .csv)")
    p_export.add_argument("--format", choices=["excel", "csv"], help="Export format: 'excel' (.xlsx) or 'csv' (Exportify compatible)")

    # Subcommand: export-all (Bulk Exportify)
    p_export_all = subparsers.add_parser("export-all", help="Bulk export all user playlists and Liked Songs into a folder")
    p_export_all.add_argument("--output-dir", default="spotify_backups", help="Target directory for all exported playlists")
    p_export_all.add_argument("--format", choices=["excel", "csv"], default="excel", help="File format: 'excel' (.xlsx) or 'csv'")
    p_export_all.add_argument("--include-liked", action="store_true", default=True, help="Include Liked Songs library in export (default: True)")
    p_export_all.add_argument("--no-liked", action="store_false", dest="include_liked", help="Skip Liked Songs library")

    # Subcommand: analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze genres, themes, decades, languages, and artists")
    p_analyze.add_argument("--input", help="Path to previously exported Excel (.xlsx) file")
    p_analyze.add_argument("--playlist", help="Spotify Playlist ID, URI, or URL to analyze live")

    # Subcommand: filter
    p_filter = subparsers.add_parser("filter", help="Filter and sort songs by human categories")
    p_filter.add_argument("--input", help="Source Excel (.xlsx) file")
    p_filter.add_argument("--playlist", help="Source Spotify Playlist ID/URL")
    p_filter.add_argument("--artist", help="Filter by artist name(s), comma-separated e.g. 'Taylor Swift, Drake'")
    p_filter.add_argument("--genre", help="Filter by genre e.g. 'Rock', 'Hip-Hop', 'Pop', 'K-Pop', 'R&B'")
    p_filter.add_argument("--theme", help="Filter by theme e.g. 'workout', 'late-night', 'chill', 'party', 'road-trip', 'focus'")
    p_filter.add_argument("--decade", help="Filter by decade e.g. '90s', '80s', '2000s', '2010s', '2020s'")
    p_filter.add_argument("--language", help="Filter by language/region e.g. 'English', 'Spanish', 'Korean', 'Hindi'")
    p_filter.add_argument("--clean", action="store_true", help="Include only clean (radio-friendly) tracks")
    p_filter.add_argument("--explicit", action="store_true", help="Include only explicit tracks")
    p_filter.add_argument("--filter", help="Custom human expression e.g. \"genre == 'rock' and decade == '90s'\"")
    p_filter.add_argument("--sort", help="Smart sort: 'declump' (artist spacing), 'chronological', 'newest', 'genre', 'theme', 'decade', 'popularity', 'gems', 'artist', 'album'")
    p_filter.add_argument("--limit", type=int, default=20, help="Max preview rows (default: 20)")
    p_filter.add_argument("--output", help="Save filtered tracks to a new Excel file")

    # Subcommand: create-playlist
    p_create = subparsers.add_parser("create-playlist", help="Create a new Spotify playlist on command")
    p_create.add_argument("--name", required=True, help="Name of the new Spotify playlist")
    p_create.add_argument("--description", help="Description for the new playlist")
    p_create.add_argument("--from-excel", help="Source tracks from an exported Excel file")
    p_create.add_argument("--playlist", help="Source tracks live from an existing playlist ID/URL")
    p_create.add_argument("--artist", help="Filter by artist name(s)")
    p_create.add_argument("--genre", help="Filter by genre")
    p_create.add_argument("--theme", help="Filter by theme")
    p_create.add_argument("--decade", help="Filter by decade")
    p_create.add_argument("--language", help="Filter by language")
    p_create.add_argument("--clean", action="store_true", help="Clean tracks only")
    p_create.add_argument("--explicit", action="store_true", help="Explicit tracks only")
    p_create.add_argument("--filter", help="Custom filter expression")
    p_create.add_argument("--sort", help="Smart sort e.g. 'declump', 'chronological', 'genre', 'theme', 'popularity'")
    p_create.add_argument("--public", action="store_true", help="Make playlist public (default: private)")

    # Subcommand: delete-playlist
    p_delete = subparsers.add_parser("delete-playlist", help="Delete (unfollow) a Spotify playlist from your account")
    p_delete.add_argument("--playlist", required=True, help="Playlist ID, URI, or URL to delete")
    p_delete.add_argument("--confirm", action="store_true", help="Acknowledge confirmation to delete")

    args = parser.parse_args()

    if args.command == "auth":
        handle_auth(args)
    elif args.command == "list-playlists":
        handle_list_playlists(args)
    elif args.command == "export":
        handle_export(args)
    elif args.command == "export-all":
        handle_export_all(args)
    elif args.command == "analyze":
        handle_analyze(args)
    elif args.command == "filter":
        handle_filter(args)
    elif args.command == "create-playlist":
        handle_create_playlist(args)
    elif args.command == "delete-playlist":
        client = SpotifyClient()
        client.delete_playlist(args.playlist)
        print(f"[SUCCESS] Playlist '{args.playlist}' has been deleted from your Spotify library.")


if __name__ == "__main__":
    main()
