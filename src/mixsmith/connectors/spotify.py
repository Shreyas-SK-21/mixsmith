#!/usr/bin/env python3
# /// script
# dependencies = ["requests", "openpyxl"]
# ///
"""
Spotify API Client & Human-Centric Playlist Processor
Enriches Spotify tracks with humanly understandable attributes:
- Artists & Co-artists
- Genres (Primary genre & full genre tags from artist profiles)
- Themes & Vibes (Late Night Drive, Workout / Gym, Chill & Coffee Shop, Party & Club, Road Trip, etc.)
- Eras & Decades (60s, 70s, 80s, 90s, 2000s, 2010s, 2020s, exact Release Year)
- Languages & Cultural Regions (English, Spanish/Latin, Korean, Japanese, Hindi/Desi, French, Portuguese, etc.)
- Popularity Tiers (Superstar Hit, Mainstream Popular, Moderate, Hidden Gem)
- Track Lengths (Quick Track, Standard, Extended / Epic)
- Content Advisory (Clean vs Explicit)

Provides smart sorting:
- Smart Artist Spacing (De-clumping: never hear the same artist back-to-back)
- Chronological Time Travel (Oldest to Newest) & Newest-First
- Genre Cluster Flow & Theme / Vibe Flow
- Decade Progression
- Album Track Order Flow
- Mainstream Hits vs Underground Hidden Gems
"""

import ast
import base64
import http.server
import json
import os
import re
import socketserver
import sys
import time
import urllib.parse
import webbrowser
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Fix Windows console UTF-8 encoding for emojis and international scripts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("Error: 'requests' is required. Run 'pip install requests' or use 'uv run'.", file=sys.stderr)
    sys.exit(1)

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Error: 'openpyxl' is required. Run 'pip install openpyxl' or use 'uv run'.", file=sys.stderr)
    sys.exit(1)


DEFAULT_CREDENTIALS_PATH = Path.home() / ".gemini" / "config" / "plugins" / "spotify" / "credentials.json"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read"
]


