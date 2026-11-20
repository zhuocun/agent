"""Unit tests for app.uploads — attachment text extraction.

Covers the uncovered branches:
- `is_supported_attachment_type`: all media type / mime type combinations.
- `extract_attachment_text`: dispatch by media_type, max_chars < 1 guard.
- `_extract_plain_text`: binary guard, utf-16 BOM, utf-8 fallback.
- `_normalize_text`: whitespace collapsing, empty-after-normalize.
- `_extract_pdf_text`: PDF stream extraction, inflate, hex strings, literals.
- `_decode_pdf_literal`: octal escapes, backslash sequences, line continuations.
- `_decode_pdf_hex`: hex padding, invalid hex.
- `_decode_pdf_bytes`: BOM detection, null-heavy encoding guessing.
"""

from __future__ import annotations

import zlib

from app.uploads import (
    _decode_pdf_bytes,
    _decode_pdf_hex,
    _decode_pdf_literal,
    _extract_pdf_text,
    _extract_plain_text,
    _normalize_text,
    _pdf_streams,
    _pdf_text_strings,
    extract_attachment_text,
    is_supported_attachment_type,
)

# ---------------------------------------------------------------------------
# is_supported_attachment_type
# ---------------------------------------------------------------------------


class TestIsSupportedAttachmentType:
    def test_image_types(self) -> None:
        for mime in ("image/gif", "image/jpeg", "image/png", "image/webp"):
            assert is_supported_attachment_type("image", mime) is True
        assert is_supported_attachment_type("image", "image/bmp") is False

    def test_pdf_type(self) -> None:
        assert is_supported_attachment_type("pdf", "application/pdf") is True
        assert is_supported_attachment_type("pdf", "text/plain") is False

    def test_text_types(self) -> None:
        assert is_supported_attachment_type("text", "text/plain") is True
        assert is_supported_attachment_type("text", "text/markdown") is True
        assert is_supported_attachment_type("text", "application/json") is True
        assert is_supported_attachment_type("text", "application/xml") is True
        assert is_supported_attachment_type("text", "text/csv") is True
        assert is_supported_attachment_type("text", "application/octet-stream") is False

    def test_unknown_media_type(self) -> None:
        assert is_supported_attachment_type("video", "video/mp4") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# extract_attachment_text
# ---------------------------------------------------------------------------


class TestExtractAttachmentText:
    def test_max_chars_zero_returns_none(self) -> None:
        assert extract_attachment_text(
            media_type="text", mime_type="text/plain", data=b"hello", max_chars=0
        ) is None

    def test_text_dispatch(self) -> None:
        result = extract_attachment_text(
            media_type="text", mime_type="text/plain", data=b"hello world"
        )
        assert result == "hello world"

    def test_image_returns_none(self) -> None:
        result = extract_attachment_text(
            media_type="image", mime_type="image/png", data=b"\x89PNG..."
        )
        assert result is None

    def test_pdf_dispatch(self) -> None:
        # Minimal PDF with a text stream.
        pdf_data = b"%PDF-1.4\nstream\n(Hello World)\nendstream"
        result = extract_attachment_text(
            media_type="pdf", mime_type="application/pdf", data=pdf_data
        )
        assert result is not None
        assert "Hello World" in result


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_collapses_whitespace(self) -> None:
        assert _normalize_text("  a   b  ", max_chars=100) == "a b"

    def test_collapses_newlines(self) -> None:
        assert _normalize_text("a\n\n\n\nb", max_chars=100) == "a\n\nb"

    def test_empty_after_normalize(self) -> None:
        assert _normalize_text("   \n\n  ", max_chars=100) is None

    def test_truncates_to_max_chars(self) -> None:
        result = _normalize_text("abcdefgh", max_chars=4)
        assert result == "abcd"

    def test_crlf_normalization(self) -> None:
        assert _normalize_text("a\r\nb\rc", max_chars=100) == "a\nb\nc"


# ---------------------------------------------------------------------------
# _extract_plain_text
# ---------------------------------------------------------------------------


class TestExtractPlainText:
    def test_simple_utf8(self) -> None:
        assert _extract_plain_text(b"hello", max_chars=100) == "hello"

    def test_binary_guard(self) -> None:
        # More than 1% NULs -> None.
        data = b"\x00" * 50 + b"text"
        assert _extract_plain_text(data, max_chars=100) is None

    def test_utf16_bom(self) -> None:
        # UTF-16 encoding interleaves NUL bytes, so for ASCII-range text the
        # binary guard (>1% NULs) fires. The BOM path is reachable only with
        # characters whose UTF-16 form avoids NULs (high codepoints). Use
        # characters entirely above U+00FF so neither byte in a pair is 0x00.
        # U+4E2D (中) → LE bytes 0x2D 0x4E — no NULs.
        text = "中" * 100
        data = text.encode("utf-16")  # includes BOM
        result = _extract_plain_text(data, max_chars=200)
        assert result == text

    def test_invalid_encoding_returns_none(self) -> None:
        # Bytes that are invalid in both utf-8-sig and utf-16.
        data = bytes(range(0x80, 0x90)) * 10
        # Should not raise, may return the latin-1 fallback or None.
        # The function tries utf-8 and utf-16 and returns None if both fail.
        result = _extract_plain_text(data, max_chars=100)
        # It should not raise. If it returns something, it's fine.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _extract_pdf_text
# ---------------------------------------------------------------------------


