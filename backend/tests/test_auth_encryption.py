"""Auth token and encryption unit tests."""


from cryptography.fernet import Fernet

from app.auth import create_session_token, verify_session_token, verify_totp
from app.config import Settings, get_settings
from app.encryption import decrypt_value, encrypt_value


def test_session_token_roundtrip():
    settings = Settings(session_secret="test-secret-key-for-hmac", app_env="development")
    token = create_session_token("sess-123", settings)
    assert verify_session_token("sess-123", token, settings)
    assert not verify_session_token("sess-123", "wrong", settings)


def test_encryption_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    enc = encrypt_value("guest@example.com")
    assert decrypt_value(enc) == "guest@example.com"
    get_settings.cache_clear()


def test_totp_disabled_in_dev_without_secret():
    settings = Settings(admin_totp_secret="", app_env="development")
    assert verify_totp("000000", settings) is True
