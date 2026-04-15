"""Exceptions for the SberHome integration."""


class SberSmartHomeError(Exception):
    """Base exception for SberHome."""


class SberAuthError(SberSmartHomeError):
    """Authentication/authorization error."""


class SberApiError(SberSmartHomeError):
    """API returned an error response."""

    def __init__(
        self, code: int, status_code: int, message: str, retry_after: int = 0
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"{code} ({status_code}): {message}")


class SberConnectionError(SberSmartHomeError):
    """Network/connection error."""
