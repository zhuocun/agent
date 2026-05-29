"""Versioned-KEK rotation tests for `app.security.crypto`.

These cover the M4 Post-hardening seam: legacy single-KEK rows must keep
decrypting after rotation, the new versioned format must round-trip end-to-end
at v1 and after rotating to v2, and the magic-prefix dispatch must fail-loud
on a magic-present payload that hits an unknown version. The tests build their
own `VersionedCipher` instances rather than depending on `get_settings()` so
they don't poison the process-wide settings cache.
"""

from __future__ import annotations

import base64
import os
import re

import pytest

from app.security.crypto import (
    _MAGIC,
    AeadCipher,
    DecryptionError,
    VersionedCipher,
    decrypt,
    encrypt,
    get_cipher,
    parse_kek_versions,
    register_kek,
)


def _make_kek_b64() -> str:
    """Return a fresh, valid 32-byte KEK in base64."""
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _legacy_cipher() -> tuple[VersionedCipher, str]:
    """Build a `VersionedCipher` in `current_version == 0` (legacy) mode."""
    legacy_kek = _make_kek_b64()
    return (
        VersionedCipher(
            legacy=get_cipher(legacy_kek),
            registry={},
            current_version=0,
        ),
        legacy_kek,
    )


def _v1_cipher() -> tuple[VersionedCipher, str, str]:
    """Build a `VersionedCipher` in `current_version == 1` mode.

    Returns the cipher plus both KEKs so tests can recheck the format by
    hand if they want.
    """
    legacy_kek = _make_kek_b64()
    v1_kek = _make_kek_b64()
    cipher = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(v1_kek)},
        current_version=1,
    )
    return cipher, legacy_kek, v1_kek


def test_legacy_roundtrip_uses_unversioned_format() -> None:
    """`current_version=0` must produce bit-for-bit legacy ciphertext.

    A v0 write must not carry the magic prefix, so a deployment that has
    not opted into rotation keeps writing the exact same on-disk shape as
    before the seam landed.
    """
    cipher, _ = _legacy_cipher()
    ct_b64 = cipher.encrypt("sk-legacy-12345")
    blob = base64.b64decode(ct_b64)
    assert not blob.startswith(_MAGIC), "legacy writes must not carry magic prefix"
    assert cipher.decrypt(ct_b64) == "sk-legacy-12345"


def test_v1_roundtrip_uses_versioned_format() -> None:
    """`current_version=1` writes carry magic + version byte 1."""
    cipher, _, _ = _v1_cipher()
    ct_b64 = cipher.encrypt("sk-v1-12345")
    blob = base64.b64decode(ct_b64)
    assert blob.startswith(_MAGIC), "v1 writes must carry magic prefix"
    assert blob[len(_MAGIC)] == 1, "version byte must equal 1"
    assert cipher.decrypt(ct_b64) == "sk-v1-12345"


def test_rotation_to_v2_decrypts_old_v1_and_writes_v2() -> None:
    """After rotating to v2, old v1 ciphertexts decrypt and new writes pin v2.

    Critical path for KEK rotation: an operator adds version 2 to the
    registry and bumps `current_version` -> the v1 KEK stays in the
    registry, so historical rows keep decrypting, and new BYOK writes
    pick up v2 without a rewrite pass.
    """
    legacy_kek = _make_kek_b64()
    v1_kek = _make_kek_b64()
    v2_kek = _make_kek_b64()

    # First the v1 cipher writes a row.
    v1_cipher = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(v1_kek)},
        current_version=1,
    )
    v1_ct = v1_cipher.encrypt("rotate-me")

    # Operator rotates: same legacy + v1 KEK, plus v2 KEK, current=2.
    v2_cipher = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(v1_kek), 2: get_cipher(v2_kek)},
        current_version=2,
    )

    # Old v1 ciphertext still decrypts via the registry.
    assert v2_cipher.decrypt(v1_ct) == "rotate-me"

    # New writes pin v2.
    new_ct = v2_cipher.encrypt("new-write")
    blob = base64.b64decode(new_ct)
    assert blob.startswith(_MAGIC)
    assert blob[len(_MAGIC)] == 2
    assert v2_cipher.decrypt(new_ct) == "new-write"


