"""Credential handling — local Digest (Gen2+) and Basic (Gen1) auth helpers.

Centralizes the auth maths so the backends stay about transport, not crypto. Cloud
auth is just an account-wide ``auth_key`` injected into the request body (handled in
:mod:`shelly_mcp.backends.cloud`); the HTTP-level schemes live here.

Credentials are used to compute headers only — never logged, echoed, or returned.
"""

from __future__ import annotations

import hashlib

import aiohttp


def basic_auth(username: str, password: str | None) -> aiohttp.BasicAuth | None:
    """An aiohttp Basic-auth object for Gen1, or None when no password is set."""
    return aiohttp.BasicAuth(username, password) if password else None


def parse_digest_challenge(header: str) -> dict[str, str]:
    """Parse a ``WWW-Authenticate: Digest ...`` header into its key=value parts."""
    scheme, _, rest = header.partition(" ")
    if scheme.lower() != "digest":
        return {}
    parts: dict[str, str] = {}
    for token in rest.split(","):
        key, _, value = token.strip().partition("=")
        parts[key.strip()] = value.strip().strip('"')
    return parts


def digest_authorization(
    challenge: dict[str, str], *, user: str, password: str, method: str, uri: str, cnonce: str
) -> str:
    """Compute an RFC 7616 SHA-256 Digest ``Authorization`` header value.

    Pure + deterministic given ``cnonce`` (so it's unit-testable against a vector).
    Shelly Gen2+ uses ``algorithm=SHA-256`` with ``qop=auth``.
    """
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    qop = challenge.get("qop", "auth")
    nc = "00000001"

    def h(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    ha1 = h(f"{user}:{realm}:{password}")
    ha2 = h(f"{method}:{uri}")
    response = h(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    return (
        f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
        f'qop={qop}, nc={nc}, cnonce="{cnonce}", response="{response}", algorithm=SHA-256'
    )
