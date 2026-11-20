"""Encryption of stored API tokens and hashing of issued MCP tokens (research R3, "Tokens at rest")."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_NONCE_BYTES = 12


class TokenCipher:
    """AES-256-GCM. Ciphertexts are ``base64(nonce || ciphertext||tag)``."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("encryption key must be 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + sealed).decode()

    def decrypt(self, token: str) -> str:
        raw = base64.b64decode(token)
        return self._aead.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], None).decode()


def hash_token(token: str) -> str:
    """Storage key for an issued MCP token: we never store the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    """A new opaque, URL-safe token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def derive_key(master: bytes, purpose: str) -> bytes:
    """Derive an independent 32-byte sub-key so one secret can serve several purposes."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()).derive(
        master
    )
