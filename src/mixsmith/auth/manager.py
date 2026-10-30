"""OAuth2 authentication and token management for Spotify."""

from __future__ import annotations

import base64
import http.server
import json
import socketserver
import sys
import time
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

import requests

from mixsmith.core.exceptions import (
    AuthorizationDeniedError,
    CredentialsNotFoundError,
    TokenExpiredError,
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
    """Local HTTP server handler to intercept the OAuth redirect code."""
    auth_code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _AuthCallbackHandler.auth_code = params["code"][0]
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
    """Manages Spotify OAuth2 authorization flow and token lifecycle."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.load()

    def get_auth_url(self) -> str:
        """Constructs the Spotify OAuth authorization URL."""
        if not self.config.client_id:
            raise CredentialsNotFoundError(
                "Spotify Client ID is missing. Set SPOTIFY_CLIENT_ID or run 'mixsmith auth setup'."
            )
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(SCOPES),
            "show_dialog": "true"
        }
        return f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def authorize_interactive(self, port: int = 8888) -> str:
        """Opens the user's browser, handles redirect callback, and retrieves access tokens."""
        if not self.config.client_id or not self.config.client_secret:
            raise CredentialsNotFoundError("Both SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required.")

        auth_url = self.get_auth_url()
        print(f"\nOpening browser for Spotify authentication...\n{auth_url}\n")
        webbrowser.open(auth_url)

        _AuthCallbackHandler.auth_code = None
        _AuthCallbackHandler.error = None

        with socketserver.TCPServer(("127.0.0.1", port), _AuthCallbackHandler) as httpd:
            httpd.timeout = 120
            while not _AuthCallbackHandler.auth_code and not _AuthCallbackHandler.error:
                httpd.handle_request()

        if _AuthCallbackHandler.error:
            raise AuthorizationDeniedError(f"Spotify authentication error: {_AuthCallbackHandler.error}")

        if not _AuthCallbackHandler.auth_code:
            raise AuthorizationDeniedError("Timed out waiting for authentication callback.")

        return self.exchange_code_for_token(_AuthCallbackHandler.auth_code)

    def exchange_code_for_token(self, code: str) -> str:
        """Exchanges an authorization code for access and refresh tokens."""
        auth_header = base64.b64encode(
            f"{self.config.client_id}:{self.config.client_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri
        }

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data, timeout=15)
        if resp.status_code != 200:
            raise AuthorizationDeniedError(f"Failed to exchange code for token: HTTP {resp.status_code}")

        token_data = resp.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token") or self.config.refresh_token

        self.config.save_tokens(access_token, refresh_token)
        logger.info("Successfully authenticated with Spotify.")
        return access_token

    def refresh_access_token(self) -> Optional[str]:
        """Refreshes the OAuth access token using the stored refresh token."""
        if not self.config.refresh_token:
            logger.warning("No refresh token available.")
            return None

        auth_header = base64.b64encode(
            f"{self.config.client_id}:{self.config.client_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.config.refresh_token
        }

        resp = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Failed to refresh token: HTTP {resp.status_code}")
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
