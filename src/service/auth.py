"""GitHub OIDC JWT verification.

GitHub Actions can request an OIDC token from
``https://token.actions.githubusercontent.com``.  The token is a standard
JWT signed with RS256.  We verify:

1. Signature — against the issuer's JWKS (``<issuer>/.well-known/jwks``).
2. Issuer / audience — standard claims.
3. Repository claim — must be in the allow-list so only approved repos
   can hit the service.

The issuer URL is configurable so a **mock OIDC provider** can be used
for local end-to-end testing of the full auth flow.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"

# Cached per-issuer JWKS clients
_jwks_clients: dict[str, tuple[PyJWKClient, float]] = {}
_JWKS_REFRESH_INTERVAL = 3600


def _get_jwks_client(issuer: str) -> PyJWKClient:
    now = time.time()
    entry = _jwks_clients.get(issuer)
    if entry is None or (now - entry[1]) > _JWKS_REFRESH_INTERVAL:
        jwks_url = f"{issuer.rstrip('/')}/.well-known/jwks"
        client = PyJWKClient(jwks_url, cache_keys=True)
        _jwks_clients[issuer] = (client, now)
        return client
    return entry[0]


def verify_oidc_token(
    token: str,
    *,
    allowed_repos: list[str],
    expected_audience: str = "erc7730-analyzer",
    issuer: str = GITHUB_OIDC_ISSUER,
) -> dict[str, Any]:
    """Decode and verify an OIDC JWT (GitHub Actions or mock provider).

    Returns the full claims dict on success.
    Raises ``jwt.exceptions.PyJWTError`` (or subclass) on failure.
    """
    client = _get_jwks_client(issuer)
    signing_key = client.get_signing_key_from_jwt(token)

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=expected_audience,
        options={"require": ["exp", "iss", "aud", "sub", "repository"]},
    )

    repo = claims.get("repository", "")
    if repo not in allowed_repos:
        raise jwt.InvalidTokenError(
            f"Repository '{repo}' is not in the allow-list: {allowed_repos}"
        )

    logger.info(
        "[AUTH] Token verified — issuer=%s repo=%s workflow=%s ref=%s",
        issuer,
        repo,
        claims.get("workflow", "?"),
        claims.get("ref", "?"),
    )
    return claims


async def verify_token_or_dev(
    authorization: str | None,
    *,
    allowed_repos: list[str],
    dev_mode: bool = False,
    issuer: str = GITHUB_OIDC_ISSUER,
) -> dict[str, Any] | None:
    """Convenience wrapper used by FastAPI endpoints.

    In dev mode, returns ``None`` (no claims) and skips verification.
    Otherwise, extracts the Bearer token and verifies it.
    """
    if dev_mode:
        logger.debug("[AUTH] dev mode — skipping token verification")
        return None

    if not authorization or not authorization.startswith("Bearer "):
        raise jwt.InvalidTokenError("Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    return verify_oidc_token(token, allowed_repos=allowed_repos, issuer=issuer)
