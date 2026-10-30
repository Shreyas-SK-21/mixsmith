"""Unit tests for Excel and CSV Exporters."""

import csv
from pathlib import Path
import openpyxl
import pytest
from mixsmith.exporters.csv import export_tracks_to_csv, CSV_HEADERS
from mixsmith.exporters.excel import export_tracks_to_excel


def test_export_to_csv(sample_tracks, tmp_path):
    """Verifies that CSV export adheres to Exportify structure and UTF-8-sig encoding."""
    out_file = tmp_path / "test_export.csv"
    res = export_tracks_to_csv(sample_tracks, out_file)

    assert Path(res).exists()

    with open(res, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    assert header == CSV_HEADERS
    assert len(rows) == len(sample_tracks)
    assert rows[0][1] == sample_tracks[0].name


def test_export_to_excel(sample_tracks, tmp_path):
    """Verifies that Excel workbook generates both Tracks and Overview sheets with proper styling."""
    out_file = tmp_path / "test_export.xlsx"
    res = export_tracks_to_excel(sample_tracks, out_file, playlist_name="Unit Test Mix")

    assert Path(res).exists()

    wb = openpyxl.load_workbook(res)
    assert "Tracks" in wb.sheetnames
    assert "Overview & Insights" in wb.sheetnames

    ws_tracks = wb["Tracks"]
    assert ws_tracks.auto_filter.ref is not None
    assert ws_tracks.freeze_panes == "A2"
    assert ws_tracks.cell(row=2, column=2).value == sample_tracks[0].name
