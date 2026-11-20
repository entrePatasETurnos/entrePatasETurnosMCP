import pytest
from cryptography.exceptions import InvalidTag

from entrepataseturnos_mcp.auth.crypto import TokenCipher, derive_key, hash_token, new_token


def test_round_trip_and_random_nonce() -> None:
    c = TokenCipher(bytes(32))
    a, b = c.encrypt("secret-token"), c.encrypt("secret-token")
    assert a != b
    assert "secret-token" not in a
    assert c.decrypt(a) == "secret-token"


def test_tampered_ciphertext_fails() -> None:
    import base64

    c = TokenCipher(bytes(32))
    raw = bytearray(base64.b64decode(c.encrypt("value")))
    raw[-1] ^= 1
    with pytest.raises(InvalidTag):
        c.decrypt(base64.b64encode(bytes(raw)).decode())


def test_hash_token_is_sha256_hex_without_token() -> None:
    token = new_token()
    digest = hash_token(token)
    assert len(digest) == 64 and token not in digest


def test_derived_keys_differ_by_purpose() -> None:
    assert derive_key(bytes(32), "a") != derive_key(bytes(32), "b")
    assert len(derive_key(bytes(32), "a")) == 32