def test_rotation_legacy_row_still_decrypts_after_moving_to_v1() -> None:
    """Rows written under the legacy format keep decrypting after rotation.

    The whole point of the seam: an operator rotates without rewriting
    historical rows, so the legacy KEK must remain on the cipher as the
    fall-through path for magic-absent ciphertexts.
    """
    legacy_kek = _make_kek_b64()
    v1_kek = _make_kek_b64()

    legacy = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={},
        current_version=0,
    )
    legacy_ct = legacy.encrypt("old-row")

    rotated = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(v1_kek)},
        current_version=1,
    )
    assert rotated.decrypt(legacy_ct) == "old-row"


def test_versioned_ciphertext_with_unknown_version_raises() -> None:
    """A magic-present payload with an unknown version is a hard error.

    No silent fall-through to legacy: the operator either lost a KEK or
    we are looking at corrupted data, both of which are loud failures.
    """
    cipher, _, _ = _v1_cipher()
    # Build a payload with magic + version 99 + plausible nonce + tag bytes.
    blob = _MAGIC + bytes([99]) + os.urandom(12) + os.urandom(16)
    fake_b64 = base64.b64encode(blob).decode("ascii")
    with pytest.raises(DecryptionError, match=re.escape("no KEK registered")):
        cipher.decrypt(fake_b64)


def test_magic_prefix_on_corrupted_legacy_does_not_fall_back() -> None:
    """A garbage payload that happens to start with magic must fail-loud.

    Probabilistically negligible (~2^-32 false match on a random legacy
    nonce) but the failure path must still raise `DecryptionError`
    rather than silently retrying as legacy -- otherwise we'd paper over
    a real corruption event.
    """
    cipher, _, _ = _v1_cipher()
    # Magic + an unregistered version: the dispatch goes into the
    # versioned path and stays there.
    garbage = _MAGIC + bytes([2]) + os.urandom(12) + os.urandom(16)
    with pytest.raises(DecryptionError):
        cipher.decrypt(base64.b64encode(garbage).decode("ascii"))


def test_versioned_payload_with_wrong_kek_in_registry_raises() -> None:
    """A v1 row decrypted against a registry whose v1 KEK is a different
    key produces a `DecryptionError`, not a silent garbage decrypt."""
    legacy_kek = _make_kek_b64()
    real_v1 = _make_kek_b64()
    wrong_v1 = _make_kek_b64()

    writer = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(real_v1)},
        current_version=1,
    )
    ct = writer.encrypt("secret")

    reader = VersionedCipher(
        legacy=get_cipher(legacy_kek),
        registry={1: get_cipher(wrong_v1)},
        current_version=1,
    )
    with pytest.raises(DecryptionError):
        reader.decrypt(ct)


def test_versioned_ciphertext_too_short_raises() -> None:
    """Magic prefix but truncated header / body must raise."""
    cipher, _, _ = _v1_cipher()
    # Just the magic, no version byte.
    too_short = base64.b64encode(_MAGIC).decode("ascii")
    with pytest.raises(DecryptionError, match="too short"):
        cipher.decrypt(too_short)


def test_v1_only_too_short_after_version_byte_raises() -> None:
    """Header present but no room for a nonce -> `DecryptionError`."""
    cipher, _, _ = _v1_cipher()
    short = _MAGIC + bytes([1]) + b"\x00" * 4  # 4 bytes, well below nonce length
    with pytest.raises(DecryptionError, match="too short"):
        cipher.decrypt(base64.b64encode(short).decode("ascii"))


def test_v1_decrypt_non_base64_raises() -> None:
    """Plain non-base64 input still surfaces as `DecryptionError`."""
    cipher, _, _ = _v1_cipher()
    with pytest.raises(DecryptionError, match="base64"):
        cipher.decrypt("!!!not-base64!!!")


def test_register_kek_returns_new_cipher_with_entry_added() -> None:
    """`register_kek` is additive and returns a fresh frozen instance."""
    base, _ = _legacy_cipher()
    new_kek = _make_kek_b64()
    rotated = register_kek(base, 1, new_kek)
    assert 1 in rotated.registry
    assert 1 not in base.registry  # original cipher is untouched
    # A v1 round-trip works once `current_version` is bumped.
    promoted = VersionedCipher(
        legacy=rotated.legacy,
        registry=rotated.registry,
        current_version=1,
    )
    ct = promoted.encrypt("hi")
    assert promoted.decrypt(ct) == "hi"


def test_register_kek_rejects_out_of_range_version() -> None:
    """Versions outside [1, 255] are refused so the on-disk byte never overflows."""
    base, _ = _legacy_cipher()
    with pytest.raises(RuntimeError, match="version must be in"):
        register_kek(base, 0, _make_kek_b64())
    with pytest.raises(RuntimeError, match="version must be in"):
        register_kek(base, 256, _make_kek_b64())


