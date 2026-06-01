"""Bounded attachment text extraction.

The upload path is transient-only: callers pass request bytes in, receive a
short transcript back, and persist neither raw bytes nor extracted text.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterable
from typing import Literal

AttachmentMediaType = Literal["image", "pdf", "text"]

IMAGE_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}

TEXT_MIME_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/yaml",
    "text/csv",
    "text/markdown",
    "text/plain",
    "text/tab-separated-values",
    "text/xml",
    "text/x-log",
}

MAX_EXTRACTED_TEXT_CHARS = 20_000
_MAX_PDF_SCAN_BYTES = 2 * 1024 * 1024
_MAX_PDF_INFLATED_BYTES = 512 * 1024
_MAX_PDF_STREAMS = 64


def is_supported_attachment_type(
    media_type: AttachmentMediaType,
    mime_type: str,
) -> bool:
    """Return whether the declared attachment type is accepted."""
    if media_type == "image":
        return mime_type in IMAGE_MIME_TYPES
    if media_type == "pdf":
        return mime_type == "application/pdf"
    if media_type == "text":
        return mime_type.startswith("text/") or mime_type in TEXT_MIME_TYPES
    return False


def extract_attachment_text(
    *,
    media_type: AttachmentMediaType,
    mime_type: str,
    data: bytes,
    max_chars: int = MAX_EXTRACTED_TEXT_CHARS,
) -> str | None:
    """Extract bounded text from supported document payloads where practical."""
    if max_chars < 1:
        return None
    if media_type == "text":
        return _extract_plain_text(data, max_chars=max_chars)
    if media_type == "pdf":
        return _extract_pdf_text(data, max_chars=max_chars)
    return None


def _normalize_text(text: str, *, max_chars: int) -> str | None:
    normalized = re.sub(r"[ \t\f\v]+", " ", text.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return None
    return normalized[:max_chars]


def _extract_plain_text(data: bytes, *, max_chars: int) -> str | None:
    # Binary guard: declared text files should not contain embedded NULs.
    if data.count(b"\x00") > max(1, len(data) // 100):
        return None

    sample = data[: max_chars * 4]
    encodings = ["utf-8-sig"]
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")

    for encoding in encodings:
        try:
            return _normalize_text(sample.decode(encoding), max_chars=max_chars)
        except UnicodeDecodeError:
            continue
    return None


def _extract_pdf_text(data: bytes, *, max_chars: int) -> str | None:
    if b"%PDF-" not in data[:1024]:
        return None

    chunks: list[str] = []
    for stream in _pdf_streams(data[:_MAX_PDF_SCAN_BYTES]):
        for candidate in _inflate_candidates(stream):
            chunks.extend(_pdf_text_strings(candidate))
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                return _normalize_text("\n".join(chunks), max_chars=max_chars)
    return _normalize_text("\n".join(chunks), max_chars=max_chars)


def _pdf_streams(data: bytes) -> Iterable[bytes]:
    for count, match in enumerate(
        re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S),
        start=1,
    ):
        yield match.group(1)
        if count >= _MAX_PDF_STREAMS:
            return


def _inflate_candidates(stream: bytes) -> Iterable[bytes]:
    yield stream
    try:
        decompressor = zlib.decompressobj()
        inflated = decompressor.decompress(
            stream.strip(),
            max_length=_MAX_PDF_INFLATED_BYTES,
        )
        if inflated:
            yield inflated
    except zlib.error:
        return


def _pdf_text_strings(data: bytes) -> list[str]:
    text: list[str] = []
    for raw in re.findall(rb"\((?:\\.|[^\\()])*\)", data):
        decoded = _decode_pdf_literal(raw[1:-1])
        if decoded:
            text.append(decoded)
    for raw_hex in re.findall(rb"<([0-9A-Fa-f\s]{4,})>", data):
        decoded_hex = _decode_pdf_hex(raw_hex)
        if decoded_hex:
            text.append(decoded_hex)
    return text


def _decode_pdf_literal(raw: bytes) -> str | None:
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b != 0x5C:  # backslash
            out.append(b)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        esc = raw[i]
        i += 1
        escapes = {
            ord("n"): ord("\n"),
            ord("r"): ord("\n"),
            ord("t"): ord("\t"),
            ord("b"): ord("\b"),
            ord("f"): ord("\f"),
            ord("("): ord("("),
            ord(")"): ord(")"),
            ord("\\"): ord("\\"),
        }
        if esc in escapes:
            out.append(escapes[esc])
        elif 48 <= esc <= 55:
            octal = bytes([esc])
            for _ in range(2):
                if i < len(raw) and 48 <= raw[i] <= 55:
                    octal += bytes([raw[i]])
                    i += 1
            out.append(int(octal, 8))
        elif esc in (10, 13):
            if esc == 13 and i < len(raw) and raw[i] == 10:
                i += 1
        else:
            out.append(esc)
    return _decode_pdf_bytes(bytes(out))


def _decode_pdf_hex(raw_hex: bytes) -> str | None:
    compact = re.sub(rb"\s+", b"", raw_hex)
    if len(compact) % 2 == 1:
        compact += b"0"
    try:
        return _decode_pdf_bytes(bytes.fromhex(compact.decode("ascii")))
    except ValueError:
        return None


def _decode_pdf_bytes(raw: bytes) -> str | None:
    if not raw:
        return None
    if raw.startswith((b"\xfe\xff", b"\xff\xfe")):
        encodings = ["utf-16"]
    elif raw[::2].count(0) > max(1, len(raw) // 4):
        encodings = ["utf-16-be", "latin-1"]
    else:
        encodings = ["utf-8", "latin-1"]
    for encoding in encodings:
        try:
            decoded = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        cleaned = decoded.strip()
        if cleaned:
            return cleaned
    return None
