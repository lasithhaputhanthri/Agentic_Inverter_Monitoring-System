"""Error definitions for the IIR system.

Purpose: Provide typed exceptions for failure modes across the application.
Inputs: Error messages and context parameters.
Outputs: Custom exception instances inheriting from IIRError.
"""


class IIRError(Exception):
    """Base exception for all errors raised within the IIR application."""

    pass


class ConfigError(IIRError):
    """Raised when configuration validation fails or a required secret is missing.

    Ensures that missing secrets name the missing variable without leaking values.
    """

    def __init__(self, variable_name: str, message: str | None = None) -> None:
        self.variable_name = variable_name
        detail = message or f"Missing required configuration secret: {variable_name}"
        super().__init__(detail)


class FaultPlanError(IIRError):
    """Raised when fault planning encounters invalid parameters, overlapping faults, or unknown device IDs."""

    pass


class MonitorError(IIRError):
    """Raised when monitoring detects unknown devices or invalid operational state."""

    pass


class LLMError(IIRError):
    """Base exception for errors originating from LLM interactions."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM provider request times out."""

    pass


class LLMQuotaExceededError(LLMError):
    """Raised when a daily or per-run token or call budget is exhausted."""

    pass


class LLMUnavailableError(LLMError):
    """Raised when all provider retry attempts are exhausted."""

    pass