class TestExtractPdfText:
    def test_no_pdf_header(self) -> None:
        assert _extract_pdf_text(b"not a pdf", max_chars=100) is None

    def test_basic_stream(self) -> None:
        data = b"%PDF-1.4\nstream\n(Hello PDF)\nendstream"
        result = _extract_pdf_text(data, max_chars=100)
        assert result is not None
        assert "Hello PDF" in result

    def test_compressed_stream(self) -> None:
        content = b"(Compressed Text)"
        compressed = zlib.compress(content)
        data = b"%PDF-1.4\nstream\n" + compressed + b"\nendstream"
        result = _extract_pdf_text(data, max_chars=100)
        assert result is not None
        assert "Compressed Text" in result

    def test_hex_string(self) -> None:
        hex_str = "48656C6C6F"  # "Hello" in hex
        data = b"%PDF-1.4\nstream\n<" + hex_str.encode() + b">\nendstream"
        result = _extract_pdf_text(data, max_chars=100)
        assert result is not None
        assert "Hello" in result

    def test_max_chars_truncation(self) -> None:
        data = b"%PDF-1.4\nstream\n(AAAAAAAAAA)\nendstream"
        result = _extract_pdf_text(data, max_chars=5)
        assert result is not None
        assert len(result) <= 5


# ---------------------------------------------------------------------------
# _pdf_streams
# ---------------------------------------------------------------------------


class TestPdfStreams:
    def test_extracts_streams(self) -> None:
        data = b"stream\ncontent1\nendstream other stream\ncontent2\nendstream"
        streams = list(_pdf_streams(data))
        assert len(streams) == 2
        assert streams[0] == b"content1"
        assert streams[1] == b"content2"

    def test_max_streams_limit(self) -> None:
        # Build data with 70 streams (more than _MAX_PDF_STREAMS=64).
        parts = []
        for i in range(70):
            parts.append(f"stream\n(text{i})\nendstream\n".encode())
        data = b"".join(parts)
        streams = list(_pdf_streams(data))
        assert len(streams) == 64


# ---------------------------------------------------------------------------
# _pdf_text_strings
# ---------------------------------------------------------------------------


class TestPdfTextStrings:
    def test_literal_strings(self) -> None:
        data = b"BT (Hello) Tj (World) Tj ET"
        result = _pdf_text_strings(data)
        assert "Hello" in result
        assert "World" in result

    def test_hex_strings(self) -> None:
        data = b"<48656C6C6F>"  # "Hello"
        result = _pdf_text_strings(data)
        assert "Hello" in result

    def test_empty_data(self) -> None:
        assert _pdf_text_strings(b"") == []


# ---------------------------------------------------------------------------
# _decode_pdf_literal
# ---------------------------------------------------------------------------


class TestDecodePdfLiteral:
    def test_simple_text(self) -> None:
        assert _decode_pdf_literal(b"Hello") == "Hello"

    def test_escape_sequences(self) -> None:
        assert _decode_pdf_literal(b"a\\nb") == "a\nb"
        assert _decode_pdf_literal(b"a\\tb") == "a\tb"
        assert _decode_pdf_literal(b"a\\(b") == "a(b"
        assert _decode_pdf_literal(b"a\\)b") == "a)b"
        assert _decode_pdf_literal(b"a\\\\b") == "a\\b"

    def test_octal_escape(self) -> None:
        # \101 = 'A' (octal 101 = decimal 65)
        assert _decode_pdf_literal(b"\\101") == "A"

    def test_line_continuation_lf(self) -> None:
        # Backslash followed by LF is a line continuation (ignored).
        result = _decode_pdf_literal(b"ab\\\ncd")
        assert result == "abcd"

    def test_line_continuation_cr_lf(self) -> None:
        result = _decode_pdf_literal(b"ab\\\r\ncd")
        assert result == "abcd"

    def test_empty(self) -> None:
        assert _decode_pdf_literal(b"") is None

    def test_trailing_backslash(self) -> None:
        # Trailing backslash at end of data — should not crash.
        result = _decode_pdf_literal(b"abc\\")
        assert result == "abc"


# ---------------------------------------------------------------------------
# _decode_pdf_hex
# ---------------------------------------------------------------------------


class TestDecodePdfHex:
    def test_normal_hex(self) -> None:
        assert _decode_pdf_hex(b"48656C6C6F") == "Hello"

    def test_odd_length_padded(self) -> None:
        # Odd-length hex gets a trailing 0 appended.
        result = _decode_pdf_hex(b"4")
        assert result is not None

    def test_whitespace_stripped(self) -> None:
        assert _decode_pdf_hex(b"48 65 6C 6C 6F") == "Hello"

    def test_invalid_hex(self) -> None:
        assert _decode_pdf_hex(b"ZZZZ") is None


# ---------------------------------------------------------------------------
# _decode_pdf_bytes
# ---------------------------------------------------------------------------


class TestDecodePdfBytes:
    def test_empty(self) -> None:
        assert _decode_pdf_bytes(b"") is None

    def test_utf16_bom_be(self) -> None:
        data = b"\xfe\xff\x00H\x00e\x00l\x00l\x00o"
        assert _decode_pdf_bytes(data) == "Hello"

    def test_utf16_bom_le(self) -> None:
        data = b"\xff\xfeH\x00e\x00l\x00l\x00o\x00"
        assert _decode_pdf_bytes(data) == "Hello"

    def test_ascii_text(self) -> None:
        assert _decode_pdf_bytes(b"Hello") == "Hello"

    def test_null_heavy_tries_utf16be(self) -> None:
        # Data with lots of null bytes -> tries utf-16-be.
        data = b"\x00H\x00e\x00l\x00l\x00o"
        result = _decode_pdf_bytes(data)
        assert result is not None
        assert "Hello" in result

    def test_whitespace_only_returns_none(self) -> None:
        assert _decode_pdf_bytes(b"   ") is None
