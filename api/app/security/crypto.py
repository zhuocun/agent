"""AES-GCM at-rest encryption for BYOK keys.

The KEK (key encryption key) is supplied via the `BYOK_ENCRYPTION_KEK` env var,
base64-encoded, and must be exactly 32 bytes after decoding. Boot fails fast if
the KEK is missing or malformed (see `app.config`). Each `encrypt()` call mints
a fresh 12-byte nonce. The on-disk format is
`base64(nonce || ciphertext_with_tag)` stored as TEXT in `api_key.ciphertext`.

KMS envelope encryption (a per-key DEK wrapped by a KMS-managed CMK) is the M4
hardening target — the KEK is itself a process-readable secret right now, which
is the weakest link in this design. The format above is forward-compatible: a
future envelope scheme can prepend a version byte without breaking decryption
of existing rows.

Decrypt failures are signaled by `DecryptionError`; the caller is responsible
for falling back to platform defaults (see `app.streaming.handler` per-request
BYOK resolution).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12  # AES-GCM standard nonce length.
_EXPECTED_KEK_LEN = 32  # AES-256-GCM.


class CryptoError(Exception):
    """Base for crypto subsystem errors."""


class DecryptionError(CryptoError):
    """Raised on tag-verification failures or malformed ciphertext."""


def decode_kek(kek_b64: str) -> bytes:
    """Decode a base64 KEK string into raw bytes, validating length.

    Raises `RuntimeError` (boot-time misconfiguration) if the KEK is missing,
    malformed, or the wrong length. Boot should call this once via
    `Settings.assert_prod_safe()` so misconfiguration fails fast rather than
    surfacing as a 500 on the first BYOK write.
    """
    if not kek_b64:
        raise RuntimeError("BYOK_ENCRYPTION_KEK is required for BYOK encryption.")
    try:
        raw = base64.b64decode(kek_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "BYOK_ENCRYPTION_KEK must be base64-encoded."
        ) from exc
    if len(raw) != _EXPECTED_KEK_LEN:
        raise RuntimeError(
            f"BYOK_ENCRYPTION_KEK must decode to exactly {_EXPECTED_KEK_LEN} bytes "
            f"(got {len(raw)})."
        )
    return raw


@dataclass(frozen=True)
class AeadCipher:
    """Thin wrapper over AESGCM bound to a specific KEK.

    Keep the AESGCM instance precomputed so per-call overhead is just a nonce
    generation + one AES block schedule. Cipher is stateless beyond the key.
    """

    _aead: AESGCM

    @classmethod
    def from_kek_base64(cls, kek_b64: str) -> AeadCipher:
        raw = decode_kek(kek_b64)
        return cls(_aead=AESGCM(raw))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt `plaintext` -> base64(nonce || ciphertext-with-tag).

        Nonce is random per call; never reused. AAD is not used: every cipher
        instance corresponds to a single trust domain (BYOK keys at rest), so
        there's no domain-separation requirement that AAD would add value to.
        """
        nonce = os.urandom(_NONCE_LEN)
        ct = self._aead.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, packed_b64: str) -> str:
        """Decrypt a `base64(nonce || ciphertext-with-tag)` blob to plaintext.

        Raises `DecryptionError` on any tag mismatch, length error, or base64
        decode failure. The caller should treat this as "key is unusable" and
        fall back to platform defaults rather than surfacing the error to the
        user.
        """
        try:
            blob = base64.b64decode(packed_b64.encode("ascii"), validate=True)
        except (ValueError, TypeError) as exc:
            raise DecryptionError("ciphertext is not valid base64") from exc
        if len(blob) <= _NONCE_LEN:
            raise DecryptionError("ciphertext too short to contain nonce + tag")
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        try:
            pt = self._aead.decrypt(nonce, ct, None)
        except InvalidTag as exc:
            raise DecryptionError("ciphertext tag verification failed") from exc
        return pt.decode("utf-8")


# Module-level cipher cache, keyed by KEK material so tests can build their own
# cipher without poisoning the process-wide one. Production code reaches the
# cipher via `get_cipher()` which reads from `Settings.byok_encryption_kek`.
# MVP: dict-based cache keyed by base64 KEK. Acceptable for KEK rotation
# because a stale cipher remains usable for old ciphertexts; M4 should add
# a versioned-KEK lookup so re-encrypted rows pick up the new key.
_CIPHER_CACHE: dict[str, AeadCipher] = {}


def get_cipher(kek_b64: str) -> AeadCipher:
    """Return a process-cached `AeadCipher` for the given KEK."""
    cached = _CIPHER_CACHE.get(kek_b64)
    if cached is not None:
        return cached
    cipher = AeadCipher.from_kek_base64(kek_b64)
    _CIPHER_CACHE[kek_b64] = cipher
    return cipher


def encrypt(plaintext: str, kek_b64: str) -> str:
    """Encrypt with the KEK supplied. Convenience wrapper over `get_cipher`."""
    return get_cipher(kek_b64).encrypt(plaintext)


def decrypt(ciphertext: str, kek_b64: str) -> str:
    """Decrypt with the KEK supplied. Raises `DecryptionError` on failure."""
    return get_cipher(kek_b64).decrypt(ciphertext)
