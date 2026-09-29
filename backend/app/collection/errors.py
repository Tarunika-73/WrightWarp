"""Structured exceptions adapters and the service raise/catch.

``CollectionService`` never lets a bare exception escape from an adapter
call: anything unexpected is caught and reclassified as
``CollectionErrorType.UNKNOWN_ERROR`` so a bug in one adapter cannot crash
the API or leak internal detail (stack traces, headers, cookies) to a
caller. Adapters that want a *specific* classification (e.g. a real
timeout) should raise ``CollectionException`` directly.
"""
from app.core.enums import CollectionErrorType

# Error types that represent a transient condition worth retrying, with
# conservative, bounded backoff. Everything else (validation errors,
# compliance blocks, auth failures) is retried zero times - retrying a
# request robots.txt/ToS disallows, or one that was malformed, would
# never succeed and is not "responsible collection".
RETRYABLE_ERROR_TYPES: frozenset[CollectionErrorType] = frozenset(
    {
        CollectionErrorType.NETWORK_ERROR,
        CollectionErrorType.TIMEOUT,
        CollectionErrorType.SOURCE_UNAVAILABLE,
        CollectionErrorType.RATE_LIMITED,
    }
)


class CollectionException(Exception):
    """Raised by an adapter (or internal collection code) with a known error type."""

    def __init__(self, error_type: CollectionErrorType, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.error_type in RETRYABLE_ERROR_TYPES


def is_retryable(error_type: CollectionErrorType) -> bool:
    return error_type in RETRYABLE_ERROR_TYPES
