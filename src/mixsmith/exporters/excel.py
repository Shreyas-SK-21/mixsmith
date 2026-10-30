"""Styled multi-sheet Excel exporter for Mixsmith."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from mixsmith.core.models import Playlist, Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.export.excel")


def export_tracks_to_excel(
    tracks: list[Track],
    output_path: str | Path,
    playlist_name: str = "Mixsmith Playlist"
) -> str:
    """Exports enriched tracks and overview insights to a styled Excel workbook."""
    output_file = Path(output_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()

    # Sheet 1: Tracks
    ws_tracks = wb.active
    ws_tracks.title = "Tracks"
    ws_tracks.views.sheetView[0].showGridLines = True

    green_fill = PatternFill(start_color="1DB954", end_color="1DB954", fill_type="solid")
    dark_fill = PatternFill(start_color="191414", end_color="191414", fill_type="solid")
    zebra_fill = PatternFill(start_color="F7F9F8", end_color="F7F9F8", fill_type="solid")

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Segoe UI", size=10)
    link_font = Font(name="Segoe UI", size=10, color="0066CC", underline="single")
    bold_font = Font(name="Segoe UI", size=10, bold=True)
    title_font = Font(name="Segoe UI", size=14, bold=True, color="1DB954")
    subtitle_font = Font(name="Segoe UI", size=11, italic=True)

    thin_border = Border(
        left=Side(style="thin", color="E0E0E0"),
        right=Side(style="thin", color="E0E0E0"),
        top=Side(style="thin", color="E0E0E0"),
        bottom=Side(style="thin", color="E0E0E0")
    )

    headers = [
        ("#", 6),
        ("Track Name", 32),
        ("Artist(s)", 26),
        ("Album", 26),
        ("Album Type", 14),
        ("Primary Genre", 20),
        ("Theme / Vibe", 22),
        ("Era / Decade", 18),
        ("Release Year", 14),
        ("Language / Region", 20),
        ("Popularity Tier", 18),
        ("Duration", 10),
        ("Length Category", 18),
        ("Rating", 11),
        ("All Genres", 32),
        ("ISRC", 16),
        ("Spotify URL", 36),
    ]

    for col_idx, (col_name, width) in enumerate(headers, 1):
        cell = ws_tracks.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = dark_fill
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 5, 9, 12, 14] else "left", vertical="center")
        col_letter = get_column_letter(col_idx)
        ws_tracks.column_dimensions[col_letter].width = width

    ws_tracks.row_dimensions[1].height = 28

    for row_idx, t in enumerate(tracks, 2):
        row_fill = zebra_fill if row_idx % 2 == 0 else None
        pop_tier = "Superstar Hit" if t.popularity >= 75 else ("Mainstream Popular" if t.popularity >= 50 else ("Moderate" if t.popularity >= 25 else "Hidden Gem"))
        length_cat = "Quick Track (<2:30)" if t.duration_ms < 150000 else ("Standard (2:30-5:00)" if t.duration_ms <= 300000 else "Extended / Epic (>5:00)")

        row_data = [
            row_idx - 1,
            t.name,
            t.artist_display,
            t.album,
            t.album_type,
            t.primary_genre,
            t.theme,
            f"{t.era} ({t.decade})",
            t.release_year or "",
            t.language,
            pop_tier,
            t.duration_formatted,
            length_cat,
            "Explicit" if t.explicit else "Clean",
            ", ".join(t.all_genres),
            t.isrc,
            t.spotify_url,
        ]

        for col_idx, val in enumerate(row_data, 1):
            cell = ws_tracks.cell(row=row_idx, column=col_idx, value=val)
            cell.font = regular_font
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 9, 12]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [14]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if val == "Explicit":
                    cell.font = Font(name="Segoe UI", size=10, bold=True, color="CC0000")
                else:
                    cell.font = Font(name="Segoe UI", size=10, color="008800")
            elif col_idx == 17 and str(val).startswith("http"):
                cell.font = link_font
                cell.hyperlink = str(val)

        ws_tracks.row_dimensions[row_idx].height = 20

    # Auto-filter and freeze header row
    ws_tracks.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(tracks) + 1}"
    ws_tracks.freeze_panes = "A2"

    # Sheet 2: Overview & Insights
    ws_summary = wb.create_sheet(title="Overview & Insights")
    ws_summary.views.sheetView[0].showGridLines = True

    # Title Banner
    ws_summary.cell(row=1, column=1, value=f"{playlist_name} — Musical DNA").font = title_font
    total_seconds = sum(t.duration_ms for t in tracks) // 1000
    hours = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
    ws_summary.cell(row=2, column=1, value=f"Total Tracks: {len(tracks)} | Runtime: {duration_str}").font = subtitle_font

    ws_summary.row_dimensions[1].height = 24
    ws_summary.row_dimensions[2].height = 18

    def write_breakdown_table(start_row: int, title: str, counts: Counter, total: int):
        ws_summary.cell(row=start_row, column=1, value=title).font = bold_font
        ws_summary.cell(row=start_row + 1, column=1, value="Category").font = header_font
        ws_summary.cell(row=start_row + 1, column=1).fill = green_fill
        ws_summary.cell(row=start_row + 1, column=2, value="Tracks").font = header_font
        ws_summary.cell(row=start_row + 1, column=2).fill = green_fill
        ws_summary.cell(row=start_row + 1, column=3, value="Share %").font = header_font
        ws_summary.cell(row=start_row + 1, column=3).fill = green_fill

        curr = start_row + 2
        for item, count in counts.most_common(12):
            pct = f"{(count / total) * 100:.1f}%" if total > 0 else "0.0%"
            c1 = ws_summary.cell(row=curr, column=1, value=item)
            c2 = ws_summary.cell(row=curr, column=2, value=count)
            c3 = ws_summary.cell(row=curr, column=3, value=pct)
            for c in (c1, c2, c3):
                c.font = regular_font
                c.border = thin_border
            c2.alignment = Alignment(horizontal="center")
            c3.alignment = Alignment(horizontal="center")
            curr += 1
        return curr + 2

    n_total = len(tracks)
    r = 4
    r = write_breakdown_table(r, "Primary Genres", Counter(t.primary_genre for t in tracks), n_total)
    r = write_breakdown_table(r, "Eras & Decades", Counter(t.decade for t in tracks), n_total)
    r = write_breakdown_table(r, "Themes & Vibes", Counter(t.theme for t in tracks), n_total)
    r = write_breakdown_table(r, "Languages & Regions", Counter(t.language for t in tracks), n_total)

    ws_summary.column_dimensions["A"].width = 28
    ws_summary.column_dimensions["B"].width = 12
    ws_summary.column_dimensions["C"].width = 12

    wb.save(output_file)
    logger.info(f"Saved styled Excel workbook with {len(tracks)} tracks to {output_file}")
    return str(output_file)


def export_playlist_to_excel(playlist: Playlist, output_path: str | Path) -> str:
    """Exports playlist to Excel workbook."""
    return export_tracks_to_excel(playlist.tracks, output_path, playlist_name=playlist.name)
