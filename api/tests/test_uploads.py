from __future__ import annotations

import zlib

from app.uploads import (
    _MAX_PDF_INFLATED_BYTES,
    _inflate_candidates,
    extract_attachment_text,
    is_supported_attachment_type,
)


def test_plain_text_extraction_is_bounded() -> None:
    text = extract_attachment_text(
        media_type="text",
        mime_type="text/plain",
        data=("alpha " * 100).encode("utf-8"),
        max_chars=20,
    )

    assert text == "alpha alpha alpha al"


def test_binary_disguised_as_text_is_not_extracted() -> None:
    text = extract_attachment_text(
        media_type="text",
        mime_type="text/plain",
        data=b"a\x00b\x00c\x00d\x00",
    )

    assert text is None


def test_simple_flate_pdf_text_extraction() -> None:
    stream = zlib.compress(b"BT /F1 12 Tf 72 720 Td (Hello PDF notes) Tj ET")
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Length 999 /Filter /FlateDecode >> stream\n"
        + stream
        + b"\nendstream endobj\n%%EOF"
    )

    text = extract_attachment_text(
        media_type="pdf",
        mime_type="application/pdf",
        data=pdf,
    )

    assert text == "Hello PDF notes"


def test_pdf_flate_stream_inflation_is_capped() -> None:
    compressed = zlib.compress(b"(A)" * (_MAX_PDF_INFLATED_BYTES + 1024))

    candidates = list(_inflate_candidates(compressed))

    assert len(candidates) == 2
    assert candidates[0] == compressed
    assert len(candidates[1]) == _MAX_PDF_INFLATED_BYTES


def test_supported_attachment_type_matrix() -> None:
    assert is_supported_attachment_type("image", "image/png") is True
    assert is_supported_attachment_type("image", "image/jpeg") is True
    assert is_supported_attachment_type("pdf", "application/pdf") is True
    assert is_supported_attachment_type("text", "text/markdown") is True
    assert is_supported_attachment_type("text", "application/json") is True
    assert is_supported_attachment_type("image", "image/svg+xml") is False
    assert is_supported_attachment_type("pdf", "text/plain") is False
