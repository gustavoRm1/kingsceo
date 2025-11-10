from __future__ import annotations


class AppError(RuntimeError):
    """Base application error."""


class ConfigurationError(AppError):
    """Raised when environment configuration is invalid."""


class PermissionError(AppError):
    """Raised when bot lacks required permissions."""


class NotFoundError(AppError):
    """Raised when a requested entity is not found."""


class AlreadyExistsError(AppError):
    """Raised when attempting to create a duplicate entity."""

