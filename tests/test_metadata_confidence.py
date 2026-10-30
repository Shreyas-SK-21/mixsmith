"""Tests for confidence-aware metadata inference and user overrides."""

from mixsmith.utils.metadata import (
    MetadataConfidence,
    MetadataProvenance,
    infer_language_and_region,
    infer_primary_genre,
    infer_theme,
)


def test_user_override_confidence():
    """Explicit user overrides must always receive KNOWN confidence."""
    res = infer_language_and_region(
        isrc="US123456",
        genres=["indie"],
        title="Unknown Song",
        artists=["Artist"],
        user_override="Spanish"
    )
    assert res.value == "Spanish"
    assert res.confidence == MetadataConfidence.KNOWN
    assert res.provenance == MetadataProvenance.USER_OVERRIDE


def test_unicode_script_high_confidence():
    """Unicode Japanese, Korean, Devanagari scripts must yield HIGH confidence."""
    # Japanese Kanji/Kana
    res_jp = infer_language_and_region(
        isrc="",
        genres=[],
        title="夜を駆ける",
        artists=["スピッツ"]
    )
    assert res_jp.value == "Japanese"
    assert res_jp.confidence == MetadataConfidence.HIGH
    assert res_jp.provenance == MetadataProvenance.UNICODE_SCRIPT

    # Korean Hangul
    res_kr = infer_language_and_region(
        isrc="",
        genres=[],
        title="봄날 (Spring Day)",
        artists=["방탄소년단"]
    )
    assert res_kr.value == "Korean"
    assert res_kr.confidence == MetadataConfidence.HIGH
    assert res_kr.provenance == MetadataProvenance.UNICODE_SCRIPT

    # Devanagari
    res_in = infer_language_and_region(
        isrc="",
        genres=[],
        title="तुम ही हो",
        artists=["अरिजीत सिंह"]
    )
    assert res_in.value == "Hindi / Desi"
    assert res_in.confidence == MetadataConfidence.HIGH
    assert res_in.provenance == MetadataProvenance.UNICODE_SCRIPT


def test_instrumental_detection():
    """Instrumental and ambient recordings should not be forced into vocal language buckets."""
    res = infer_language_and_region(
        isrc="US123456",
        genres=["ambient", "drone"],
        title="Weightless (Ambient Version) - Instrumental",
        artists=["Marconi Union"]
    )
    assert res.value == "Instrumental / Non-Vocal"
    assert res.confidence == MetadataConfidence.HIGH
    assert res.provenance == MetadataProvenance.TITLE_HEURISTIC


def test_isrc_country_medium_confidence():
    """ISRC country code prefix yields MEDIUM confidence."""
    res = infer_language_and_region(
        isrc="FR1234567890",
        genres=[],
        title="Une Chanson",
        artists=["Artiste"]
    )
    assert res.value == "French"
    assert res.confidence == MetadataConfidence.MEDIUM
    assert res.provenance == MetadataProvenance.ISRC_COUNTRY


def test_unknown_empty_metadata():
    """Empty or uninformative tracks must report UNKNOWN confidence without arbitrary guessing."""
    res_lang = infer_language_and_region(
        isrc="",
        genres=[],
        title="",
        artists=[]
    )
    assert res_lang.value == "Unspecified / Global"
    assert res_lang.confidence == MetadataConfidence.UNKNOWN
    assert res_lang.provenance == MetadataProvenance.DEFAULT_FALLBACK

    res_genre = infer_primary_genre([])
    assert res_genre.value == "Other / Unclassified"
    assert res_genre.confidence == MetadataConfidence.UNKNOWN
    assert res_genre.provenance == MetadataProvenance.DEFAULT_FALLBACK


def test_theme_inference_confidence():
    """High energy workout vs late night drive themes with appropriate confidence."""
    res_drive = infer_theme(
        title="Midnight Highway Drive",
        genres=["synthwave"],
        primary_genre="Electronic / Dance",
        release_year=2021,
        popularity=60,
        duration_ms=210000
    )
    assert res_drive.value == "Late Night Drive"
    assert res_drive.confidence == MetadataConfidence.HIGH
    assert res_drive.provenance == MetadataProvenance.TITLE_HEURISTIC

    res_heartbreak = infer_theme(
        title="Tears and Broken Heart",
        genres=["indie"],
        primary_genre="Indie / Alternative",
        release_year=2020,
        popularity=40,
        duration_ms=180000
    )
    assert res_heartbreak.value == "Heartbreak & Melancholy"
    assert res_heartbreak.confidence == MetadataConfidence.HIGH
