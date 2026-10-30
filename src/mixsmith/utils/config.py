"""Configuration and credential resolution for Mixsmith."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.config")

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def get_default_config_dir() -> Path:
    """Returns the platform-specific default config directory."""
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "mixsmith"
    return Path.home() / ".config" / "mixsmith"


def get_legacy_plugin_credentials_path() -> Path:
    """Returns the legacy Gemini/Antigravity plugin credentials path for backward compatibility."""
    return Path.home() / ".gemini" / "config" / "plugins" / "spotify" / "credentials.json"


@dataclass
class AppConfig:
    """Application configuration and credentials container."""
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    credentials_file: Optional[Path] = None

    @classmethod
    def load(cls, custom_path: Optional[Path] = None) -> AppConfig:
        """Loads configuration from environment variables, .env, and credentials files."""
        # Check .env if present
        env_path = Path(".env")
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            except Exception as e:
                logger.debug(f"Could not parse .env file: {e}")

        # Resolve credentials file path
        creds_file = None
        data: Dict[str, Any] = {}

        candidate_paths = []
        if custom_path:
            candidate_paths.append(Path(custom_path))
        candidate_paths.append(get_default_config_dir() / "credentials.json")
        candidate_paths.append(get_legacy_plugin_credentials_path())

        for p in candidate_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    creds_file = p
                    break
                except Exception as e:
                    logger.debug(f"Could not read credentials from {p}: {e}")

        # If no file found, default target is the standard config directory
        if not creds_file:
            creds_file = custom_path or (get_default_config_dir() / "credentials.json")

        # Environment variables take precedence over file contents
        client_id = os.environ.get("SPOTIFY_CLIENT_ID") or data.get("client_id")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or data.get("client_secret")
        redirect_uri = (
            os.environ.get("SPOTIFY_REDIRECT_URI")
            or data.get("redirect_uri")
            or DEFAULT_REDIRECT_URI
        )
        access_token = os.environ.get("SPOTIFY_ACCESS_TOKEN") or data.get("access_token")
        refresh_token = os.environ.get("SPOTIFY_REFRESH_TOKEN") or data.get("refresh_token")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            access_token=access_token,
            refresh_token=refresh_token,
            credentials_file=creds_file
        )

    def save_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        """Persists updated OAuth tokens to the resolved credentials file."""
        self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token

        if not self.credentials_file:
            self.credentials_file = get_default_config_dir() / "credentials.json"

        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)

        existing: Dict[str, Any] = {}
        if self.credentials_file.exists():
            try:
                with open(self.credentials_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        existing["client_id"] = self.client_id
        if self.client_secret:
            existing["client_secret"] = self.client_secret
        existing["redirect_uri"] = self.redirect_uri
        existing["access_token"] = self.access_token
        if self.refresh_token:
            existing["refresh_token"] = self.refresh_token

        with open(self.credentials_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        logger.debug(f"Saved credentials to {self.credentials_file}")
