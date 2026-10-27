"""Hasła i tokeny — na bibliotekach standardowych, bez zewnętrznych zależności."""

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Weryfikacja odporna na atak czasowy (compare_digest)."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if algo != _ALGO:
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def verify_env_password(candidate: str, expected: str) -> bool:
    """Porównanie z hasłem z konfiguracji (ADMIN_PASSWORD).

    Hasło ze zmiennej środowiskowej jest jawne, więc nie ma czego hashować —
    liczy się tylko to, żeby porównanie nie wyciekało informacji czasem trwania.
    """
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def new_token() -> str:
    """Token uczestnika — ląduje w localStorage telefonu i służy do reconnectu."""
    return secrets.token_urlsafe(24)
