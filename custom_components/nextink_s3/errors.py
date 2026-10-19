"""Sanitized exceptions: never retain server bodies, URLs or credentials."""


class NextInkError(Exception):
    """Base error."""


class AuthenticationError(NextInkError):
    """Explicit credential rejection."""


class InteractiveAuthError(AuthenticationError):
    """Interactive verification required; automatic login must stop."""


class StructureError(NextInkError):
    """Unknown or ambiguous page structure."""


class FormError(StructureError):
    """Unsupported or unsafe login form."""


class DataError(StructureError):
    """Missing or invalid quota data."""


class ConnectionError(NextInkError):
    """Temporary network or HTTP error."""


class AccessDeniedError(ConnectionError):
    """403 without reliable authentication evidence."""


class RateLimitError(ConnectionError):
    """A server retry deadline applies to this account."""

    def __init__(self, retry_seconds: float) -> None:
        super().__init__("rate_limited")
        self.retry_seconds = retry_seconds
