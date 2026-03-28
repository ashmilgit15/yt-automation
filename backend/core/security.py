import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import get_settings


settings = get_settings()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _build_fernet() -> Fernet:
    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    token = _build_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def decrypt_secret(value: str) -> str:
    token = value[4:] if value.startswith("enc:") else value
    return _build_fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_secret_maybe_legacy(value: str) -> str:
    try:
        return decrypt_secret(value)
    except (InvalidToken, ValueError):
        return value
