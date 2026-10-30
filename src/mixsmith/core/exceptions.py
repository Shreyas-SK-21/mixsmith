"""Mixsmith custom exceptions hierarchy."""


class MixsmithError(Exception):
    """Base exception for all Mixsmith errors."""
    pass


# --- Authentication & Credentials ---

class AuthError(MixsmithError):
    """Base exception for authentication failures."""
    pass


class CredentialsNotFoundError(AuthError):
    """Raised when Spotify API credentials cannot be found."""
    pass


class TokenExpiredError(AuthError):
    """Raised when an OAuth access token has expired and refresh failed."""
    pass


class AuthorizationDeniedError(AuthError):
    """Raised when the user denies OAuth access or authentication is cancelled."""
    pass


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
    pass


class InfeasibleConstraintError(CurationError):
    """Raised when playlist constraints are mathematically impossible to satisfy."""
    def __init__(self, message: str, constraint: str, details: dict = None):
        super().__init__(message)
        self.constraint = constraint
        self.details = details or {}


class FilterSyntaxError(CurationError):
    """Raised when a custom filter expression contains invalid syntax."""
    pass


class PlaylistMutationError(CurationError):
    """Raised when safe playlist mutation safeguards are violated or fail."""
    pass


class SnapshotDriftError(PlaylistMutationError):
    """Raised when the target playlist's snapshot ID changed unexpectedly during mutation."""
    pass


# --- Exporters ---

class ExportError(MixsmithError):
    """Raised when exporting to Excel, CSV, or other formats fails."""
    pass
