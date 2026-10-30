"""Mixsmith CLI - Command-Line Interface for Music Curation."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

# Safe UTF-8 encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mixsmith.ai.parser import execute_natural_language_curation
from mixsmith.auth.manager import OAuthManager
from mixsmith.connectors.spotify import SpotifyConnector
from mixsmith.core.dedup import deduplicate_tracks, find_duplicates
from mixsmith.core.filters import filter_tracks
from mixsmith.core.manager import (
    compare_playlists,
    save_playlist_snapshot,
    split_by_decade,
    split_by_genre,
)
from mixsmith.core.models import Playlist, Track
from mixsmith.core.sequencing import ConstraintSequencingEngine, CurationConstraints
from mixsmith.exporters.csv import export_tracks_to_csv
from mixsmith.exporters.excel import export_tracks_to_excel
from mixsmith.utils.config import AppConfig, get_default_config_dir
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.cli")


def load_tracks_from_source(
    connector: Optional[SpotifyConnector],
    file_input: Optional[str],
    playlist_input: Optional[str]
) -> Tuple[List[Track], str]:
    """Loads tracks from an Excel file, CSV file, or live Spotify playlist."""
    if file_input:
        path = Path(file_input).resolve()
        if not path.exists():
            print(f"[ERROR] Source file not found: {path}", file=sys.stderr)
            sys.exit(1)

        tracks: List[Track] = []
        if path.suffix.lower() == ".csv":
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tracks.append(Track.from_dict(row))
            return tracks, path.stem

        elif path.suffix.lower() in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb["Tracks"] if "Tracks" in wb.sheetnames else wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return [], path.stem
            header = [str(c or "").strip() for c in rows[0]]
            for r in rows[1:]:
                row_dict = dict(zip(header, r))
                tracks.append(Track.from_dict(row_dict))
            return tracks, path.stem

    if playlist_input:
        conn = connector or SpotifyConnector()
        playlist = conn.get_playlist(playlist_input)
        return playlist.tracks, playlist.name

    # Check default directory for any exported playlist
    default_dir = Path.cwd()
    csv_candidates = list(default_dir.glob("*.csv"))
    if csv_candidates:
        print(f"Loading tracks from found CSV: {csv_candidates[0].name}")
        return load_tracks_from_source(connector, str(csv_candidates[0]), None)

    print("[ERROR] Please specify a source via --from-excel, --input, or --playlist", file=sys.stderr)
    sys.exit(1)


# --- Command Handlers ---

def handle_auth(args):
    config = AppConfig.load()
    auth = OAuthManager(config)

    if args.auth_cmd == "status":
        print("\n=== Mixsmith Authentication Status ===")
        print(f"Config File: {config.credentials_file}")
        print(f"Client ID: {'Configured' if config.client_id else 'Missing'}")
        print(f"Client Secret: {'Configured' if config.client_secret else 'Missing'}")
        print(f"Access Token: {'Present' if config.access_token else 'Missing'}")
        print(f"Refresh Token: {'Present' if config.refresh_token else 'Missing'}")
        if config.access_token or config.refresh_token:
            try:
                conn = SpotifyConnector(config=config, auth_manager=auth)
                me = conn.get_me()
                print(f"[OK] Authenticated as: {me.get('display_name')} (ID: {me.get('id')})")
            except Exception as e:
                print(f"[WARNING] Token verification failed: {e}")
        else:
            print("[INFO] Not authenticated. Run 'mixsmith auth login' to authenticate.")

    elif args.auth_cmd == "setup":
        client_id = input("Enter Spotify Client ID: ").strip()
        client_secret = input("Enter Spotify Client Secret: ").strip()
        config.client_id = client_id
        config.client_secret = client_secret
        config.save_tokens(access_token="", refresh_token="")
        print("Credentials saved. Starting OAuth login flow...")
        auth.authorize_interactive()

    elif args.auth_cmd == "login":
        auth.authorize_interactive()

    elif args.auth_cmd == "set-token":
        config.save_tokens(access_token=args.token.strip())
        print("[SUCCESS] Access token saved.")


def handle_list_playlists(args):
    conn = SpotifyConnector()
    playlists = conn.list_playlists(limit=args.limit)
    print(f"\nYour Spotify Playlists ({len(playlists)} found):")
    print(f"{'#':<4} {'Name':<35} {'Tracks':<8} {'ID'}")
    print("-" * 75)
    for idx, p in enumerate(playlists, 1):
        print(f"{idx:<4} {p['name'][:33]:<35} {p['total_tracks']:<8} {p['id']}")


def handle_export(args):
    conn = SpotifyConnector()
    playlist = conn.get_playlist(args.playlist)
    out_format = args.format or ("csv" if str(args.output).endswith(".csv") else "excel")

    if out_format == "csv":
        out_path = export_tracks_to_csv(playlist.tracks, args.output)
    else:
        out_path = export_tracks_to_excel(playlist.tracks, args.output, playlist_name=playlist.name)

    print(f"[SUCCESS] Exported {len(playlist.tracks)} tracks to: {out_path}")


def handle_analyze(args):
    tracks, name = load_tracks_from_source(None, args.input, args.playlist)
    print(f"\n=== Musical DNA Analysis: {name} ===")
    print(f"Total Tracks: {len(tracks)}")
    total_sec = sum(t.duration_ms for t in tracks) // 1000
    print(f"Total Runtime: {total_sec // 3600}h {(total_sec % 3600) // 60}m")

    def show_counts(title, counter, top_n=6):
        print(f"\n-- {title} --")
        for item, count in counter.most_common(top_n):
            pct = (count / len(tracks)) * 100 if tracks else 0
            bar = "#" * int(pct / 4)
            print(f"  {item:<24} {count:>3} ({pct:>5.1f}%) {bar}")

    show_counts("Primary Genres", Counter(t.primary_genre for t in tracks))
    show_counts("Eras & Decades", Counter(t.decade for t in tracks))
    show_counts("Themes & Vibes", Counter(t.theme for t in tracks))
    show_counts("Languages & Regions", Counter(t.language for t in tracks))


def handle_filter(args):
    tracks, name = load_tracks_from_source(None, args.input, args.playlist)

    filtered = filter_tracks(
        tracks,
        artist_filter=args.artist,
        genre_filter=args.genre,
        theme_filter=args.theme,
        decade_filter=args.decade,
        language_filter=args.language,
        clean_only=args.clean,
        explicit_only=args.explicit,
        filter_expr=args.filter
    )

    if args.sort:
        engine = ConstraintSequencingEngine()
        plan = engine.curate(filtered, CurationConstraints(sort_mode=args.sort))
        filtered = plan.tracks

    print(f"\nFiltered Tracks: {len(filtered)} of {len(tracks)} matched criteria.")
    print(f"{'#':<4} {'Track Name':<30} {'Artist':<22} {'Genre':<18} {'Decade'}")
    print("-" * 80)
    for idx, t in enumerate(filtered[:args.limit], 1):
        print(f"{idx:<4} {t.name[:28]:<30} {t.primary_artist[:20]:<22} {t.primary_genre[:16]:<18} {t.decade}")

    if args.output:
        if args.output.endswith(".csv"):
            export_tracks_to_csv(filtered, args.output)
        else:
            export_tracks_to_excel(filtered, args.output, playlist_name=f"Filtered - {name}")
        print(f"[SUCCESS] Saved filtered tracks to: {args.output}")


def handle_curate(args):
    """Natural-language and constraint-based curation command."""
    conn = SpotifyConnector() if not args.from_excel else None
    tracks, source_name = load_tracks_from_source(conn, args.from_excel, args.playlist)

    if args.prompt:
        print(f"\nCurating with natural language instruction: '{args.prompt}'")
        plan, spec = execute_natural_language_curation(tracks, args.prompt)
    else:
        constraints = CurationConstraints(
            min_artist_spacing=args.spacing,
            max_tracks_per_artist=args.max_per_artist,
            target_duration_minutes=args.target_duration,
            sort_mode=args.sort
        )
        engine = ConstraintSequencingEngine()
        plan = engine.curate(tracks, constraints, playlist_name=args.name or f"Curated {source_name}")

    print(f"\n=== Curation Plan Preview: '{plan.playlist_name}' ===")
    print(f"Source Tracks: {plan.initial_track_count} -> Selected: {plan.final_track_count}")
    print("Constraints Evaluated:")
    for c in plan.constraints_evaluated:
        status_tag = "[PASS]" if c.satisfied else f"[{c.severity.upper()}]"
        print(f"  {status_tag} {c.name}: {c.details}")

    print("\nTrack Sequencing Preview (first 10 tracks):")
    for idx, t in enumerate(plan.tracks[:10], 1):
        print(f"  {idx:>2}. {t.name:<30} — {t.artist_display:<25} ({t.primary_genre})")

    # Curation Explainability Report
    if getattr(args, "explain", False) or getattr(args, "explain_output", None):
        if plan.explanation:
            fmt = getattr(args, "explain_format", "markdown")
            report_text = plan.explanation.to_json() if fmt == "json" else plan.explanation.to_markdown()
            if getattr(args, "explain", False):
                print("\n" + report_text)
            if getattr(args, "explain_output", None):
                with open(args.explain_output, "w", encoding="utf-8") as f:
                    f.write(report_text)
                print(f"\n[SUCCESS] Saved explanation report to {args.explain_output}")

    if args.dry_run:
        print("\n[DRY RUN] No modifications were made to Spotify.")
        return

    # Check for confirmation
    if not args.confirm:
        resp = input(f"\nCreate Spotify playlist '{plan.playlist_name}' with {len(plan.tracks)} tracks? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("Operation cancelled by user.")
            return

    # Execute playlist creation on Spotify
    conn = SpotifyConnector()
    created = conn.create_playlist(
        name=args.name or plan.playlist_name,
        description=f"Curated by Mixsmith ({plan.final_track_count} tracks)",
        public=args.public,
        tracks=plan.tracks
    )
    print(f"\n[SUCCESS] Playlist created on Spotify!")
    print(f"URL: {created.url}")


def handle_dedup(args):
    """Deduplication command with version intelligence."""
    tracks, name = load_tracks_from_source(None, args.input, args.playlist)
    groups = find_duplicates(tracks)

    print(f"\n=== Deduplication Analysis: {name} ===")
    print(f"Identified {len(groups)} duplicate clusters across {len(tracks)} tracks.")

    for idx, g in enumerate(groups[:8], 1):
        print(f"\nCluster #{idx} [{g.category.upper()}]: '{g.canonical_track.name}' by {g.canonical_track.primary_artist}")
        print(f"  Canonical: {g.canonical_track.name} (Album: {g.canonical_track.album})")
        for v in g.variants:
            print(f"  Variant  : {v.name} (Album: {v.album})")

    if args.dry_run:
        print("\n[DRY RUN] Run without --dry-run to apply deduplication.")
        return

    deduped, _ = deduplicate_tracks(tracks, strategy=args.strategy)
    print(f"\nDeduplicated playlist: {len(tracks)} -> {len(deduped)} tracks (Strategy: {args.strategy}).")

    if args.output:
        if args.output.endswith(".csv"):
            export_tracks_to_csv(deduped, args.output)
        else:
            export_tracks_to_excel(deduped, args.output, playlist_name=f"Deduped {name}")
        print(f"[SUCCESS] Saved deduplicated collection to: {args.output}")


def handle_compare(args):
    """Compare two playlists."""
    t1, name1 = load_tracks_from_source(None, args.input_1, args.playlist_1)
    t2, name2 = load_tracks_from_source(None, args.input_2, args.playlist_2)

    p1 = Playlist(id="p1", name=name1, tracks=t1)
    p2 = Playlist(id="p2", name=name2, tracks=t2)

    diff = compare_playlists(p1, p2)
    print(f"\n=== Playlist Overlap Analysis ===")
    print(f"Playlist A: {name1} ({len(t1)} tracks)")
    print(f"Playlist B: {name2} ({len(t2)} tracks)")
    print(f"Common Tracks: {diff['common_count']}")
    print(f"Unique to A  : {diff['unique_to_p1_count']}")
    print(f"Unique to B  : {diff['unique_to_p2_count']}")
    print(f"Jaccard Similarity: {diff['jaccard_similarity']}%")


def main():
    parser = argparse.ArgumentParser(
        prog="mixsmith",
        description="Mixsmith: Production-Grade Music Curation and Sequencing Engine"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: auth
    p_auth = subparsers.add_parser("auth", help="Manage Spotify API authentication")
    p_auth_sub = p_auth.add_subparsers(dest="auth_cmd", required=True)
    p_auth_sub.add_parser("status", help="Check current authentication status")
    p_auth_sub.add_parser("setup", help="Configure Client ID/Secret and authenticate")
    p_auth_sub.add_parser("login", help="Log in via Spotify OAuth in browser")
    p_set_token = p_auth_sub.add_parser("set-token", help="Directly set OAuth token")
    p_set_token.add_argument("token", help="Spotify Bearer token")

    # Subcommand: list-playlists
    p_list = subparsers.add_parser("list-playlists", help="List user's Spotify playlists")
    p_list.add_argument("--limit", type=int, default=50, help="Max playlists to retrieve")

    # Subcommand: export
    p_export = subparsers.add_parser("export", help="Export playlist to Excel or CSV")
    p_export.add_argument("--playlist", required=True, help="Playlist ID, URL, or 'liked'")
    p_export.add_argument("--output", default="playlist.xlsx", help="Output file path (.xlsx or .csv)")
    p_export.add_argument("--format", choices=["excel", "csv"], help="Export format")

    # Subcommand: analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze genres, themes, and decades")
    p_analyze.add_argument("--input", help="Source file (.xlsx or .csv)")
    p_analyze.add_argument("--playlist", help="Spotify Playlist ID/URL")

    # Subcommand: filter
    p_filter = subparsers.add_parser("filter", help="Filter and sort tracks")
    p_filter.add_argument("--input", help="Source file (.xlsx or .csv)")
    p_filter.add_argument("--playlist", help="Spotify Playlist ID/URL")
    p_filter.add_argument("--artist", help="Filter by artist name(s)")
    p_filter.add_argument("--genre", help="Filter by genre")
    p_filter.add_argument("--theme", help="Filter by theme")
    p_filter.add_argument("--decade", help="Filter by decade")
    p_filter.add_argument("--language", help="Filter by language")
    p_filter.add_argument("--clean", action="store_true", help="Clean tracks only")
    p_filter.add_argument("--explicit", action="store_true", help="Explicit tracks only")
    p_filter.add_argument("--filter", help="AST filter expression")
    p_filter.add_argument("--sort", help="Sorting method (e.g. declump, chronological, decade, genre)")
    p_filter.add_argument("--limit", type=int, default=20, help="Max preview rows")
    p_filter.add_argument("--output", help="Save filtered tracks to file")

    # Subcommand: curate (Natural language & constraint sequencing)
    p_curate = subparsers.add_parser("curate", help="Curate playlists using natural language or constraints")
    p_curate.add_argument("--prompt", help="Natural language instruction (e.g. '2-hour late night drive with The Weeknd')")
    p_curate.add_argument("--name", help="Name for the curated playlist")
    p_curate.add_argument("--from-excel", help="Source tracks from file (.xlsx or .csv)")
    p_curate.add_argument("--playlist", help="Source tracks live from Spotify playlist")
    p_curate.add_argument("--spacing", type=int, default=1, help="Min artist spacing (default: 1)")
    p_curate.add_argument("--max-per-artist", type=int, help="Max tracks allowed per artist")
    p_curate.add_argument("--target-duration", type=int, help="Target duration in minutes")
    p_curate.add_argument("--sort", help="Sequencing journey (declump, chronological, decade, genre, nostalgia)")
    p_curate.add_argument("--dry-run", action="store_true", help="Preview plan without creating on Spotify")
    p_curate.add_argument("--confirm", action="store_true", help="Auto-confirm Spotify creation")
    p_curate.add_argument("--public", action="store_true", help="Make playlist public")
    p_curate.add_argument("--explain", action="store_true", help="Display comprehensive curation explanation report")
    p_curate.add_argument("--explain-format", choices=["markdown", "json"], default="markdown", help="Format for explanation report")
    p_curate.add_argument("--explain-output", help="Save explanation report to file (e.g. report.md)")

    # Subcommand: dedup
    p_dedup = subparsers.add_parser("dedup", help="Detect and resolve duplicates and version variants")
    p_dedup.add_argument("--input", help="Source file (.xlsx or .csv)")
    p_dedup.add_argument("--playlist", help="Spotify Playlist ID/URL")
    p_dedup.add_argument("--strategy", choices=["exact_only", "keep_original", "keep_remaster", "keep_all"], default="exact_only")
    p_dedup.add_argument("--dry-run", action="store_true", help="Preview duplicates without modifying")
    p_dedup.add_argument("--output", help="Save deduplicated tracks to file")

    # Subcommand: compare
    p_comp = subparsers.add_parser("compare", help="Compare two playlists for overlap and differences")
    p_comp.add_argument("--playlist-1", help="Spotify Playlist 1")
    p_comp.add_argument("--input-1", help="File for Playlist 1")
    p_comp.add_argument("--playlist-2", help="Spotify Playlist 2")
    p_comp.add_argument("--input-2", help="File for Playlist 2")

    # Backward compatibility: create-playlist
    p_create = subparsers.add_parser("create-playlist", help="Create Spotify playlist (legacy alias for curate)")
    p_create.add_argument("--name", required=True, help="Playlist name")
    p_create.add_argument("--from-excel", help="Source tracks from file")
    p_create.add_argument("--playlist", help="Source tracks from Spotify")
    p_create.add_argument("--artist", help="Filter by artist")
    p_create.add_argument("--genre", help="Filter by genre")
    p_create.add_argument("--theme", help="Filter by theme")
    p_create.add_argument("--decade", help="Filter by decade")
    p_create.add_argument("--sort", help="Sort method")
    p_create.add_argument("--public", action="store_true", help="Make public")
    p_create.add_argument("--confirm", action="store_true", help="Confirm creation")

    # Subcommand: delete-playlist
    p_del = subparsers.add_parser("delete-playlist", help="Delete (unfollow) a Spotify playlist")
    p_del.add_argument("--playlist", required=True, help="Playlist ID or URL")
    p_del.add_argument("--confirm", action="store_true", help="Confirm deletion")

    args = parser.parse_args()

    if args.command == "auth":
        handle_auth(args)
    elif args.command == "list-playlists":
        handle_list_playlists(args)
    elif args.command == "export":
        handle_export(args)
    elif args.command == "analyze":
        handle_analyze(args)
    elif args.command == "filter":
        handle_filter(args)
    elif args.command == "curate":
        handle_curate(args)
    elif args.command == "dedup":
        handle_dedup(args)
    elif args.command == "compare":
        handle_compare(args)
    elif args.command == "create-playlist":
        # Route to curate for consistent safe mutation handling
        args.prompt = None
        args.spacing = 1
        args.max_per_artist = None
        args.target_duration = None
        args.dry_run = False
        handle_curate(args)
    elif args.command == "delete-playlist":
        if not args.confirm:
            ans = input(f"Are you sure you want to delete playlist {args.playlist}? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("Deletion cancelled.")
                return
        conn = SpotifyConnector()
        conn.delete_playlist(args.playlist)
        print(f"[SUCCESS] Unfollowed playlist {args.playlist}")


if __name__ == "__main__":
    main()