class SpotifyAuthHandler(http.server.SimpleHTTPRequestHandler):
    """Callback server for OAuth2 authorization code flow."""
    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                SpotifyAuthHandler.auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <html>
                <body style="font-family: system-ui, sans-serif; background: #121212; color: #fff; text-align: center; padding: 50px;">
                    <div style="background: #181818; max-width: 480px; margin: auto; padding: 30px; border-radius: 12px; border: 1px solid #1DB954;">
                        <h1 style="color: #1DB954;">Spotify Authorization Successful!</h1>
                        <p>You can close this tab and return to your terminal / agent.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            elif "error" in params:
                SpotifyAuthHandler.error = params["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"Authorization error: {SpotifyAuthHandler.error}".encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


class SpotifyClient:
    """Spotify API Client supporting Auth, Playlists, Tracks, Human Categorization, and Excel Export."""

    def __init__(self, credentials_path: Optional[Path] = None):
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.credentials: Dict[str, Any] = self._load_credentials()

    def _load_credentials(self) -> Dict[str, Any]:
        """Loads credentials from file or environment variables."""
        creds = {}
        if self.credentials_path.exists():
            try:
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    creds = json.load(f)
            except Exception as e:
                print(f"Warning: Could not read credentials file: {e}", file=sys.stderr)

        if os.environ.get("SPOTIFY_CLIENT_ID"):
            creds["client_id"] = os.environ["SPOTIFY_CLIENT_ID"]
        if os.environ.get("SPOTIFY_CLIENT_SECRET"):
            creds["client_secret"] = os.environ["SPOTIFY_CLIENT_SECRET"]
        if os.environ.get("SPOTIFY_ACCESS_TOKEN"):
            creds["access_token"] = os.environ["SPOTIFY_ACCESS_TOKEN"]
        if os.environ.get("SPOTIFY_REFRESH_TOKEN"):
            creds["refresh_token"] = os.environ["SPOTIFY_REFRESH_TOKEN"]

        if "redirect_uri" not in creds:
            creds["redirect_uri"] = DEFAULT_REDIRECT_URI

        return creds

    def save_credentials(self, updates: Dict[str, Any]) -> None:
        """Saves updated credentials to disk."""
        self.credentials.update(updates)
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.credentials_path, "w", encoding="utf-8") as f:
            json.dump(self.credentials, f, indent=2)

    def is_authenticated(self) -> bool:
        """Checks if a valid or refreshable token is available."""
        if self.credentials.get("access_token"):
            return True
        if self.credentials.get("refresh_token") and self.credentials.get("client_id") and self.credentials.get("client_secret"):
            return True
        return False

    def get_auth_url(self) -> str:
        """Generates the Spotify OAuth authorization URL."""
        client_id = self.credentials.get("client_id")
        if not client_id:
            raise ValueError("Spotify client_id is missing. Please run setup first.")
        redirect_uri = self.credentials.get("redirect_uri", DEFAULT_REDIRECT_URI)
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(DEFAULT_SCOPES),
            "show_dialog": "true"
        }
        return f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchanges an authorization code for access and refresh tokens."""
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        redirect_uri = self.credentials.get("redirect_uri", DEFAULT_REDIRECT_URI)

        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required to exchange token.")

        auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        }

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to exchange code: HTTP {resp.status_code} - {resp.text}")

        token_data = resp.json()
        expires_in = token_data.get("expires_in", 3600)
        updates = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token", self.credentials.get("refresh_token")),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": time.time() + expires_in
        }
        self.save_credentials(updates)
        return updates

    def refresh_access_token(self) -> bool:
        """Refreshes the access token using the stored refresh token."""
        refresh_token = self.credentials.get("refresh_token")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")

        if not refresh_token or not client_id or not client_secret:
            return False

        auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        if resp.status_code == 200:
            token_data = resp.json()
            expires_in = token_data.get("expires_in", 3600)
            updates = {
                "access_token": token_data.get("access_token"),
                "expires_at": time.time() + expires_in
            }
            if "refresh_token" in token_data:
                updates["refresh_token"] = token_data["refresh_token"]
            self.save_credentials(updates)
            return True
        else:
            print(f"Warning: Failed to refresh token (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
            return False

    def authorize_interactive(self, port: int = 8888, timeout: int = 120) -> bool:
        """Starts a local HTTP server and opens the browser for authorization."""
        auth_url = self.get_auth_url()
        print(f"\nOpening browser for Spotify Authorization:\n{auth_url}\n")

        SpotifyAuthHandler.auth_code = None
        SpotifyAuthHandler.error = None

        try:
            with socketserver.TCPServer(("127.0.0.1", port), SpotifyAuthHandler) as httpd:
                httpd.timeout = 2.0
                webbrowser.open(auth_url)
                start_time = time.time()
                print("Waiting for Spotify authorization callback...")
                while time.time() - start_time < timeout:
                    httpd.handle_request()
                    if SpotifyAuthHandler.auth_code:
                        print("Authorization code received! Exchanging for tokens...")
                        self.exchange_code_for_token(SpotifyAuthHandler.auth_code)
                        print("Authentication successful!")
                        return True
                    if SpotifyAuthHandler.error:
                        print(f"Authorization failed: {SpotifyAuthHandler.error}", file=sys.stderr)
                        return False
                print("Timed out waiting for Spotify authorization.", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Error running local auth server: {e}", file=sys.stderr)
            print("Fallback: Please visit the authorization URL manually and paste the code:")
            code = input("Authorization Code: ").strip()
            if code:
                self.exchange_code_for_token(code)
                return True
            return False

    def _get_valid_token(self) -> str:
        """Returns a valid access token, refreshing if necessary."""
        expires_at = self.credentials.get("expires_at", 0)
        if expires_at and time.time() > (expires_at - 60):
            if not self.refresh_access_token():
                raise RuntimeError("Access token expired and failed to refresh. Please re-authenticate.")
        
        token = self.credentials.get("access_token")
        if not token:
            raise RuntimeError("No Spotify access token available. Run 'spotify_cli.py auth setup' first.")
        return token

    def api_request(self, method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None, max_retries: int = 3) -> Any:
        """Makes an authenticated request to the Spotify Web API with rate limit handling."""
        url = endpoint if endpoint.startswith("http") else f"{SPOTIFY_API_BASE}/{endpoint.lstrip('/')}"
        
        for attempt in range(max_retries):
            token = self._get_valid_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            resp = requests.request(method, url, headers=headers, params=params, json=json_data)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                print(f"Rate limited by Spotify API. Waiting {retry_after}s before retry...", file=sys.stderr)
                time.sleep(retry_after)
                continue

            if resp.status_code == 401:
                print("Token expired. Attempting token refresh...", file=sys.stderr)
                if self.refresh_access_token():
                    continue
                else:
                    raise RuntimeError("Spotify authentication failed (HTTP 401). Please re-authenticate.")

            if resp.status_code >= 400:
                raise RuntimeError(f"Spotify API Error HTTP {resp.status_code} ({url}): {resp.text}")

            if resp.status_code == 204 or not resp.text:
                return {}

            return resp.json()

        raise RuntimeError(f"Request failed after {max_retries} retries: {url}")

    def get_me(self) -> Dict[str, Any]:
        """Gets the current authenticated user's profile."""
        return self.api_request("GET", "me")

    def list_user_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves all playlists for the current user."""
        playlists = []
        url = f"me/playlists?limit={limit}"
        while url:
            data = self.api_request("GET", url)
            items = data.get("items", [])
            for item in items:
                if not item:
                    continue
                tracks_cnt = (
                    item.get("tracks", {}).get("total")
                    if isinstance(item.get("tracks"), dict)
                    else (item.get("items", {}).get("total") if isinstance(item.get("items"), dict) else 0)
                ) or item.get("items", {}).get("total", 0)
                playlists.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description") or "",
                    "tracks_count": tracks_cnt,
                    "public": item.get("public", False),
                    "collaborative": item.get("collaborative", False),
                    "owner": item.get("owner", {}).get("display_name") or item.get("owner", {}).get("id"),
                    "url": item.get("external_urls", {}).get("spotify"),
                    "uri": item.get("uri"),
                    "snapshot_id": item.get("snapshot_id")
                })
            url = data.get("next")
        return playlists

    @staticmethod
    def extract_playlist_id(playlist_identifier: str) -> str:
        """Extracts playlist ID from a URL, URI, or ID string."""
        identifier = playlist_identifier.strip()
        url_match = re.search(r"playlist[/:]([a-zA-Z0-9]{22})", identifier)
        if url_match:
            return url_match.group(1)
        if re.match(r"^[a-zA-Z0-9]{22}$", identifier):
            return identifier
        return identifier

    def get_artists_data(self, artist_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch fetches artist metadata (genres, popularity) in chunks of up to 50."""
        artists_map: Dict[str, Dict[str, Any]] = {}
        unique_ids = [aid for aid in dict.fromkeys(artist_ids) if aid]

        chunk_size = 50
        for i in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[i:i + chunk_size]
            try:
                res = self.api_request("GET", f"artists?ids={','.join(chunk)}")
                for art in res.get("artists", []):
                    if not art or not art.get("id"):
                        continue
                    artists_map[art["id"]] = {
                        "name": art.get("name"),
                        "genres": art.get("genres", []),
                        "popularity": art.get("popularity", 0)
                    }
            except Exception as e:
                print(f"Warning: Failed to fetch artists batch ({e}). Continuing...", file=sys.stderr)

        return artists_map

    @staticmethod
    def classify_primary_genre(genres_list: List[str]) -> str:
        """Classifies a list of specific subgenres into a clean, universally understood primary genre."""
        if not genres_list:
            return "Pop & Contemporary"

        g_str = " " + " ".join(genres_list).lower() + " "

        if any(k in g_str for k in ["k-pop", "korean pop", "k-rap", "k-rock"]):
            return "K-Pop"
        if any(k in g_str for k in ["bollywood", "desi", "punjabi", "filmi", "hindi", "tamil", "telugu"]):
            return "Desi / South Asian"
        if any(k in g_str for k in ["reggaeton", "latin", "urbano latino", "bachata", "cumbia", "salsa", "musica mexicana", "corridos"]):
            return "Latin"
        if any(k in g_str for k in ["afrobeats", "amapiano", "afro pop"]):
            return "Afrobeats"
        if any(k in g_str for k in ["metal", "metalcore", "death metal", "heavy metal", "thrash"]):
            return "Metal"
        if any(k in g_str for k in ["shoegaze", "dream pop", "japanese shoegaze"]):
            return "Shoegaze / Dream Pop"
        if any(k in g_str for k in ["hip hop", "rap", "trap", "drill", "boom bap", "gangster rap"]):
            return "Hip-Hop / Rap"
        if any(k in g_str for k in ["r&b", "soul", "neo soul", "motown", "contemporary r&b"]):
            return "R&B / Soul"
        if any(k in g_str for k in ["indie", "alternative", "bedroom pop", "shoegaze", "indie pop", "indie rock"]):
            return "Indie / Alternative"
        if any(k in g_str for k in ["house", "edm", "techno", "electronic", "electro", "trance", "dubstep", "synthwave", "drum and bass"]):
            return "Electronic / Dance"
        if any(k in g_str for k in ["classic rock", "hard rock", "punk", "grunge", "rock", "garage rock"]):
            return "Rock"
        if any(k in g_str for k in ["country", "bluegrass", "americana"]):
            return "Country / Americana"
        if any(k in g_str for k in ["classical", "soundtrack", "score", "orchestral", "cinematic", "ambient"]):
            return "Classical / Cinematic"
        if any(k in g_str for k in ["jazz", "blues", "smooth jazz", "bossa nova"]):
            return "Jazz & Blues"
        if any(k in g_str for k in ["folk", "acoustic", "singer-songwriter"]):
            return "Folk & Acoustic"
        if any(k in g_str for k in ["reggae", "dancehall", "dub"]):
            return "Reggae"
        if any(k in g_str for k in ["pop"]):
            return "Pop"

        return "Alternative / Other"

    @staticmethod
    def detect_era_and_decade(release_date: str) -> Tuple[Optional[int], str, str]:
        """Extracts release year, decade (e.g. 90s), and human era description."""
        if not release_date:
            return None, "Unknown", "Unknown Era"

        year_match = re.match(r"^(\d{4})", release_date)
        if not year_match:
            return None, "Unknown", "Unknown Era"

        year = int(year_match.group(1))

        if year >= 2020:
            decade = "2020s"
            era = "Modern 2020s"
        elif 2010 <= year <= 2019:
            decade = "2010s"
            era = "2010s Streaming Era"
        elif 2000 <= year <= 2009:
            decade = "2000s"
            era = "2000s Y2K Era"
        elif 1990 <= year <= 1999:
            decade = "90s"
            era = "90s Nostalgia"
        elif 1980 <= year <= 1989:
            decade = "80s"
            era = "Retro 80s"
        elif 1970 <= year <= 1979:
            decade = "70s"
            era = "Classic 70s"
        elif 1960 <= year <= 1969:
            decade = "60s"
            era = "Golden 60s"
        else:
            decade = "Vintage"
            era = "Vintage Golden Oldies"

        return year, decade, era

    @staticmethod
    def detect_language_and_region(isrc: str, genres: List[str], title: str, artists: str) -> str:
        """Detects the human language / cultural region of a track."""
        full_text = f"{title} {artists}"

        # 1. Native Script Detection
        if re.search(r"[\uac00-\ud7af\u1100-\u11ff]", full_text):
            return "Korean"
        if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", full_text):
            return "Japanese"
        if re.search(r"[\u0900-\u097f]", full_text):
            return "Hindi / Desi"
        if re.search(r"[\u0a00-\u0a7f]", full_text):
            return "Punjabi"
        if re.search(r"[\u0600-\u06ff]", full_text):
            return "Arabic"
        if re.search(r"[\u0400-\u04ff]", full_text):
            return "Russian / Slavic"
        if re.search(r"[\u4e00-\u9fff]", full_text):
            return "Chinese"

        # 2. Genre Indicators
        g_str = " ".join(genres).lower()
        if any(k in g_str for k in ["k-pop", "korean"]):
            return "Korean"
        if any(k in g_str for k in ["j-pop", "anime", "japanese", "visual kei"]):
            return "Japanese"
        if any(k in g_str for k in ["bollywood", "desi", "punjabi", "filmi", "hindi", "indian"]):
            return "Hindi / Desi"
        if any(k in g_str for k in ["reggaeton", "latin", "urbano latino", "musica mexicana", "bachata", "cumbia", "salsa", "flamenco", "corridos"]):
            return "Spanish / Latin"
        if any(k in g_str for k in ["french", "rap francais", "chanson"]):
            return "French"
        if any(k in g_str for k in ["brazilian", "mpb", "bossa nova", "funk carioca", "sertanejo", "portuguese"]):
            return "Portuguese / Brazilian"
        if any(k in g_str for k in ["deutschrap", "german"]):
            return "German"
        if any(k in g_str for k in ["italian", "trap italiano"]):
            return "Italian"
        if any(k in g_str for k in ["afrobeats", "amapiano", "nigerian"]):
            return "Afrobeats / African"

        # 3. ISRC Country Code Prefix
        if isrc and len(isrc) >= 2:
            cc = isrc[:2].upper()
            cc_map = {
                "KR": "Korean",
                "JP": "Japanese",
                "IN": "Hindi / Desi",
                "PK": "Punjabi / Urdu",
                "ES": "Spanish / Latin", "MX": "Spanish / Latin", "CO": "Spanish / Latin",
                "AR": "Spanish / Latin", "PR": "Spanish / Latin", "CL": "Spanish / Latin",
                "FR": "French",
                "BR": "Portuguese / Brazilian", "PT": "Portuguese / Brazilian",
                "DE": "German", "AT": "German",
                "IT": "Italian",
                "NG": "Afrobeats / African", "ZA": "Afrobeats / African",
                "US": "English (US)", "GB": "English (UK)", "CA": "English (CA)", "AU": "English (AU)"
            }
            if cc in cc_map:
                return cc_map[cc]

        return "English / International"

    @staticmethod
    def detect_theme(title: str, genres: List[str], primary_genre: str, release_year: Optional[int], popularity: int, duration_ms: int) -> str:
        """Infers a humanly understandable theme / vibe for the song."""
        t_lower = title.lower()
        g_str = " ".join(genres).lower()

        # 1. Workout / High Energy Gym
        if any(k in t_lower for k in ["workout", "pump", "power", "strong", "lift", "run", "push", "beast", "harder", "faster", "gym", "train", "unstoppable"]) or \
           (primary_genre in ["Metal", "Hip-Hop / Rap", "Electronic / Dance"] and any(k in g_str for k in ["trap", "hard rock", "gym", "bass", "dubstep", "drill"])):
            return "Workout / Gym"

        # 2. Late Night Drive
        if any(k in t_lower for k in ["midnight", "night", "drive", "moon", "dark", "city", "ride", "late", "after hours", "lights", "neon", "shadow"]) or \
           any(k in g_str for k in ["synthwave", "vaporwave", "dark r&b", "chillwave", "atmospheric"]):
            return "Late Night Drive"

        # 3. Party & Club
        if any(k in t_lower for k in ["party", "club", "dance", "drink", "shots", "celebrate", "weekend", "friday", "saturday", "rave", "dj"]) or \
           any(k in g_str for k in ["club", "dance pop", "house", "edm", "reggaeton", "disco"]):
            return "Party & Club"

        # 4. Chill & Coffee Shop
        if any(k in t_lower for k in ["coffee", "morning", "sun", "tea", "calm", "peace", "rain", "soft", "breeze", "slow", "sunday", "acoustic", "gentle"]) or \
           any(k in g_str for k in ["lo-fi", "indie folk", "bedroom pop", "acoustic", "smooth jazz", "chillhop"]):
            return "Chill & Coffee Shop"

        # 5. Focus & Study
        if any(k in g_str for k in ["soundtrack", "ambient", "classical", "score", "piano", "instrumental", "lo-fi beats"]) or \
           any(k in t_lower for k in ["study", "focus", "meditation", "ambient", "sleep"]):
            return "Focus & Study"

        # 6. Road Trip & Anthems
        if any(k in t_lower for k in ["road", "highway", "miles", "journey", "home", "summer", "california", "runaway", "drive", "travel"]) or \
           any(k in g_str for k in ["classic rock", "americana", "yacht rock", "anthem"]):
            return "Road Trip"

        # 7. Heartbreak & Melancholy
        if any(k in t_lower for k in ["cry", "tears", "broken", "hurt", "lonely", "miss you", "leave", "goodbye", "heartbreak", "sad", "sorry", "pain", "bleed", "alone"]):
            return "Heartbreak & Melancholy"

        # 8. Love & Romance
        if any(k in t_lower for k in ["love", "baby", "forever", "kiss", "sweet", "darling", "honey", "romantic", "you and me", "marry", "angel"]) or \
           any(k in g_str for k in ["neo-soul", "love song"]):
            return "Love & Romance"

        # 9. Throwback Classics
        if release_year and release_year < 2010:
            return "Throwback Classics"

        genre_vibes = {
            "Shoegaze / Dream Pop": "Dreamy & Ethereal",
            "Hip-Hop / Rap": "Hip-Hop Beats",
            "Rock": "Rock Anthem",
            "Electronic / Dance": "Electronic Groove",
            "Pop": "Upbeat Pop",
            "R&B / Soul": "Smooth R&B",
            "Indie / Alternative": "Indie Atmosphere",
            "Latin": "Latin Groove",
            "K-Pop": "K-Pop Energy",
            "Desi / South Asian": "Desi Rhythm"
        }
        return genre_vibes.get(primary_genre, "Feel-Good Music")

    @staticmethod
    def classify_popularity_tier(pop: int) -> str:
        """Translates Spotify 0-100 score into human discovery tiers."""
        if pop >= 75:
            return "Superstar Hit"
        elif pop >= 55:
            return "Mainstream Popular"
        elif pop >= 35:
            return "Moderate / Familiar"
        else:
            return "Hidden Gem / Deep Cut"

    @staticmethod
    def classify_length_category(duration_ms: int) -> str:
        """Classifies duration into human track length categories."""
        mins = duration_ms / 60000.0
        if mins < 2.75:
            return "Quick Track (<2.5m)"
        elif mins <= 4.25:
            return "Standard (3-4m)"
        else:
            return "Extended / Epic (>4m)"

    def get_playlist(self, playlist_identifier: str) -> Dict[str, Any]:
        """Fetches playlist metadata and all tracks (supports standard playlists and 'liked' songs), handling pagination."""
        is_liked = playlist_identifier.strip().lower() in ("liked", "liked-songs", "saved", "me/tracks", "liked songs")
        
        raw_tracks: List[Dict[str, Any]] = []

        def parse_items(raw_items):
            for item in raw_items:
                if not item or not item.get("track"):
                    continue
                tr = item["track"]
                if not tr.get("id"):
                    continue
                raw_tracks.append((item, tr))

        if is_liked:
            print("Fetching Liked Songs library from Spotify (me/tracks)...")
            metadata = {
                "id": "liked-songs",
                "name": "Liked Songs",
                "description": "User's saved/liked tracks library",
                "owner": {"display_name": "Me"},
                "external_urls": {"spotify": "https://open.spotify.com/collection/tracks"}
            }
            first_page = self.api_request("GET", "me/tracks?limit=50")
            total_expected = first_page.get("total", 0)
            url = first_page.get("next")
            items = first_page.get("items", [])
            parse_items(items)
            print(f"Retrieved {len(raw_tracks)} of {total_expected} liked songs...")
            
            while url:
                data = self.api_request("GET", url)
                parse_items(data.get("items", []))
                if len(raw_tracks) % 250 == 0 or not data.get("next"):
                    print(f"Retrieved {len(raw_tracks)} of {total_expected} liked songs...")
                url = data.get("next")
        else:
            playlist_id = self.extract_playlist_id(playlist_identifier)
            metadata = self.api_request("GET", f"playlists/{playlist_id}")
            tracks_data = metadata.get("tracks") if isinstance(metadata.get("tracks"), dict) else (metadata.get("items") if isinstance(metadata.get("items"), dict) else {})
            total_expected = tracks_data.get("total", 0)
            url = tracks_data.get("next")
            items = tracks_data.get("items", [])
            parse_items(items)

            while url:
                data = self.api_request("GET", url)
                parse_items(data.get("items", []))
                if len(raw_tracks) % 250 == 0 or not data.get("next"):
                    print(f"Retrieved {len(raw_tracks)} of {total_expected} songs...")
                url = data.get("next")

        all_artist_ids: Set[str] = set()
        for _, tr in raw_tracks:
            for art in tr.get("artists", []):
                if art.get("id"):
                    all_artist_ids.add(art["id"])

        print(f"Gathering artist genres for {len(all_artist_ids)} artists in playlist...")
        artists_data = self.get_artists_data(list(all_artist_ids))

        enriched_tracks: List[Dict[str, Any]] = []
        for item, tr in raw_tracks:
            artist_list = [a.get("name", "") for a in tr.get("artists", []) if a.get("name")]
            primary_artist = artist_list[0] if artist_list else "Unknown"
            artist_names = ", ".join(artist_list)
            
            track_genres: List[str] = []
            for art in tr.get("artists", []):
                aid = art.get("id")
                if aid and aid in artists_data:
                    track_genres.extend(artists_data[aid].get("genres", []))
            track_genres = list(dict.fromkeys(track_genres))

            album = tr.get("album", {})
            album_type = album.get("album_type", "album").capitalize()
            release_date = album.get("release_date", "")
            duration_ms = tr.get("duration_ms", 0)
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) // 1000
            duration_fmt = f"{minutes}:{seconds:02d}"

            isrc = tr.get("external_ids", {}).get("isrc", "")
            pop = tr.get("popularity", 0)
            title = tr.get("name", "")
            added_by = item.get("added_by", {}).get("id", "")
            added_at = item.get("added_at", "")
            track_num = tr.get("track_number", 1)
            disc_num = tr.get("disc_number", 1)

            primary_genre = self.classify_primary_genre(track_genres)
            year, decade, era = self.detect_era_and_decade(release_date)
            language = self.detect_language_and_region(isrc, track_genres, title, artist_names)
            theme = self.detect_theme(title, track_genres, primary_genre, year, pop, duration_ms)
            pop_tier = self.classify_popularity_tier(pop)
            len_cat = self.classify_length_category(duration_ms)
            explicit_rating = "Explicit" if tr.get("explicit") else "Clean"

            enriched_tracks.append({
                "id": tr.get("id"),
                "name": title,
                "primary_artist": primary_artist,
                "artists": artist_names,
                "artist_list": artist_list,
                "album": album.get("name", ""),
                "album_type": album_type,
                "track_number": track_num,
                "disc_number": disc_num,
                "primary_genre": primary_genre,
                "genres": track_genres,
                "genres_str": ", ".join(track_genres[:4]) if track_genres else "Pop / Contemporary",
                "theme": theme,
                "decade": decade,
                "era": era,
                "release_year": year,
                "release_date": release_date,
                "language": language,
                "popularity": pop,
                "popularity_tier": pop_tier,
                "duration_ms": duration_ms,
                "duration_formatted": duration_fmt,
                "length_category": len_cat,
                "explicit": explicit_rating,
                "is_clean": explicit_rating == "Clean",
                "is_explicit": explicit_rating == "Explicit",
                "url": tr.get("external_urls", {}).get("spotify", f"https://open.spotify.com/track/{tr.get('id')}"),
                "uri": tr.get("uri"),
                "isrc": isrc,
                "added_at": added_at,
                "added_by": added_by
            })

        return {
            "id": metadata.get("id"),
            "name": metadata.get("name"),
            "description": metadata.get("description") or "",
            "owner": metadata.get("owner", {}).get("display_name") or metadata.get("owner", {}).get("id"),
            "total_tracks": len(enriched_tracks),
            "url": metadata.get("external_urls", {}).get("spotify"),
            "tracks": enriched_tracks
        }

    @staticmethod
    def export_to_excel(playlist_data: Dict[str, Any], output_path: Union[str, Path]) -> str:
        """Exports human-centric track metadata and overview insights to a styled Excel workbook."""
        wb = openpyxl.Workbook()
        ws_tracks = wb.active
        ws_tracks.title = "Tracks"

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
            ("Track Name", 30),
            ("Artist(s)", 26),
            ("Album", 26),
            ("Album Type", 14),
            ("Primary Genre", 18),
            ("Theme / Vibe", 22),
            ("Era / Decade", 15),
            ("Release Year", 14),
            ("Language / Region", 20),
            ("Popularity Tier", 18),
            ("Duration", 10),
            ("Length Category", 18),
            ("Rating", 11),
            ("All Genres", 30),
            ("ISRC", 16),
            ("Added By", 16),
            ("Added At", 20),
            ("Spotify URL", 35),
            ("Spotify URI", 36),
            ("Track ID", 25)
        ]

        ws_tracks.row_dimensions[1].height = 28
        for col_idx, (header_text, width) in enumerate(headers, 1):
            cell = ws_tracks.cell(row=1, column=col_idx, value=header_text)
            cell.fill = green_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border
            ws_tracks.column_dimensions[get_column_letter(col_idx)].width = width

        tracks = playlist_data.get("tracks", [])
        for row_idx, track in enumerate(tracks, start=2):
            ws_tracks.row_dimensions[row_idx].height = 20
            row_fill = zebra_fill if row_idx % 2 == 0 else PatternFill(fill_type=None)

            values = [
                row_idx - 1,
                track.get("name"),
                track.get("artists"),
                track.get("album"),
                track.get("album_type"),
                track.get("primary_genre"),
                track.get("theme"),
                track.get("decade"),
                track.get("release_year"),
                track.get("language"),
                track.get("popularity_tier"),
                track.get("duration_formatted"),
                track.get("length_category"),
                track.get("explicit"),
                track.get("genres_str"),
                track.get("isrc"),
                track.get("added_by"),
                track.get("added_at"),
                track.get("url"),
                track.get("uri"),
                track.get("id")
            ]

            for col_idx, val in enumerate(values, start=1):
                cell = ws_tracks.cell(row=row_idx, column=col_idx, value=val)
                cell.font = regular_font
                cell.border = thin_border
                if row_fill.fill_type:
                    cell.fill = row_fill

                if col_idx == 1:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 19 and val:
                    cell.font = link_font

        ws_tracks.freeze_panes = "A2"
        ws_tracks.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(tracks) + 1}"

        ws_sum = wb.create_sheet(title="Playlist Overview")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum["A1"] = playlist_data.get("name", "Spotify Playlist")
        ws_sum["A1"].font = title_font
        ws_sum["A2"] = playlist_data.get("description", "")
        ws_sum["A2"].font = subtitle_font
        ws_sum["A3"] = f"Curated by: {playlist_data.get('owner', 'Unknown')} | Total Songs: {len(tracks)}"
        ws_sum["A3"].font = regular_font

        durations = [t["duration_ms"] for t in tracks if t.get("duration_ms")]
        total_ms = sum(durations)
        total_hours = total_ms / (1000 * 60 * 60)
        total_mins = (total_ms % (1000 * 60 * 60)) / (1000 * 60)

        overview_stats = [
            ("Metric", "Value"),
            ("Total Songs", len(tracks)),
            ("Total Playtime", f"{int(total_hours)}h {int(total_mins)}m ({round(total_ms / 60000, 1)} minutes)"),
            ("Clean Songs", sum(1 for t in tracks if t.get("is_clean"))),
            ("Explicit Songs", sum(1 for t in tracks if t.get("is_explicit"))),
        ]

        ws_sum.cell(row=5, column=1, value="Overview").font = bold_font
        for s_idx, (m, v) in enumerate(overview_stats, start=6):
            c1 = ws_sum.cell(row=s_idx, column=1, value=m)
            c2 = ws_sum.cell(row=s_idx, column=2, value=v)
            if s_idx == 6:
                c1.fill = green_fill; c2.fill = green_fill
                c1.font = header_font; c2.font = header_font
            else:
                c1.font = bold_font; c2.font = regular_font
            c1.border = thin_border; c2.border = thin_border

        def build_breakdown(title_text, row_start, col_start, counts_dict, col_label):
            ws_sum.cell(row=row_start, column=col_start, value=title_text).font = bold_font
            c_hdr1 = ws_sum.cell(row=row_start + 1, column=col_start, value=col_label)
            c_hdr2 = ws_sum.cell(row=row_start + 1, column=col_start + 1, value="Songs")
            c_hdr3 = ws_sum.cell(row=row_start + 1, column=col_start + 2, value="Share")
            for c in (c_hdr1, c_hdr2, c_hdr3):
                c.fill = dark_fill
                c.font = header_font
                c.border = thin_border

            sorted_items = sorted(counts_dict.items(), key=lambda x: x[1], reverse=True)
            for idx, (item, count) in enumerate(sorted_items, start=row_start + 2):
                c1 = ws_sum.cell(row=idx, column=col_start, value=item)
                c2 = ws_sum.cell(row=idx, column=col_start + 1, value=count)
                share = (count / len(tracks)) if tracks else 0
                c3 = ws_sum.cell(row=idx, column=col_start + 2, value=share)
                c3.number_format = "0.0%"
                for c in (c1, c2, c3):
                    c.font = regular_font
                    c.border = thin_border
                c2.alignment = Alignment(horizontal="center")
                c3.alignment = Alignment(horizontal="right")
            return row_start + len(sorted_items) + 3

        genre_counts = defaultdict(int)
        theme_counts = defaultdict(int)
        decade_counts = defaultdict(int)
        lang_counts = defaultdict(int)
        artist_counts = defaultdict(int)

        for t in tracks:
            genre_counts[t.get("primary_genre") or "Other"] += 1
            theme_counts[t.get("theme") or "Other"] += 1
            decade_counts[t.get("decade") or "Other"] += 1
            lang_counts[t.get("language") or "Other"] += 1
            for a in t.get("artist_list", []):
                artist_counts[a] += 1

        r1 = build_breakdown("Top Genres", 12, 1, genre_counts, "Genre")
        r2 = build_breakdown("Themes & Vibes", r1, 1, theme_counts, "Theme / Vibe")
        r3 = build_breakdown("Eras & Decades", 12, 5, decade_counts, "Decade")
        r4 = build_breakdown("Languages & Regions", r3, 5, lang_counts, "Language / Region")
        top_10_artists = dict(sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        build_breakdown("Top Artists", max(r2, r4), 1, top_10_artists, "Artist")

        ws_sum.column_dimensions["A"].width = 28
        ws_sum.column_dimensions["B"].width = 16
        ws_sum.column_dimensions["C"].width = 14
        ws_sum.column_dimensions["D"].width = 6
        ws_sum.column_dimensions["E"].width = 26
        ws_sum.column_dimensions["F"].width = 16
        ws_sum.column_dimensions["G"].width = 14

        output_file = Path(output_path).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_file)
        return str(output_file)

    @staticmethod
    def export_to_csv(playlist_data: Dict[str, Any], output_path: Union[str, Path]) -> str:
        """Exports enriched playlist tracks to standard CSV format (compatible with Exportify)."""
        import csv
        output_file = Path(output_path).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)

        fields = [
            "Track URI",
            "Track Name",
            "Artist Name(s)",
            "Album Name",
            "Album Type",
            "Primary Genre",
            "All Genres",
            "Theme / Vibe",
            "Era / Decade",
            "Release Year",
            "Release Date",
            "Language / Region",
            "Popularity Tier",
            "Popularity Score",
            "Duration",
            "Duration (ms)",
            "Length Category",
            "Explicit",
            "Added At",
            "Added By",
            "ISRC",
            "Track Number",
            "Disc Number",
            "Spotify URL",
            "Track ID"
        ]

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            for t in playlist_data.get("tracks", []):
                writer.writerow([
                    t.get("uri"),
                    t.get("name"),
                    t.get("artists"),
                    t.get("album"),
                    t.get("album_type"),
                    t.get("primary_genre"),
                    t.get("genres_str"),
                    t.get("theme"),
                    t.get("decade"),
                    t.get("release_year"),
                    t.get("release_date"),
                    t.get("language"),
                    t.get("popularity_tier"),
                    t.get("popularity"),
                    t.get("duration_formatted"),
                    t.get("duration_ms"),
                    t.get("length_category"),
                    t.get("explicit"),
                    t.get("added_at"),
                    t.get("added_by"),
                    t.get("isrc"),
                    t.get("track_number"),
                    t.get("disc_number"),
                    t.get("url"),
                    t.get("id")
                ])
        return str(output_file)

    @staticmethod
    def evaluate_filter(track: Dict[str, Any], filter_expr: str) -> bool:
        """Evaluates humanly understandable criteria against a track."""
        expr = filter_expr.strip()
        if not expr:
            return True

        var_map = {
            "artist": (track.get("artists") or "").lower(),
            "artists": (track.get("artists") or "").lower(),
            "primary_artist": (track.get("primary_artist") or "").lower(),
            "genre": (track.get("primary_genre") or "").lower(),
            "primary_genre": (track.get("primary_genre") or "").lower(),
            "genres": " ".join(track.get("genres", [])).lower(),
            "theme": (track.get("theme") or "").lower(),
            "vibe": (track.get("theme") or "").lower(),
            "language": (track.get("language") or "").lower(),
            "decade": (track.get("decade") or "").lower(),
            "year": track.get("release_year") or 0,
            "release_year": track.get("release_year") or 0,
            "popularity": track.get("popularity") or 0,
            "popularity_tier": (track.get("popularity_tier") or "").lower(),
            "tier": (track.get("popularity_tier") or "").lower(),
            "length": (track.get("length_category") or "").lower(),
            "explicit": track.get("is_explicit", False),
            "clean": track.get("is_clean", True),
            "title": (track.get("name") or "").lower(),
            "name": (track.get("name") or "").lower(),
            "album": (track.get("album") or "").lower()
        }

        preset_map = {
            "workout": "theme == 'workout / gym' or 'workout' in theme or 'trap' in genres",
            "gym": "theme == 'workout / gym' or 'workout' in theme",
            "chill": "theme == 'chill & coffee shop' or 'chill' in theme",
            "coffee": "theme == 'chill & coffee shop'",
            "party": "theme == 'party & club' or 'party' in theme",
            "club": "theme == 'party & club'",
            "focus": "theme == 'focus & study' or 'study' in theme",
            "study": "theme == 'focus & study'",
            "late-night": "theme == 'late night drive' or 'late' in theme",
            "road-trip": "theme == 'road trip' or 'road' in theme",
            "romance": "theme == 'love & romance' or 'love' in theme",
            "heartbreak": "theme == 'heartbreak & melancholy'",
            "nostalgia": "decade in ['60s', '70s', '80s', '90s', '2000s']",
            "throwback": "decade in ['60s', '70s', '80s', '90s', '2000s']",
            "hits": "popularity >= 70 or 'hit' in tier",
            "gems": "popularity <= 40 or 'gem' in tier",
            "underground": "popularity <= 40 or 'gem' in tier",
            "clean": "clean == True",
            "explicit": "explicit == True"
        }
        if expr.lower() in preset_map:
            expr = preset_map[expr.lower()]

        try:
            parsed = ast.parse(expr, mode="eval")

            def eval_node(node):
                if isinstance(node, ast.Expression):
                    return eval_node(node.body)
                elif isinstance(node, ast.BoolOp):
                    if isinstance(node.op, ast.And):
                        return all(eval_node(v) for v in node.values)
                    elif isinstance(node.op, ast.Or):
                        return any(eval_node(v) for v in node.values)
                elif isinstance(node, ast.UnaryOp):
                    if isinstance(node.op, ast.Not):
                        return not eval_node(node.operand)
                elif isinstance(node, ast.Compare):
                    left = eval_node(node.left)
                    for op, comparator in zip(node.ops, node.comparators):
                        right = eval_node(comparator)
                        if isinstance(op, ast.Eq) and not (left == right):
                            return False
                        elif isinstance(op, ast.NotEq) and not (left != right):
                            return False
                        elif isinstance(op, ast.Lt) and not (left < right):
                            return False
                        elif isinstance(op, ast.LtE) and not (left <= right):
                            return False
                        elif isinstance(op, ast.Gt) and not (left > right):
                            return False
                        elif isinstance(op, ast.GtE) and not (left >= right):
                            return False
                        elif isinstance(op, ast.In) and not (left in right):
                            return False
                        elif isinstance(op, ast.NotIn) and not (left not in right):
                            return False
                    return True
                elif isinstance(node, ast.Name):
                    name_key = node.id.lower()
                    if name_key in var_map:
                        return var_map[name_key]
                    raise ValueError(f"Unknown variable: {node.id}")
                elif isinstance(node, ast.Constant):
                    if isinstance(node.value, str):
                        return node.value.lower()
                    return node.value
                elif isinstance(node, ast.List):
                    return [eval_node(elt) for elt in node.elts]
                elif isinstance(node, ast.BinOp):
                    l = eval_node(node.left)
                    r = eval_node(node.right)
                    if isinstance(node.op, ast.Add): return l + r
                    elif isinstance(node.op, ast.Sub): return l - r
                    elif isinstance(node.op, ast.Mult): return l * r
                    elif isinstance(node.op, ast.Div): return l / r
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "contains":
                        target = eval_node(node.func.value)
                        arg = eval_node(node.args[0])
                        return str(arg) in str(target)

                raise ValueError(f"Unsupported node: {ast.dump(node)}")

            return bool(eval_node(parsed))
        except Exception:
            return False

    @staticmethod
    def declump_tracks_by_artist(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Smart Artist Spacing (De-clumper).
        Maximizes the distance between songs by the same artist, ensuring you
        never hear back-to-back repetitions of the same artist.
        """
        if len(tracks) <= 2:
            return list(tracks)

        def _get_artist_key(item: Dict[str, Any]) -> str:
            a = item.get("primary_artist") or item.get("artists")
            if isinstance(a, list):
                return str(a[0]) if a else "Unknown"
            return str(a) if a else "Unknown"

        by_artist = defaultdict(list)
        for t in tracks:
            art = _get_artist_key(t)
            by_artist[art].append(t)

        buckets = sorted(by_artist.values(), key=len, reverse=True)
        result: List[Dict[str, Any]] = []

        while any(buckets):
            active = [b for b in buckets if b]
            if not active:
                break

            last_artist = _get_artist_key(result[-1]) if result else None
            candidates = [b for b in active if _get_artist_key(b[0]) != last_artist]
            if not candidates:
                candidates = active

            best_bucket = max(candidates, key=len)
            item = best_bucket.pop(0)
            result.append(item)

        return result

    @staticmethod
    def filter_and_sort_tracks(
        tracks: List[Dict[str, Any]],
        filter_expr: Optional[str] = None,
        artist_filter: Optional[str] = None,
        genre_filter: Optional[str] = None,
        theme_filter: Optional[str] = None,
        decade_filter: Optional[str] = None,
        language_filter: Optional[str] = None,
        clean_only: bool = False,
        explicit_only: bool = False,
        sort_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Filters tracks by human dimensions and applies smart sorting algorithms."""
        filtered = list(tracks)

        if artist_filter:
            target_artists = [a.strip().lower() for a in artist_filter.split(",") if a.strip()]
            filtered = [
                t for t in filtered
                if any(target in t.get("artists", "").lower() for target in target_artists)
            ]

        # 2. Genre Filter
        if genre_filter:
            target_genres = [g.strip().lower() for g in genre_filter.split(",") if g.strip()]
            filtered = [
                t for t in filtered
                if any(
                    tg in t.get("primary_genre", "").lower() or
                    tg.replace("-", " ") in t.get("primary_genre", "").lower() or
                    tg.replace(" ", "-") in t.get("primary_genre", "").lower() or
                    any(tg in g.lower() or tg.replace("-", " ") in g.lower() for g in t.get("genres", []))
                    for tg in target_genres
                )
            ]

        # 3. Theme Filter
        if theme_filter:
            target_themes = [th.strip().lower() for th in theme_filter.split(",") if th.strip()]
            filtered = [
                t for t in filtered
                if any(
                    th in t.get("theme", "").lower() or
                    th.replace("-", " ") in t.get("theme", "").lower() or
                    th.replace(" ", "-") in t.get("theme", "").lower()
                    for th in target_themes
                )
            ]

        if decade_filter:
            target_decades = [d.strip().lower() for d in decade_filter.split(",") if d.strip()]
            filtered = [
                t for t in filtered
                if any(td == t.get("decade", "").lower() or td in t.get("era", "").lower() for td in target_decades)
            ]

        if language_filter:
            target_langs = [l.strip().lower() for l in language_filter.split(",") if l.strip()]
            filtered = [
                t for t in filtered
                if any(tl in t.get("language", "").lower() for tl in target_langs)
            ]

        if clean_only:
            filtered = [t for t in filtered if t.get("is_clean")]
        elif explicit_only:
            filtered = [t for t in filtered if t.get("is_explicit")]

        if filter_expr:
            filtered = [t for t in filtered if SpotifyClient.evaluate_filter(t, filter_expr)]

        if sort_by:
            sb = sort_by.strip().lower()

            if sb in ("declump", "artist-spacing", "smart-artist-spacing"):
                filtered = SpotifyClient.declump_tracks_by_artist(filtered)

            elif sb in ("chronological", "time-travel", "oldest-first"):
                filtered.sort(key=lambda t: (t.get("release_year") or 9999, t.get("release_date") or ""))

            elif sb in ("newest", "newest-first", "reverse-chronological"):
                filtered.sort(key=lambda t: (t.get("release_year") or 0, t.get("release_date") or ""), reverse=True)

            elif sb in ("decade", "era"):
                decade_order = {"60s": 1, "70s": 2, "80s": 3, "90s": 4, "2000s": 5, "2010s": 6, "2020s": 7}
                filtered.sort(key=lambda t: (decade_order.get(t.get("decade", "").lower(), 99), t.get("release_year") or 9999))

            elif sb in ("genre", "genre-flow"):
                genre_sequence = [
                    "Pop", "Indie / Alternative", "Rock", "Metal", "Electronic / Dance",
                    "Hip-Hop / Rap", "R&B / Soul", "Latin", "K-Pop", "Desi / South Asian",
                    "Country / Americana", "Folk & Acoustic", "Jazz & Blues", "Classical / Cinematic"
                ]
                genre_idx = {g.lower(): i for i, g in enumerate(genre_sequence)}
                filtered.sort(key=lambda t: (genre_idx.get(t.get("primary_genre", "").lower(), 99), t.get("popularity", 0)), reverse=False)

            elif sb in ("theme", "vibe", "theme-flow"):
                filtered.sort(key=lambda t: (t.get("theme", ""), t.get("popularity", 0)), reverse=True)

            elif sb in ("popularity", "hits", "hits-first"):
                filtered.sort(key=lambda t: t.get("popularity", 0), reverse=True)

            elif sb in ("gems", "gems-first", "underground"):
                filtered.sort(key=lambda t: t.get("popularity", 0), reverse=False)

            elif sb in ("artist", "artist-a-z"):
                filtered.sort(key=lambda t: t.get("primary_artist", "").lower())

            elif sb in ("artist-z-a", "artist:desc"):
                filtered.sort(key=lambda t: t.get("primary_artist", "").lower(), reverse=True)

            elif sb in ("album", "album-flow"):
                filtered.sort(key=lambda t: (t.get("primary_artist", "").lower(), t.get("album", "").lower(), t.get("track_number", 1)))

            elif sb in ("duration:asc", "quick-first"):
                filtered.sort(key=lambda t: t.get("duration_ms", 0))

            elif sb in ("duration:desc", "epic-first"):
                filtered.sort(key=lambda t: t.get("duration_ms", 0), reverse=True)

            elif sb in ("recently-added", "newest-added"):
                filtered.sort(key=lambda t: t.get("added_at", ""), reverse=True)

        return filtered

    def create_playlist(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        track_uris: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Creates a new playlist and adds tracks in batches of 100."""
        me = self.get_me()
        user_id = me["id"]

        payload = {
            "name": name,
            "description": description or "Created by Spotify Playlist Manager plugin",
            "public": public
        }

        print(f"Creating new Spotify playlist '{name}'...")
        try:
            playlist = self.api_request("POST", "me/playlists", json_data=payload)
        except Exception:
            playlist = self.api_request("POST", f"users/{user_id}/playlists", json_data=payload)
            
        playlist_id = playlist["id"]
        playlist_url = playlist.get("external_urls", {}).get("spotify")

        if track_uris:
            print(f"Adding {len(track_uris)} tracks to playlist '{name}'...")
            chunk_size = 100
            for i in range(0, len(track_uris), chunk_size):
                chunk = track_uris[i:i + chunk_size]
                try:
                    self.api_request("POST", f"playlists/{playlist_id}/items", json_data={"uris": chunk})
                except Exception:
                    self.api_request("POST", f"playlists/{playlist_id}/tracks", json_data={"uris": chunk})

        return {
            "id": playlist_id,
            "name": name,
            "url": playlist_url,
            "total_tracks": len(track_uris) if track_uris else 0
        }

    def delete_playlist(self, playlist_identifier: str) -> bool:
        """Unfollows (deletes) a playlist from the user's Spotify account."""
        clean_id = self.extract_playlist_id(playlist_identifier)
        print(f"Deleting/unfollowing Spotify playlist ID: {clean_id}...")
        self.api_request("DELETE", f"playlists/{clean_id}/followers")
        return True