def test_aead_cipher_still_round_trips_independently() -> None:
    """`AeadCipher` is unchanged: builds + roundtrips without the version seam."""
    kek = _make_kek_b64()
    cipher = AeadCipher.from_kek_base64(kek)
    ct = cipher.encrypt("standalone")
    assert cipher.decrypt(ct) == "standalone"


# -- parse_kek_versions ---------------------------------------------------


def test_parse_empty_registry() -> None:
    assert parse_kek_versions("") == {}
    assert parse_kek_versions("   ") == {}


def test_parse_single_entry() -> None:
    k = _make_kek_b64()
    assert parse_kek_versions(f"1:{k}") == {1: k}


def test_parse_multiple_entries_with_whitespace() -> None:
    k1, k2 = _make_kek_b64(), _make_kek_b64()
    raw = f" 1 : {k1} , 2 : {k2} "
    parsed = parse_kek_versions(raw)
    assert parsed == {1: k1, 2: k2}


def test_parse_rejects_missing_colon() -> None:
    with pytest.raises(RuntimeError, match="must be 'version:base64key'"):
        parse_kek_versions("1=AAAA")


def test_parse_rejects_non_integer_version() -> None:
    with pytest.raises(RuntimeError, match="must be an integer"):
        parse_kek_versions(f"x:{_make_kek_b64()}")


def test_parse_rejects_zero_version() -> None:
    """`0` is reserved for the legacy single-KEK path."""
    with pytest.raises(RuntimeError, match="must be in"):
        parse_kek_versions(f"0:{_make_kek_b64()}")


def test_parse_rejects_oversize_version() -> None:
    with pytest.raises(RuntimeError, match="must be in"):
        parse_kek_versions(f"256:{_make_kek_b64()}")


def test_parse_rejects_duplicate_version() -> None:
    k1, k2 = _make_kek_b64(), _make_kek_b64()
    with pytest.raises(RuntimeError, match="duplicate"):
        parse_kek_versions(f"1:{k1},1:{k2}")


def test_parse_rejects_wrong_length_kek() -> None:
    short = base64.b64encode(b"\x00" * 16).decode("ascii")
    with pytest.raises(RuntimeError, match="32 bytes"):
        parse_kek_versions(f"1:{short}")


# -- Module-level helpers --------------------------------------------------


@pytest.fixture
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset `get_settings` cache so per-test env tweaks land cleanly."""
    from app.config import get_settings

    get_settings.cache_clear()
    # `conftest.py` sets COOKIE_SECURE etc. at process start; we don't
    # touch those here, only the BYOK envs.


def test_module_encrypt_legacy_when_current_version_is_zero(
    monkeypatch: pytest.MonkeyPatch, reset_settings: None
) -> None:
    """Module-level `encrypt` defaults to legacy format when settings haven't
    opted into rotation, matching the pre-seam behavior every existing call
    site relies on."""
    monkeypatch.setenv("BYOK_KEK_VERSIONS", "")
    monkeypatch.setenv("BYOK_CURRENT_KEK_VERSION", "0")
    from app.config import get_settings

    get_settings.cache_clear()

    kek = _make_kek_b64()
    ct = encrypt("legacy", kek)
    # Round-trip through the same helper.
    assert decrypt(ct, kek) == "legacy"
    # And no magic prefix on the blob.
    blob = base64.b64decode(ct)
    assert not blob.startswith(_MAGIC)


def test_module_encrypt_versioned_when_current_version_set(
    monkeypatch: pytest.MonkeyPatch, reset_settings: None
) -> None:
    """With `BYOK_CURRENT_KEK_VERSION=1` and a registry entry, the module
    helper writes the versioned format and decrypts it round-trip."""
    legacy_kek = _make_kek_b64()
    v1_kek = _make_kek_b64()
    monkeypatch.setenv("BYOK_ENCRYPTION_KEK", legacy_kek)
    monkeypatch.setenv("BYOK_KEK_VERSIONS", f"1:{v1_kek}")
    monkeypatch.setenv("BYOK_CURRENT_KEK_VERSION", "1")
    from app.config import get_settings

    get_settings.cache_clear()

    ct = encrypt("v1-row", legacy_kek)
    blob = base64.b64decode(ct)
    assert blob.startswith(_MAGIC)
    assert blob[len(_MAGIC)] == 1
    assert decrypt(ct, legacy_kek) == "v1-row"
    # Clear so the rest of the suite sees the conftest defaults.
    get_settings.cache_clear()
