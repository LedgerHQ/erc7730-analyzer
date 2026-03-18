#!/usr/bin/env python3
"""Mock GitHub OIDC provider for local end-to-end auth testing.

Starts a tiny HTTP server that:
  - Generates an ephemeral RSA-2048 key pair on startup
  - Serves ``/.well-known/jwks`` (public key in JWK format)
  - Serves ``/token?audience=<aud>`` — mints a signed JWT with
    GitHub-like claims (repository, workflow, ref, …)

The analyzer service verifies tokens against this mock the same way it
would against GitHub's real ``token.actions.githubusercontent.com``.

Usage
-----
    # Start mock on port 8740 (background):
    python scripts/mock_oidc.py &

    # Or with custom port / repo:
    python scripts/mock_oidc.py --port 8740 --repo LedgerHQ/clear-signing-erc7730-registry

    # The client can then get a token from the mock:
    ACTIONS_ID_TOKEN_REQUEST_URL="http://localhost:8740/token" \
    ACTIONS_ID_TOKEN_REQUEST_TOKEN="mock" \
    python -m service.client --service-url http://localhost:8730 --descriptor ...

    # The service must be started with:
    OIDC_ISSUER_URL=http://localhost:8740 python -m service.app
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

logger = logging.getLogger(__name__)

# Generated once at startup
_private_key: rsa.RSAPrivateKey | None = None
_kid = "mock-key-1"


def _generate_keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _int_to_base64url(n: int) -> str:
    byte_length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()


def _public_key_to_jwk(key: rsa.RSAPrivateKey) -> dict[str, Any]:
    pub = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": _kid,
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_base64url(pub.n),
        "e": _int_to_base64url(pub.e),
    }


def _mint_token(
    private_key: rsa.RSAPrivateKey,
    *,
    issuer: str,
    audience: str,
    repository: str,
    workflow: str = "Analyze (via Service)",
    ref: str = "refs/pull/42/merge",
) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": f"repo:{repository}:pull_request",
        "repository": repository,
        "workflow": workflow,
        "ref": ref,
        "actor": "mock-user",
        "event_name": "pull_request",
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }

    pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": _kid})


class _MockOIDCHandler(BaseHTTPRequestHandler):
    """Handles /.well-known/jwks and /token requests."""

    server: "_MockOIDCServer"

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/.well-known/jwks":
            self._respond_json({"keys": [_public_key_to_jwk(self.server.private_key)]})
            return

        if parsed.path == "/.well-known/openid-configuration":
            issuer = self.server.issuer
            self._respond_json({
                "issuer": issuer,
                "jwks_uri": f"{issuer}/.well-known/jwks",
                "token_endpoint": f"{issuer}/token",
            })
            return

        if parsed.path == "/token":
            qs = parse_qs(parsed.query)
            audience = qs.get("audience", ["erc7730-analyzer"])[0]
            token = _mint_token(
                self.server.private_key,
                issuer=self.server.issuer,
                audience=audience,
                repository=self.server.repository,
            )
            self._respond_json({"value": token})
            logger.info("[MOCK-OIDC] Minted token for audience=%s repo=%s", audience, self.server.repository)
            return

        self.send_error(404)

    def _respond_json(self, body: dict):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        logger.debug("[MOCK-OIDC] %s", format % args)


class _MockOIDCServer(HTTPServer):
    private_key: rsa.RSAPrivateKey
    issuer: str
    repository: str


def main():
    parser = argparse.ArgumentParser(description="Mock GitHub OIDC Provider")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8740)
    parser.add_argument("--repo", default="LedgerHQ/clear-signing-erc7730-registry",
                        help="Repository claim in minted tokens")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    private_key = _generate_keypair()
    issuer = f"http://{args.host}:{args.port}"

    server = _MockOIDCServer((args.host, args.port), _MockOIDCHandler)
    server.private_key = private_key
    server.issuer = issuer
    server.repository = args.repo

    logger.info("[MOCK-OIDC] Listening on %s", issuer)
    logger.info("[MOCK-OIDC] JWKS:  %s/.well-known/jwks", issuer)
    logger.info("[MOCK-OIDC] Token: %s/token?audience=erc7730-analyzer", issuer)
    logger.info("[MOCK-OIDC] Repo claim: %s", args.repo)
    logger.info("")
    logger.info("[MOCK-OIDC] To use with the service:")
    logger.info("  OIDC_ISSUER_URL=%s python -m service.app", issuer)
    logger.info("")
    logger.info("[MOCK-OIDC] To use with the client:")
    logger.info('  ACTIONS_ID_TOKEN_REQUEST_URL="%s/token" \\', issuer)
    logger.info('  ACTIONS_ID_TOKEN_REQUEST_TOKEN="mock" \\')
    logger.info("  python -m service.client --service-url http://localhost:8730 --descriptor ...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[MOCK-OIDC] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
