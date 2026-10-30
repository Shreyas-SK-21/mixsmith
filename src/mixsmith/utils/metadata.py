"""Human-centric music categorization and metadata inference."""

from __future__ import annotations

import re
from typing import List, Tuple


def classify_primary_genre(genres_list: List[str]) -> str:
    """Classifies a list of granular artist subgenres into a humanly understandable universal genre."""
    if not genres_list:
        return "Other / Unclassified"

    combined = " ".join(genres_list).lower()

    if any(k in combined for k in [
        "shoegaze", "dream pop", "nu gaze", "japanese shoegaze", "noise pop", "ethereal wave"
    ]):
        return "Shoegaze / Dream Pop"

    if any(k in combined for k in [
        "k-pop", "korean pop", "korean r&b", "korean indie", "k-rock", "k-rap"
    ]):
        return "K-Pop"

    if any(k in combined for k in [
        "j-pop", "japanese pop", "anime", "j-rock", "japanese alternative", "city pop"
    ]):
        return "J-Pop / Japanese"

    if any(k in combined for k in [
        "desi", "bollywood", "filmi", "hindi", "punjabi", "urdu", "indian indie", "tamil", "bhangra", "sufi"
    ]):
        return "Desi / South Asian"

    if any(k in combined for k in [
        "reggaeton", "latin", "urbano latino", "salsa", "bachata", "cumbia", "latin pop", "trap latino", "corrido", "mariachi"
    ]):
        return "Latin"

    if any(k in combined for k in [
        "metal", "death metal", "black metal", "thrash", "metalcore", "heavy metal", "deathcore", "nu metal"
    ]):
        return "Metal"

    if any(k in combined for k in [
        "hip hop", "rap", "trap", "drill", "boom bap", "conscious hip hop", "gangsta rap"
    ]):
        return "Hip-Hop / Rap"

    if any(k in combined for k in [
        "r&b", "soul", "contemporary r&b", "neo soul", "motown", "funk", "quiet storm"
    ]):
        return "R&B / Soul"

    if any(k in combined for k in [
        "edm", "house", "techno", "electronic", "synthwave", "dance", "trance", "drum and bass", "dubstep", "electro", "ambient"
    ]):
        return "Electronic / Dance"

    if any(k in combined for k in [
        "indie", "alternative", "indie rock", "indie pop", "post-punk", "grunge", "art rock", "new wave"
    ]):
        return "Indie / Alternative"

    if any(k in combined for k in [
        "rock", "classic rock", "hard rock", "punk", "psychedelic rock", "blues rock", "southern rock", "glam rock"
    ]):
        return "Rock"

    if any(k in combined for k in [
        "country", "bluegrass", "americana", "contemporary country", "alt-country", "honky tonk"
    ]):
        return "Country / Americana"

    if any(k in combined for k in [
        "folk", "acoustic", "singer-songwriter", "traditional folk", "celtic"
    ]):
        return "Folk & Acoustic"

    if any(k in combined for k in [
        "jazz", "blues", "bop", "swing", "vocal jazz", "cool jazz", "delta blues", "chicago blues"
    ]):
        return "Jazz & Blues"

    if any(k in combined for k in [
        "classical", "soundtrack", "orchestral", "film score", "baroque", "romantic", "opera", "cinematic"
    ]):
        return "Classical / Cinematic"

    if any(k in combined for k in [
        "pop", "dance pop", "electropop", "teen pop", "art pop", "synth-pop"
    ]):
        return "Pop"

    return "Pop / Miscellaneous"


def detect_era_and_decade(release_date: str) -> Tuple[str, str, int]:
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


def detect_language_and_region(isrc: str, genres: List[str], title: str, artists: List[str]) -> str:
    """Infers human language and regional music identity from ISRC, artist genres, and Unicode text."""
    # 1. Unicode Script Detection in Title or Artist
    text = f"{title} {' '.join(artists)}"
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", text):
        return "Japanese"
    if re.search(r"[\uAC00-\uD7AF]", text):
        return "Korean"
    if re.search(r"[\u0900-\u097F]", text):
        return "Hindi / Desi"
    if re.search(r"[\u0600-\u06FF]", text):
        return "Arabic / Persian"

    # 2. Genre Tags Check
    combined_genres = " ".join(genres).lower()
    if any(k in combined_genres for k in ["k-pop", "korean"]):
        return "Korean"
    if any(k in combined_genres for k in ["j-pop", "japanese", "anime", "j-rock", "city pop"]):
        return "Japanese"
    if any(k in combined_genres for k in ["desi", "bollywood", "filmi", "hindi", "punjabi", "urdu", "tamil", "telugu"]):
        return "Hindi / Desi"
    if any(k in combined_genres for k in ["latin", "reggaeton", "salsa", "bachata", "cumbia", "spanish", "urbano latino"]):
        return "Spanish / Latin"
    if any(k in combined_genres for k in ["french", "chanson", "variete francaise"]):
        return "French"
    if any(k in combined_genres for k in ["german", "deutsch"]):
        return "German"
    if any(k in combined_genres for k in ["brazilian", "bossa nova", "mpb", "sertanejo", "funk carioca"]):
        return "Portuguese (Brazil)"

    # 3. ISRC Country Code
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
            return isrc_map[cc]

    return "English"


def detect_theme(title: str, genres: List[str], primary_genre: str, release_year: int, popularity: int, duration_ms: int) -> str:
    """Classifies track into human themes and vibe contexts."""
    title_lower = title.lower()
    combined_genres = " ".join(genres).lower()

    if any(w in title_lower for w in ["night", "drive", "midnight", "dark", "moon", "after hours", "highway"]):
        return "Late Night Drive"

    if any(w in title_lower for w in ["gym", "run", "pump", "workout", "fitness", "beast", "energy"]) or \
       any(g in combined_genres for g in ["hardstyle", "metalcore", "workout", "trap"]):
        return "Workout / Gym"

    if any(w in title_lower for w in ["chill", "coffee", "morning", "relax", "rain", "breeze", "lo-fi", "sleep"]) or \
       any(g in combined_genres for g in ["lo-fi", "ambient", "chillout", "indie folk", "acoustic"]):
        return "Chill & Coffee Shop"

    if any(w in title_lower for w in ["party", "dance", "club", "celebrate", "shots", "disco", "rave"]) or \
       any(g in combined_genres for g in ["club", "edm", "house", "reggaeton"]):
        return "Party & Club"

    if any(w in title_lower for w in ["road", "trip", "travel", "summer", "sunshine", "freedom", "highway"]):
        return "Road Trip"

    if any(w in title_lower for w in ["study", "focus", "piano", "coding", "read", "work", "calm"]) or \
       primary_genre in ["Classical / Cinematic", "Jazz & Blues"]:
        return "Focus & Study"

    if any(w in title_lower for w in ["cry", "broken", "heartbreak", "sad", "tears", "alone", "miss you", "hurt"]):
        return "Heartbreak & Melancholy"

    if any(w in title_lower for w in ["love", "romance", "forever", "kiss", "sweetheart", "baby", "together"]):
        return "Love & Romance"

    # Default based on Primary Genre
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

    return genre_theme_map.get(primary_genre, "Eclectic & Diverse")


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
