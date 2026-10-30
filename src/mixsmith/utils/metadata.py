"""Human-centric music categorization and confidence-aware metadata inference."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class MetadataConfidence(str, Enum):
    """Categorical confidence level of inferred metadata."""
    KNOWN = "KNOWN"          # Explicit user override or verified external API signal
    HIGH = "HIGH"            # Strong deterministic evidence (e.g. Unicode script, explicit tag)
    MEDIUM = "MEDIUM"        # Solid correlation (e.g. subgenre taxonomy, ISRC country mapping)
    LOW = "LOW"              # Weak heuristic or lexical keyword match
    UNKNOWN = "UNKNOWN"      # Insufficient evidence; default placeholder without presumption


class MetadataProvenance(str, Enum):
    """Evidence source informing the metadata inference."""
    USER_OVERRIDE = "USER_OVERRIDE"
    VERIFIED_API = "VERIFIED_API"
    UNICODE_SCRIPT = "UNICODE_SCRIPT"
    GENRE_ASSOCIATION = "GENRE_ASSOCIATION"
    ISRC_COUNTRY = "ISRC_COUNTRY"
    TITLE_HEURISTIC = "TITLE_HEURISTIC"
    AUDIO_FEATURE = "AUDIO_FEATURE"
    DEFAULT_FALLBACK = "DEFAULT_FALLBACK"


@dataclass
class MetadataInferenceResult:
    """Encapsulates inferred value along with its confidence score and reasoning."""
    value: str
    confidence: MetadataConfidence
    provenance: MetadataProvenance
    rationale: str


def infer_primary_genre(genres_list: list[str], user_override: str | None = None) -> MetadataInferenceResult:
    """
    Infers a humanly understandable universal genre from granular subgenres,
    tracking confidence and provenance.
    """
    if user_override:
        return MetadataInferenceResult(
            value=user_override,
            confidence=MetadataConfidence.KNOWN,
            provenance=MetadataProvenance.USER_OVERRIDE,
            rationale="User-specified genre override."
        )

    if not genres_list:
        return MetadataInferenceResult(
            value="Other / Unclassified",
            confidence=MetadataConfidence.UNKNOWN,
            provenance=MetadataProvenance.DEFAULT_FALLBACK,
            rationale="No artist or track genre tags available from API."
        )

    combined = " ".join(genres_list).lower()

    genre_rules = [
        ("Shoegaze / Dream Pop", ["shoegaze", "dream pop", "nu gaze", "japanese shoegaze", "noise pop", "ethereal wave"]),
        ("K-Pop", ["k-pop", "korean pop", "korean r&b", "korean indie", "k-rock", "k-rap"]),
        ("J-Pop / Japanese", ["j-pop", "japanese pop", "anime", "j-rock", "japanese alternative", "city pop"]),
        ("Desi / South Asian", ["desi", "bollywood", "filmi", "hindi", "punjabi", "urdu", "indian indie", "tamil", "bhangra", "sufi"]),
        ("Latin", ["reggaeton", "latin", "urbano latino", "salsa", "bachata", "cumbia", "latin pop", "trap latino", "corrido", "mariachi"]),
        ("Metal", ["metal", "death metal", "black metal", "thrash", "metalcore", "heavy metal", "deathcore", "nu metal"]),
        ("Hip-Hop / Rap", ["hip hop", "rap", "trap", "drill", "boom bap", "conscious hip hop", "gangsta rap"]),
        ("R&B / Soul", ["r&b", "soul", "contemporary r&b", "neo soul", "motown", "funk", "quiet storm"]),
        ("Electronic / Dance", ["edm", "house", "techno", "electronic", "synthwave", "dance", "trance", "drum and bass", "dubstep", "electro", "ambient"]),
        ("Indie / Alternative", ["indie", "alternative", "indie rock", "indie pop", "post-punk", "grunge", "art rock", "new wave"]),
        ("Rock", ["rock", "classic rock", "hard rock", "punk", "psychedelic rock", "blues rock", "southern rock", "glam rock"]),
        ("Country / Americana", ["country", "bluegrass", "americana", "contemporary country", "alt-country", "honky tonk"]),
        ("Folk & Acoustic", ["folk", "acoustic", "singer-songwriter", "traditional folk", "celtic"]),
        ("Jazz & Blues", ["jazz", "blues", "bop", "swing", "vocal jazz", "cool jazz", "delta blues", "chicago blues"]),
        ("Classical / Cinematic", ["classical", "soundtrack", "orchestral", "film score", "baroque", "romantic", "opera", "cinematic"]),
        ("Pop", ["pop", "dance pop", "electropop", "teen pop", "art pop", "synth-pop"]),
    ]

    for genre_name, keywords in genre_rules:
        matched = [k for k in keywords if k in combined]
        if matched:
            return MetadataInferenceResult(
                value=genre_name,
                confidence=MetadataConfidence.HIGH if any(k in genres_list for k in keywords) else MetadataConfidence.MEDIUM,
                provenance=MetadataProvenance.GENRE_ASSOCIATION,
                rationale=f"Matched subgenre keywords: {matched[:3]}."
            )

    return MetadataInferenceResult(
        value="Pop / Miscellaneous",
        confidence=MetadataConfidence.LOW,
        provenance=MetadataProvenance.DEFAULT_FALLBACK,
        rationale=f"Unmatched genre tags ({genres_list[:3]}); defaulted to Pop / Miscellaneous."
    )


def classify_primary_genre(genres_list: list[str]) -> str:
    """Backward-compatible helper returning genre string."""
    return infer_primary_genre(genres_list).value


infer_genre = infer_primary_genre


def detect_era_and_decade(release_date: str) -> tuple[str, str, int]:
    """Detects human Era and Decades (e.g. '80s', 'Classic 70s') from release date."""
    if not release_date:
        return "Unknown Era", "Unknown", 0

    match = re.match(r"^(\d{4})", str(release_date).strip())
    if not match:
        return "Unknown Era", "Unknown", 0

    year = int(match.group(1))

    if year < 1960:
        return "Early Era (Pre-60s)", "Pre-60s", year
    elif 1960 <= year <= 1969:
        return "60s Revolution", "60s", year
    elif 1970 <= year <= 1979:
        return "Golden 70s", "70s", year
    elif 1980 <= year <= 1989:
        return "Electric 80s", "80s", year
    elif 1990 <= year <= 1999:
        return "Nostalgic 90s", "90s", year
    elif 2000 <= year <= 2009:
        return "Early 2000s Y2K", "2000s", year
    elif 2010 <= year <= 2019:
        return "Streaming Era (2010s)", "2010s", year
    else:
        return "Modern 2020s", "2020s", year


def infer_language_and_region(
    isrc: str,
    genres: list[str],
    title: str,
    artists: list[str],
    user_override: str | None = None
) -> MetadataInferenceResult:
    """
    Infers human language and regional music identity from Unicode script,
    ISRC prefix, and artist genres with explicit confidence and provenance tracking.
    """
    if user_override:
        return MetadataInferenceResult(
            value=user_override,
            confidence=MetadataConfidence.KNOWN,
            provenance=MetadataProvenance.USER_OVERRIDE,
            rationale="User-specified language override."
        )

    # 1. Instrumental check
    title_lower = title.lower()
    combined_genres = " ".join(genres).lower()
    instrumental_words = ["instrumental", "piano solo", "ambient version", "soundtrack", "orchestral", "lo-fi beat"]
    if any(w in title_lower for w in instrumental_words) or any(g in combined_genres for g in ["ambient", "post-rock instrumental", "classical piano"]):
        return MetadataInferenceResult(
            value="Instrumental / Non-Vocal",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.TITLE_HEURISTIC,
            rationale="Title or genre indicates instrumental / non-vocal recording."
        )

    # 2. Unicode Script Detection (Strongest deterministic evidence)
    text = f"{title} {' '.join(artists)}"
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", text):
        return MetadataInferenceResult(
            value="Japanese",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.UNICODE_SCRIPT,
            rationale="Detected Japanese Kana/Kanji script in title or artist name."
        )
    if re.search(r"[\uAC00-\uD7AF]", text):
        return MetadataInferenceResult(
            value="Korean",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.UNICODE_SCRIPT,
            rationale="Detected Korean Hangul script in title or artist name."
        )
    if re.search(r"[\u0900-\u097F]", text):
        return MetadataInferenceResult(
            value="Hindi / Desi",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.UNICODE_SCRIPT,
            rationale="Detected Devanagari script in title or artist name."
        )
    if re.search(r"[\u0600-\u06FF]", text):
        return MetadataInferenceResult(
            value="Arabic / Persian",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.UNICODE_SCRIPT,
            rationale="Detected Arabic script in title or artist name."
        )

    # 3. Genre Tags Association
    genre_lang_map = [
        (["k-pop", "korean"], "Korean"),
        (["j-pop", "japanese", "anime", "j-rock", "city pop"], "Japanese"),
        (["desi", "bollywood", "filmi", "hindi", "punjabi", "urdu", "tamil", "telugu"], "Hindi / Desi"),
        (["latin", "reggaeton", "salsa", "bachata", "cumbia", "spanish", "urbano latino"], "Spanish / Latin"),
        (["french", "chanson", "variete francaise"], "French"),
        (["german", "deutsch"], "German"),
        (["brazilian", "bossa nova", "mpb", "sertanejo", "funk carioca"], "Portuguese (Brazil)"),
    ]
    for keywords, lang in genre_lang_map:
        if any(k in combined_genres for k in keywords):
            return MetadataInferenceResult(
                value=lang,
                confidence=MetadataConfidence.MEDIUM,
                provenance=MetadataProvenance.GENRE_ASSOCIATION,
                rationale=f"Inferred from genre tags: {[k for k in keywords if k in combined_genres]}."
            )

    # 4. ISRC Country Code
    if isrc and len(isrc) >= 2:
        cc = isrc[:2].upper()
        isrc_map = {
            "JP": "Japanese",
            "KR": "Korean",
            "IN": "Hindi / Desi",
            "PK": "Hindi / Desi",
            "ES": "Spanish / Latin",
            "MX": "Spanish / Latin",
            "AR": "Spanish / Latin",
            "CO": "Spanish / Latin",
            "FR": "French",
            "DE": "German",
            "BR": "Portuguese (Brazil)",
            "IT": "Italian",
            "SE": "English (Sweden)",
            "GB": "English (UK)",
            "US": "English (US)",
            "CA": "English (Canada)",
            "AU": "English (Australia)",
        }
        if cc in isrc_map:
            return MetadataInferenceResult(
                value=isrc_map[cc],
                confidence=MetadataConfidence.MEDIUM,
                provenance=MetadataProvenance.ISRC_COUNTRY,
                rationale=f"Inferred from ISRC country prefix '{cc}'."
            )

    # 5. Default Fallback
    if not text.strip():
        return MetadataInferenceResult(
            value="Unspecified / Global",
            confidence=MetadataConfidence.UNKNOWN,
            provenance=MetadataProvenance.DEFAULT_FALLBACK,
            rationale="No text or metadata available to evaluate language."
        )

    return MetadataInferenceResult(
        value="English",
        confidence=MetadataConfidence.LOW,
        provenance=MetadataProvenance.DEFAULT_FALLBACK,
        rationale="Latin script without non-English language markers; presumed English."
    )


def detect_language_and_region(isrc: str, genres: list[str], title: str, artists: list[str]) -> str:
    """Backward-compatible helper returning language string."""
    return infer_language_and_region(isrc, genres, title, artists).value


def infer_theme(
    title: str,
    genres: list[str],
    primary_genre: str,
    release_year: int,
    popularity: int,
    duration_ms: int,
    user_override: str | None = None
) -> MetadataInferenceResult:
    """Classifies track into human themes with confidence tracking."""
    if user_override:
        return MetadataInferenceResult(
            value=user_override,
            confidence=MetadataConfidence.KNOWN,
            provenance=MetadataProvenance.USER_OVERRIDE,
            rationale="User-specified theme override."
        )

    title_lower = title.lower()
    combined_genres = " ".join(genres).lower()

    if any(w in title_lower for w in ["night", "drive", "midnight", "dark", "moon", "after hours", "highway"]):
        return MetadataInferenceResult(
            value="Late Night Drive",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.TITLE_HEURISTIC,
            rationale="Title explicitly mentions nocturnal or driving keywords."
        )

    if any(w in title_lower for w in ["gym", "run", "pump", "workout", "fitness", "beast", "energy"]) or \
       any(g in combined_genres for g in ["hardstyle", "metalcore", "workout", "trap"]):
        return MetadataInferenceResult(
            value="Workout / Gym",
            confidence=MetadataConfidence.HIGH if any(w in title_lower for w in ["gym", "workout"]) else MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.TITLE_HEURISTIC if any(w in title_lower for w in ["gym", "workout"]) else MetadataProvenance.GENRE_ASSOCIATION,
            rationale="High energy / workout markers detected."
        )

    if any(w in title_lower for w in ["chill", "coffee", "morning", "relax", "rain", "breeze", "lo-fi", "sleep"]) or \
       any(g in combined_genres for g in ["lo-fi", "ambient", "chillout", "indie folk", "acoustic"]):
        return MetadataInferenceResult(
            value="Chill & Coffee Shop",
            confidence=MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.GENRE_ASSOCIATION if combined_genres else MetadataProvenance.TITLE_HEURISTIC,
            rationale="Chill / coffee shop vibe detected."
        )

    if any(w in title_lower for w in ["party", "dance", "club", "celebrate", "shots", "disco", "rave"]) or \
       any(g in combined_genres for g in ["club", "edm", "house", "reggaeton"]):
        return MetadataInferenceResult(
            value="Party & Club",
            confidence=MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.TITLE_HEURISTIC if "party" in title_lower else MetadataProvenance.GENRE_ASSOCIATION,
            rationale="Party / club markers detected."
        )

    if any(w in title_lower for w in ["road", "trip", "travel", "summer", "sunshine", "freedom", "highway"]):
        return MetadataInferenceResult(
            value="Road Trip",
            confidence=MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.TITLE_HEURISTIC,
            rationale="Travel / road trip markers detected."
        )

    if any(w in title_lower for w in ["study", "focus", "piano", "coding", "read", "work", "calm"]) or \
       primary_genre in ["Classical / Cinematic", "Jazz & Blues"]:
        return MetadataInferenceResult(
            value="Focus & Study",
            confidence=MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.GENRE_ASSOCIATION,
            rationale="Focus & study genre profile."
        )

    if any(w in title_lower for w in ["cry", "broken", "heartbreak", "sad", "tears", "alone", "miss you", "hurt"]):
        return MetadataInferenceResult(
            value="Heartbreak & Melancholy",
            confidence=MetadataConfidence.HIGH,
            provenance=MetadataProvenance.TITLE_HEURISTIC,
            rationale="Melancholic / heartbreak sentiment detected in title."
        )

    if any(w in title_lower for w in ["love", "romance", "forever", "kiss", "sweetheart", "baby", "together"]):
        return MetadataInferenceResult(
            value="Love & Romance",
            confidence=MetadataConfidence.MEDIUM,
            provenance=MetadataProvenance.TITLE_HEURISTIC,
            rationale="Romance sentiment detected in title."
        )

    # Genre Theme fallback
    genre_theme_map = {
        "Shoegaze / Dream Pop": "Atmospheric & Dreamy",
        "Indie / Alternative": "Indie Moods",
        "Rock": "High Voltage Rock",
        "Metal": "Intense & Heavy",
        "Electronic / Dance": "Electronic Pulse",
        "Hip-Hop / Rap": "Urban & Hip-Hop",
        "R&B / Soul": "Soulful Grooves",
        "Pop": "Feel-Good Pop",
        "K-Pop": "Energetic K-Pop",
        "J-Pop / Japanese": "J-Pop Vibe",
        "Desi / South Asian": "Desi Rhythms",
        "Latin": "Fiesta Latina",
        "Folk & Acoustic": "Acoustic Warmth",
        "Country / Americana": "Down-Home Roots",
        "Jazz & Blues": "Smooth Jazz & Blues",
        "Classical / Cinematic": "Cinematic & Grand"
    }
    if primary_genre in genre_theme_map:
        return MetadataInferenceResult(
            value=genre_theme_map[primary_genre],
            confidence=MetadataConfidence.LOW,
            provenance=MetadataProvenance.DEFAULT_FALLBACK,
            rationale=f"Derived default theme from primary genre '{primary_genre}'."
        )

    return MetadataInferenceResult(
        value="Eclectic & Diverse",
        confidence=MetadataConfidence.UNKNOWN,
        provenance=MetadataProvenance.DEFAULT_FALLBACK,
        rationale="No identifiable theme or genre patterns; marked as eclectic."
    )


def detect_theme(title: str, genres: list[str], primary_genre: str, release_year: int, popularity: int, duration_ms: int) -> str:
    """Backward-compatible helper returning theme string."""
    return infer_theme(title, genres, primary_genre, release_year, popularity, duration_ms).value


def classify_popularity_tier(score: int) -> str:
    """Translates raw 0-100 score to human tier."""
    if score >= 75:
        return "Superstar Hit"
    elif score >= 50:
        return "Mainstream Popular"
    elif score >= 25:
        return "Moderate"
    else:
        return "Hidden Gem"


def classify_length_category(duration_ms: int) -> str:
    """Categorizes track length in human terms."""
    seconds = duration_ms // 1000
    if seconds < 150:
        return "Quick Track (<2:30)"
    elif seconds <= 300:
        return "Standard (2:30-5:00)"
    else:
        return "Extended / Epic (>5:00)"
