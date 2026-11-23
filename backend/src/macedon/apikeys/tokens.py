"""Format of API key secrets. Kept free of imports from the rest of the app."""

import hashlib
import secrets

TOKEN_PREFIX = "mcd_"  # noqa: S105 - a public format marker, not a secret


def new_token() -> str:
    """A new secret with 256 bits of entropy."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # A plain hash is enough: the secret is random, so there is nothing to brute-force.
    return hashlib.sha256(token.encode()).hexdigest()


def is_api_key(token: str) -> bool:
    return token.startswith(TOKEN_PREFIX)


def token_prefix(token: str) -> str:
    """The visible start of a token, enough to recognize it in a list."""
    return token[: len(TOKEN_PREFIX) + 6]


def required_scope(method: str, path: str) -> str:
    """Reading is anything that does not change state, plus asking a question."""
    if method in ("GET", "HEAD", "OPTIONS") or (method == "POST" and path == "/query"):
        return "read"
    return "write"
