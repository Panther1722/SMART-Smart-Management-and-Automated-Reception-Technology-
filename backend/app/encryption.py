"""Field-level encryption at rest for guest PII (Fernet / AES)."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

logger = logging.getLogger("app.encryption")


def _fernet() -> Fernet | None:
    key = get_settings().field_encryption_key.strip()
    if not key:
        return None
    try:
        return Fernet(key.encode() if len(key) == 44 else base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
    except Exception:
        logger.exception("Invalid FIELD_ENCRYPTION_KEY")
        return None


def encrypt_value(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return plaintext
    f = _fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str | None) -> str | None:
    if ciphertext is None or ciphertext == "":
        return ciphertext
    f = _fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ciphertext
