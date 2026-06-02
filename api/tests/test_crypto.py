"""AES-GCM crypto module tests (M3)."""

from __future__ import annotations

import base64
import os

import pytest

from app.security.crypto import (
    _MAGIC,
    AeadCipher,
    DecryptionError,
    VersionedCipher,
    ciphertext_version,
    decode_kek,
    decrypt,
    encrypt,
    get_cipher,
)


def _make_kek_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def test_decode_kek_accepts_32_bytes() -> None:
    kek = base64.b64encode(b"\x00" * 32).decode("ascii")
    raw = decode_kek(kek)
    assert len(raw) == 32


def test_decode_kek_rejects_wrong_length() -> None:
    with pytest.raises(RuntimeError, match="32 bytes"):
        decode_kek(base64.b64encode(b"\x00" * 16).decode("ascii"))


def test_decode_kek_rejects_empty() -> None:
    with pytest.raises(RuntimeError, match="required"):
        decode_kek("")


def test_decode_kek_rejects_non_base64() -> None:
    with pytest.raises(RuntimeError, match="base64"):
        decode_kek("not!base64!")


def test_encrypt_decrypt_roundtrip() -> None:
    kek = _make_kek_b64()
    plaintext = "sk-ant-api-fake-key-12345"
    ciphertext = encrypt(plaintext, kek)
    assert ciphertext != plaintext
    assert isinstance(ciphertext, str)
    assert decrypt(ciphertext, kek) == plaintext


def test_encrypt_produces_unique_ciphertexts_for_same_plaintext() -> None:
    """Random nonce per call -> distinct ciphertexts even for identical input."""
    kek = _make_kek_b64()
    plaintext = "same-secret"
    c1 = encrypt(plaintext, kek)
    c2 = encrypt(plaintext, kek)
    assert c1 != c2
    # Both still decrypt to the same plaintext.
    assert decrypt(c1, kek) == plaintext
    assert decrypt(c2, kek) == plaintext


def test_decrypt_with_wrong_kek_raises() -> None:
    kek1 = _make_kek_b64()
    kek2 = _make_kek_b64()
    while kek1 == kek2:  # vanishingly unlikely collision -- guard anyway
        kek2 = _make_kek_b64()
    ciphertext = encrypt("payload", kek1)
    with pytest.raises(DecryptionError):
        decrypt(ciphertext, kek2)


def test_decrypt_tampered_ciphertext_raises() -> None:
    kek = _make_kek_b64()
    ciphertext = encrypt("payload", kek)
    blob = bytearray(base64.b64decode(ciphertext))
    # Flip a bit in the tag region (last byte).
    blob[-1] ^= 0x01
    tampered = base64.b64encode(bytes(blob)).decode("ascii")
    with pytest.raises(DecryptionError):
        decrypt(tampered, kek)


def test_decrypt_too_short_ciphertext_raises() -> None:
    kek = _make_kek_b64()
    short_blob = base64.b64encode(b"\x00" * 4).decode("ascii")
    with pytest.raises(DecryptionError, match="too short"):
        decrypt(short_blob, kek)


def test_decrypt_non_base64_raises() -> None:
    kek = _make_kek_b64()
    with pytest.raises(DecryptionError, match="base64"):
        decrypt("!!!not-base64!!!", kek)


def test_ciphertext_version_legacy_is_zero() -> None:
    """A legacy (magic-absent) blob reports version 0."""
    kek = _make_kek_b64()
    legacy = VersionedCipher(legacy=get_cipher(kek), registry={}, current_version=0)
    blob = legacy.encrypt("legacy-row")
    assert not base64.b64decode(blob).startswith(_MAGIC)
    assert ciphertext_version(blob) == 0


def test_ciphertext_version_reads_version_byte() -> None:
    """A versioned blob reports the version byte from its header."""
    legacy_kek = _make_kek_b64()
    v3_kek = _make_kek_b64()
    cipher = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={3: get_cipher(v3_kek)},
        current_version=3,
    )
    blob = cipher.encrypt("v3-row")
    assert ciphertext_version(blob) == 3


def test_ciphertext_version_does_not_decrypt() -> None:
    """Version detection works on a payload we cannot decrypt (no KEK)."""
    # Hand-build a versioned header with version 7 and random (undecryptable)
    # body; we only inspect the header, never the body.
    blob = _MAGIC + bytes([7]) + os.urandom(12) + os.urandom(16)
    assert ciphertext_version(base64.b64encode(blob).decode("ascii")) == 7


def test_ciphertext_version_rejects_non_base64() -> None:
    """Malformed input surfaces the same error class as decrypt."""
    with pytest.raises(DecryptionError, match="base64"):
        ciphertext_version("!!!not-base64!!!")


def test_ciphertext_version_rejects_truncated_header() -> None:
    """Magic prefix but no version byte -> DecryptionError."""
    too_short = base64.b64encode(_MAGIC).decode("ascii")
    with pytest.raises(DecryptionError, match="too short"):
        ciphertext_version(too_short)


def test_aead_cipher_class_methods_match_module_helpers() -> None:
    """`AeadCipher.from_kek_base64(k)` builds an equivalent cipher to module
    helpers."""
    kek = _make_kek_b64()
    cipher = AeadCipher.from_kek_base64(kek)
    ct = cipher.encrypt("test")
    # Module-level decrypt with the same KEK should succeed.
    assert decrypt(ct, kek) == "test"
