from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError


def _get_cipher() -> Fernet:
    settings = get_settings()
    if not settings.fernet_key:
        raise ConfigurationError("FERNET_KEY must be configured to encrypt bot tokens.")
    return Fernet(settings.fernet_key.encode("utf-8"))


def encrypt_token(token: str) -> bytes:
    cipher = _get_cipher()
    return cipher.encrypt(token.encode("utf-8"))


def decrypt_token(token_cipher: bytes) -> str:
    cipher = _get_cipher()
    try:
        return cipher.decrypt(token_cipher).decode("utf-8")
    except InvalidToken as exc:
        raise ConfigurationError("Failed to decrypt bot token.") from exc

