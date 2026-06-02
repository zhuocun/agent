"""AES-GCM at-rest encryption for BYOK keys, with versioned-KEK rotation.

Two on-disk formats coexist so KEK rotation does not require a rewrite pass:

  * **Legacy (`current_version == 0`)** -- `base64(nonce(12) || ct_with_tag)`.
    Uses the single env-var KEK (`BYOK_ENCRYPTION_KEK`). This is the format
    every row written before rotation was wired up, and remains the default
    so existing dev / prod databases stay readable byte-for-byte.

  * **Versioned (`current_version >= 1`)** -- `base64(MAGIC(4) || version(1)
    || nonce(12) || ct_with_tag)`. The version byte indexes into a registry
    of KEKs (`BYOK_KEK_VERSIONS`, parsed in `app.config`). Decrypt peeks at
    the magic prefix to pick the right cipher; encrypt always writes the
    `current_version`'s format. Old v1 rows keep decrypting after rotating
    to v2 because v1's KEK stays in the registry.

The magic prefix is the 4 ASCII bytes ``b"kekv"``. False positives on legacy
rows are astronomically unlikely -- a random 12-byte AES-GCM nonce begins
with those 4 specific bytes with probability ~2^-32. If a corrupted legacy
ciphertext somehow does start with `kekv` we surface a `DecryptionError`
rather than silently treating it as legacy, because the failure mode of
"crypto silently fell through to a different code path" is worse than a
loud error the operator can investigate.

The cipher cache lives in module state, keyed by KEK material. Tests build
their own cipher / registry via `AeadCipher.from_kek_base64()` and the
explicit `VersionedCipher(...)` constructor without touching the cache.

KMS envelope encryption (a per-key DEK wrapped by a KMS-managed CMK) is the
intended successor: when it lands, the registry entries become KMS key ARNs
instead of raw 32-byte KEKs, and `AeadCipher` becomes a thin wrapper over
KMS Encrypt/Decrypt. The on-disk format already carries a version byte so
the swap can happen one ciphertext at a time.

Decrypt failures surface as `DecryptionError`; the caller is responsible
for falling back to platform defaults (see `app.streaming.handler` for the
per-request BYOK resolution).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12  # AES-GCM standard nonce length.
_EXPECTED_KEK_LEN = 32  # AES-256-GCM.

# 4 ASCII bytes that prefix every versioned ciphertext. Chosen to be unlikely
# to collide with a random nonce-prefix on a legacy row (~2^-32 false match);
# any legacy row that happens to start with this prefix will fail-loud on
# decrypt rather than silently falling back, which is the safer failure mode.
_MAGIC = b"kekv"
_MAGIC_LEN = len(_MAGIC)
# Bytes before the nonce in the versioned format: magic + 1 version byte.
_HEADER_LEN = _MAGIC_LEN + 1
# Highest version byte we can encode in a single byte. We reject anything
# larger at the registry level so the on-disk header byte never overflows.
_MAX_KEK_VERSION = 255


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
        return self._decrypt_raw(blob)

    def _decrypt_raw(self, blob: bytes) -> str:
        """Decrypt a `nonce || ciphertext-with-tag` blob.

        Split out so the versioned path can hand us the post-header bytes
        without re-base64-decoding.
        """
        if len(blob) <= _NONCE_LEN:
            raise DecryptionError("ciphertext too short to contain nonce + tag")
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        try:
            pt = self._aead.decrypt(nonce, ct, None)
        except InvalidTag as exc:
            raise DecryptionError("ciphertext tag verification failed") from exc
        return pt.decode("utf-8")


@dataclass(frozen=True)
class VersionedCipher:
    """Dispatch between a legacy KEK and a versioned-KEK registry.

    The split exists so callers can stay version-agnostic: hand the same
    `VersionedCipher` instance to encrypt and decrypt, and the right path
    runs based on `current_version` (for writes) or the ciphertext header
    (for reads). The dataclass is frozen so a test fixture can build one
    without poisoning the module-level cipher cache.

    `current_version == 0` -> writes the legacy format using `legacy`; reads
    fall back to `legacy` when the magic prefix is absent.

    `current_version >= 1`  -> writes the versioned format using
    `registry[current_version]`; reads with the magic prefix look up the
    cipher by version byte, reads without the prefix still use `legacy` so
    pre-rotation rows keep decrypting.
    """

    legacy: AeadCipher
    registry: dict[int, AeadCipher] = field(default_factory=dict)
    current_version: int = 0

    def encrypt(self, plaintext: str) -> str:
        """Encrypt with the cipher selected by `current_version`."""
        if self.current_version == 0:
            return self.legacy.encrypt(plaintext)
        cipher = self.registry.get(self.current_version)
        if cipher is None:
            # Construction-time validation in `assert_prod_safe` should catch
            # this; raise the same boot-time error class here so a misordered
            # test fixture surfaces loudly.
            raise RuntimeError(
                f"no KEK registered for current version {self.current_version}"
            )
        nonce = os.urandom(_NONCE_LEN)
        ct = cipher._aead.encrypt(nonce, plaintext.encode("utf-8"), None)
        header = _MAGIC + bytes([self.current_version])
        return base64.b64encode(header + nonce + ct).decode("ascii")

    def decrypt(self, packed_b64: str) -> str:
        """Decrypt either format, dispatching on the magic prefix.

        A blob whose decoded bytes start with `MAGIC` is treated as versioned
        and routed through the registry. The version byte must resolve to a
        registered cipher -- a magic-present payload with an unknown version
        is a `DecryptionError` (not a fall-through to legacy), because that
        scenario means either ciphertext corruption or a registry that has
        lost the KEK that produced the row, neither of which we want to
        paper over.

        A blob without the magic prefix is legacy and decrypts via `legacy`.
        """
        try:
            blob = base64.b64decode(packed_b64.encode("ascii"), validate=True)
        except (ValueError, TypeError) as exc:
            raise DecryptionError("ciphertext is not valid base64") from exc

        if blob.startswith(_MAGIC):
            if len(blob) < _HEADER_LEN:
                raise DecryptionError("versioned ciphertext too short for header")
            version = blob[_MAGIC_LEN]
            cipher = self.registry.get(version)
            if cipher is None:
                raise DecryptionError(
                    f"no KEK registered for ciphertext version {version}"
                )
            return cipher._decrypt_raw(blob[_HEADER_LEN:])

        # No magic -> legacy format. Hand the already-decoded bytes off
        # rather than re-encoding so we don't pay a second base64 hop.
        return self.legacy._decrypt_raw(blob)


# Module-level cipher cache, keyed by KEK material so tests can build their own
# cipher without poisoning the process-wide one. Production code reaches the
# cipher via `get_cipher()` which reads from `Settings.byok_encryption_kek`.
# The cache is intentionally keyed by the raw base64 KEK so a versioned-KEK
# rotation that recycles KEK material reuses the cached AESGCM instance.
_CIPHER_CACHE: dict[str, AeadCipher] = {}


def get_cipher(kek_b64: str) -> AeadCipher:
    """Return a process-cached `AeadCipher` for the given KEK."""
    cached = _CIPHER_CACHE.get(kek_b64)
    if cached is not None:
        return cached
    cipher = AeadCipher.from_kek_base64(kek_b64)
    _CIPHER_CACHE[kek_b64] = cipher
    return cipher


def _build_versioned_cipher(
    legacy_kek_b64: str,
    registry_b64: dict[int, str],
    current_version: int,
) -> VersionedCipher:
    """Resolve a `VersionedCipher` from base64 KEKs via `get_cipher`.

    Centralized so the module helpers and tests build identical instances --
    in particular, ciphers come from the shared cache, so a legacy row
    written before the version registry existed stays decryptable through
    the same `AeadCipher` instance.
    """
    legacy = get_cipher(legacy_kek_b64)
    registry: dict[int, AeadCipher] = {
        version: get_cipher(kek_b64) for version, kek_b64 in registry_b64.items()
    }
    return VersionedCipher(
        legacy=legacy,
        registry=registry,
        current_version=current_version,
    )


def _settings_versioned_cipher(kek_b64: str) -> VersionedCipher:
    """Build the active `VersionedCipher` from process settings.

    Imported lazily to keep `app.config` from importing `app.security.crypto`
    at module load (config already does that the other direction via
    `decode_kek`). The `kek_b64` argument is the caller's view of the legacy
    KEK; we trust it for the legacy fall-through path and ignore it for the
    write path when `current_version >= 1`.
    """
    from app.config import get_settings

    settings = get_settings()
    return _build_versioned_cipher(
        legacy_kek_b64=kek_b64,
        registry_b64=settings.kek_version_registry,
        current_version=settings.byok_current_kek_version,
    )


def encrypt(plaintext: str, kek_b64: str) -> str:
    """Encrypt with the active KEK selected by settings.

    Bit-compatible with the pre-rotation single-KEK path when
    `BYOK_CURRENT_KEK_VERSION` is 0 (the default); writes the new versioned
    format otherwise. The `kek_b64` argument is the legacy KEK the call site
    already passes; it's still required so the legacy fallback works for
    decrypting old rows after rotation.
    """
    return _settings_versioned_cipher(kek_b64).encrypt(plaintext)


def decrypt(ciphertext: str, kek_b64: str) -> str:
    """Decrypt with the cipher selected by the ciphertext header.

    Reads with the magic prefix dispatch through the version registry;
    reads without it fall through to the legacy KEK at `kek_b64`. Raises
    `DecryptionError` on any failure.
    """
    return _settings_versioned_cipher(kek_b64).decrypt(ciphertext)


def ciphertext_version(blob: str) -> int:
    """Return the KEK version a stored ciphertext was written under.

    Header inspection only -- never decrypts, so it's safe to call without a
    cipher / KEK in hand (e.g. when deciding whether a row needs a re-wrap).

    A magic-prefixed blob returns its version byte; a magic-absent blob is the
    legacy single-KEK format and returns 0. Malformed input surfaces the same
    `DecryptionError` that `decrypt` raises on bad base64 / truncation, so the
    caller can treat "can't tell the version" and "can't decrypt" identically.
    Reuses the module's MAGIC / header constants so there's a single source of
    truth for the on-disk layout.
    """
    try:
        decoded = base64.b64decode(blob.encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise DecryptionError("ciphertext is not valid base64") from exc

    if decoded.startswith(_MAGIC):
        if len(decoded) < _HEADER_LEN:
            raise DecryptionError("versioned ciphertext too short for header")
        return decoded[_MAGIC_LEN]
    return 0


def parse_kek_versions(raw: str) -> dict[int, str]:
    """Parse a `BYOK_KEK_VERSIONS` env string into a registry dict.

    Format: comma-separated `version:base64key` pairs, e.g.
    `"1:AAAA...=,2:BBBB...="`. Whitespace around tokens is tolerated.
    Empty / whitespace-only input produces an empty registry, which is the
    expected state when `current_version == 0`.

    Raises `RuntimeError` on any malformed token, duplicate version, or
    KEK that does not decode to exactly 32 bytes. Boot-time validation
    lives in `Settings.assert_prod_safe()`; this helper is the single
    parser shared by tests and runtime so both see the same error
    messages.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}

    registry: dict[int, str] = {}
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        if ":" not in token:
            raise RuntimeError(
                "BYOK_KEK_VERSIONS entries must be 'version:base64key' "
                f"(got {token!r})"
            )
        version_str, kek_b64 = token.split(":", 1)
        version_str = version_str.strip()
        kek_b64 = kek_b64.strip()
        try:
            version = int(version_str)
        except ValueError as exc:
            raise RuntimeError(
                f"BYOK_KEK_VERSIONS version must be an integer (got {version_str!r})"
            ) from exc
        if version < 1 or version > _MAX_KEK_VERSION:
            raise RuntimeError(
                f"BYOK_KEK_VERSIONS version must be in [1, {_MAX_KEK_VERSION}] "
                f"(got {version})"
            )
        if version in registry:
            raise RuntimeError(
                f"BYOK_KEK_VERSIONS has duplicate version {version}"
            )
        # Validate KEK shape eagerly -- the boot-time `assert_prod_safe()`
        # call relies on this raising a clear `RuntimeError`.
        decode_kek(kek_b64)
        registry[version] = kek_b64
    return registry


def register_kek(
    cipher: VersionedCipher, version: int, kek_b64: str
) -> VersionedCipher:
    """Return a new `VersionedCipher` with `version` mapped to `kek_b64`.

    Test helper. Builds the new `AeadCipher` via `get_cipher` so it shares
    the module-level cache. Frozen dataclass -> return a fresh instance
    rather than mutating; the caller swaps their reference. Existing
    registry entries are preserved (this is additive, matching the
    "rotate-in-new-version" production flow).
    """
    if version < 1 or version > _MAX_KEK_VERSION:
        raise RuntimeError(
            f"KEK version must be in [1, {_MAX_KEK_VERSION}] (got {version})"
        )
    new_registry = dict(cipher.registry)
    new_registry[version] = get_cipher(kek_b64)
    return VersionedCipher(
        legacy=cipher.legacy,
        registry=new_registry,
        current_version=cipher.current_version,
    )
