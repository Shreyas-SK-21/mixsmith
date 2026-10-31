"""Mixsmith custom exceptions hierarchy."""


class MixsmithError(Exception):
    """Base exception for all Mixsmith errors."""


# --- Authentication & Credentials ---

class AuthError(MixsmithError):
    """Base exception for authentication failures."""


class CredentialsNotFoundError(AuthError):
    """Raised when Spotify API credentials cannot be found."""


class TokenExpiredError(AuthError):
    """Raised when an OAuth access token has expired and refresh failed."""


class AuthorizationDeniedError(AuthError):
    """Raised when the user denies OAuth access or authentication is cancelled."""


# --- API & Network ---

class APIError(MixsmithError):
    """Base exception for external API request errors."""
    def __init__(self, message: str, status_code: int = 0, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class RateLimitExceededError(APIError):
    """Raised when API rate limit (HTTP 429) is exceeded and retries exhausted."""
    def __init__(self, message: str, retry_after: int = 5):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ResourceNotFoundError(APIError):
    """Raised when a Spotify playlist, track, or user is not found (HTTP 404)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


# --- Core Curation & Sequencing ---

class CurationError(MixsmithError):
    """Base exception for curation, filtering, or sequencing failures."""


class InfeasibleConstraintError(CurationError):
    """Raised when playlist constraints are mathematically impossible to satisfy."""
    def __init__(self, message: str, constraint: str, details: dict | None = None):
        super().__init__(message)
        self.constraint = constraint
        self.details = details or {}


class FilterSyntaxError(CurationError):
    """Raised when a custom filter expression contains invalid syntax."""


class FilterMatchError(CurationError):
    """Raised when requested filters match zero tracks in the source library."""


class PlaylistMutationError(CurationError):
    """Raised when safe playlist mutation safeguards are violated or fail."""


class SnapshotDriftError(PlaylistMutationError):
    """Raised when the target playlist's snapshot ID changed unexpectedly during mutation."""


class PartialMutationError(PlaylistMutationError):
    """Raised when a batched mutation fails mid-execution, leaving the playlist in a partially modified state."""
    def __init__(self, message: str, playlist_id: str = "", batches_completed: int = 0, tracks_added: int = 0, details: dict | None = None):
        super().__init__(message)
        self.playlist_id = playlist_id
        self.batches_completed = batches_completed
        self.tracks_added = tracks_added
        self.details = details or {}


# --- Exporters ---

class ExportError(MixsmithError):
    """Raised when exporting to Excel, CSV, or other formats fails."""
