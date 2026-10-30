"""OAuth2 authentication and token management for Spotify with PKCE and state validation."""

from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import socketserver
import urllib.parse
import webbrowser

import requests

from mixsmith.core.exceptions import (
    AuthorizationDeniedError,
    CredentialsNotFoundError,
)
from mixsmith.utils.config import AppConfig
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.auth")

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-read-private",
    "user-read-email"
]


class _AuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Local HTTP server handler to intercept the OAuth redirect callback with state verification."""
    auth_code: str | None = None
    received_state: str | None = None
    error: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _AuthCallbackHandler.auth_code = params["code"][0]
            _AuthCallbackHandler.received_state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """<!DOCTYPE html>
            <html>
            <head><title>Mixsmith - Authorized</title></head>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background: #121212; color: #fff;">
                <h1 style="color: #1DB954;">Authentication Successful!</h1>
                <p>Mixsmith has received your authorization. You can now close this tab and return to the terminal.</p>
            </body>
            </html>"""
            self.wfile.write(html.encode("utf-8"))
        elif "error" in params:
            _AuthCallbackHandler.error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Denied</h1>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence local server request logging
        pass


class OAuthManager:
    """
    Manages Spotify OAuth2 authorization flow with Proof Key for Code Exchange (PKCE)
    and cryptographic state validation.
    """

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        self._active_code_verifier: str | None = None
        self._active_state: str | None = None

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """
        Generates RFC 7636 compliant code_verifier and code_challenge pair.
        Returns:
            (code_verifier, code_challenge)
        """
        # Cryptographically secure random 64-byte string
        code_verifier = secrets.token_urlsafe(64)
        # SHA-256 digest base64url-encoded without padding
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return code_verifier, code_challenge

    @staticmethod
    def generate_state() -> str:
        """Generates a random state string to protect against CSRF attacks."""
        return secrets.token_urlsafe(16)

    def get_auth_url(
        self,
        state: str | None = None,
        code_challenge: str | None = None
    ) -> str:
        """Constructs the Spotify OAuth authorization URL with PKCE and state."""
        if not self.config.client_id:
            raise CredentialsNotFoundError(
                "Spotify Client ID is missing. Set SPOTIFY_CLIENT_ID or run 'mixsmith auth setup'."
            )

        params: dict[str, str] = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(SCOPES),
            "show_dialog": "true"
        }

        if state:
            params["state"] = state
            self._active_state = state

        if code_challenge:
            params["code_challenge_method"] = "S256"
            params["code_challenge"] = code_challenge

        return f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def authorize_interactive(self, port: int = 8888) -> str:
        """
        Opens user's browser, intercepts redirect callback, validates state,
        and exchanges authorization code with PKCE verification.
        """
        if not self.config.client_id:
            raise CredentialsNotFoundError("SPOTIFY_CLIENT_ID is required for authentication.")

        # Generate PKCE verifier/challenge and CSRF state
        verifier, challenge = self.generate_pkce_pair()
        state = self.generate_state()
        self._active_code_verifier = verifier
        self._active_state = state

        auth_url = self.get_auth_url(state=state, code_challenge=challenge)
        print(f"\nOpening browser for Spotify authentication (PKCE enabled)...\n{auth_url}\n")
        webbrowser.open(auth_url)

        _AuthCallbackHandler.auth_code = None
        _AuthCallbackHandler.received_state = None
        _AuthCallbackHandler.error = None

        with socketserver.TCPServer(("127.0.0.1", port), _AuthCallbackHandler) as httpd:
            httpd.timeout = 120
            while not _AuthCallbackHandler.auth_code and not _AuthCallbackHandler.error:
                httpd.handle_request()

        if _AuthCallbackHandler.error:
            raise AuthorizationDeniedError(f"Spotify authentication error: {_AuthCallbackHandler.error}")

        if not _AuthCallbackHandler.auth_code:
            raise AuthorizationDeniedError("Timed out waiting for authentication callback.")

        # Validate state parameter against CSRF attacks
        if _AuthCallbackHandler.received_state != state:
            raise AuthorizationDeniedError(
                f"OAuth state mismatch: expected '{state}' but received '{_AuthCallbackHandler.received_state}'. "
                "Possible CSRF attack."
            )

        return self.exchange_code_for_token(
            code=_AuthCallbackHandler.auth_code,
            code_verifier=verifier
        )

    def exchange_code_for_token(self, code: str, code_verifier: str | None = None) -> str:
        """Exchanges an authorization code for access and refresh tokens using PKCE."""
        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id or ""
        }

        # Include PKCE verifier if supplied or available
        verifier = code_verifier or self._active_code_verifier
        if verifier:
            data["code_verifier"] = verifier

        # Include Basic auth header if client_secret is present
        if self.config.client_secret:
            auth_header = base64.b64encode(
                f"{self.config.client_id}:{self.config.client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {auth_header}"

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data, timeout=15)
        if resp.status_code != 200:
            raise AuthorizationDeniedError(f"Failed to exchange code for token: HTTP {resp.status_code} ({resp.text})")

        token_data = resp.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token") or self.config.refresh_token

        self.config.save_tokens(access_token, refresh_token)
        logger.info("Successfully authenticated with Spotify (PKCE verified).")
        return access_token

    def refresh_access_token(self) -> str | None:
        """Refreshes the OAuth access token using the stored refresh token."""
        if not self.config.refresh_token:
            logger.warning("No refresh token available.")
            return None

        headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self.config.refresh_token,
            "client_id": self.config.client_id or ""
        }

        if self.config.client_secret:
            auth_header = base64.b64encode(
                f"{self.config.client_id}:{self.config.client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {auth_header}"

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Failed to refresh token: HTTP {resp.status_code} ({resp.text})")
            return None

        token_data = resp.json()
        new_access_token = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", self.config.refresh_token)

        self.config.save_tokens(new_access_token, new_refresh)
        logger.info("Spotify access token refreshed successfully.")
        return new_access_token

    def get_valid_token(self) -> str:
        """Returns a valid access token or refreshes it if needed."""
        if self.config.access_token:
            return self.config.access_token

        if self.config.refresh_token:
            token = self.refresh_access_token()
            if token:
                return token

        raise CredentialsNotFoundError(
            "No active Spotify authentication found. Run 'mixsmith auth login' first."
        )
