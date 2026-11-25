#!/usr/bin/env python3
"""Validate self-contained visual HTML documents with embedded inline SVGs.

Interpreter:
    Python 3.9+ (tested on Python 3.11 and 3.12).

Dependencies:
    Python 3 standard library only (zero external packages).

Usage:
    python3 check_visual_html.py [options] <html-file> [...]

Options:
    --min-wide-font FLOAT     Minimum SVG font size in px for wide/default SVGs
                              (default: 14.0).
    --min-narrow-font FLOAT   Minimum SVG font size in px for narrow SVGs
                              (class contains 'n' or 'narrow', or
                              data-layout="narrow"; default: 12.5).
    --max-section-chars INT   Maximum non-whitespace characters outside
                              <figure> in a <section> containing a <figure>,
                              when text is CJK-dominant (0 disables;
                              default: 220).
    --max-section-words INT   Maximum whitespace-separated words outside
                              <figure> in a <section> containing a <figure>,
                              when text is Latin-script-dominant (0 disables;
                              default: 65).
    --forbid TEXT             Forbidden/retired text checked across visible
                              HTML text, SVG <text> (with <tspan> merged), and
                              aria-label attributes (raw and whitespace-
                              stripped). Repeatable.
    --allow-external-assets   Opt out of offline single-file resource checks.
    --allow-foreign-object    Opt out of SVG <foreignObject> prohibition.
    --format text|json        Output format (default: text).

Exit codes:
    0  All checks passed for all input files.
    1  One or more validation failures were detected.
    2  CLI usage error or file I/O / decoding error.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import stat
import sys
from typing import Sequence

ALLOWED_XMLNS_URIS = frozenset(
    {
        "http://www.w3.org/2000/svg",
        "http://www.w3.org/1999/xlink",
        "http://www.w3.org/xml/1998/namespace",
    }
)

NAVIGATION_LINK_RELS = frozenset(
    {
        "canonical",
        "alternate",
        "author",
        "help",
        "license",
        "next",
        "prev",
        "bookmark",
        "search",
        "external",
        "noopener",
        "noreferrer",
    }
)

VOID_HTML_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

BLOCK_HTML_ELEMENTS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)

NON_RENDERING_SVG_CONTAINERS = frozenset(
    {
        "defs",
        "symbol",
        "marker",
        "pattern",
        "clippath",
        "mask",
        "filter",
    }
)

VISIBLE_SVG_ELEMENTS = frozenset(
    {
        "circle",
        "ellipse",
        "image",
        "line",
        "path",
        "polygon",
        "polyline",
        "rect",
        "text",
        "use",
    }
)

SVG_URL_REF_ATTRS = frozenset(
    {
        "clip-path",
        "cursor",
        "fill",
        "filter",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "shape-inside",
        "shape-subtract",
        "stroke",
    }
)

SVG_TYPE_SELECTOR_PATTERN = re.compile(
    r"(?:^|[\s>+~,(])(?:svg|text|tspan|textpath)(?=$|[\s>+~,).#:\[])",
    re.IGNORECASE,
)

NARROW_CLASS_PATTERN = re.compile(r"(?<!\\)\.(?:n|narrow)(?![\w-])", re.IGNORECASE)
WIDE_CLASS_PATTERN = re.compile(r"(?<!\\)\.(?:w|wide)(?![\w-])", re.IGNORECASE)
NARROW_ATTR_PATTERN = re.compile(
    r"""\[\s*data-layout\s*=\s*(?:"narrow"|'narrow'|narrow)\s*\]""",
    re.IGNORECASE,
)
WIDE_ATTR_PATTERN = re.compile(
    r"""\[\s*data-layout\s*=\s*(?:"wide"|'wide'|wide)\s*\]""",
    re.IGNORECASE,
)
JS_CLASS_PATTERN = re.compile(r"(?<!\\)\.js(?![\w-])")

CSS_REDUCED_MOTION_RE = re.compile(
    r"prefers-reduced-motion\s*:\s*reduce\b",
    re.IGNORECASE,
)
FONT_SIZE_VALUE_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(px|pt)?\s*(?:!important)?\s*$",
    re.IGNORECASE,
)
FONT_SHORTHAND_SIZE_RE = re.compile(
    r"(?:^|\s)([+-]?(?:\d+(?:\.\d+)?|\.\d+))(px|pt)(?=/|\s|$)",
    re.IGNORECASE,
)
DURATION_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(ms|s)?\s*(?:!important)?\s*$",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
IMPORTANT_RE = re.compile(r"!important\b", re.IGNORECASE)

_PSEUDO_ELEMENT_NAMES = frozenset(
    {"before", "after", "first-line", "first-letter", "selection", "marker", "placeholder"}
)
_MAX_SELECTOR_DEPTH = 16


@dataclass(frozen=True)
class CheckConfig:
    """Configuration options controlling validation thresholds and exemptions."""

    min_wide_font: float = 14.0
    min_narrow_font: float = 12.5
    max_section_chars: int = 220
    max_section_words: int = 65
    forbid: tuple[str, ...] = ()
    allow_external_assets: bool = False
    allow_foreign_object: bool = False


@dataclass(frozen=True)
class Failure:
    """Single actionable validation failure."""

    file: str
    location: str
    check: str
    problem: str
    expected: str
    fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "file": self.file,
            "location": self.location,
            "check": self.check,
            "problem": self.problem,
            "expected": self.expected,
            "fix": self.fix,
        }


@dataclass
class CssDeclaration:
    name: str
    value: str
    line: int
    important: bool = False


@dataclass
class CssRule:
    selectors: list[str]
    declarations: list[CssDeclaration]
    line: int
    in_reduced_motion: bool = False
    # True when the rule applies only under a condition: inside an at-rule block
    # (@media, @supports, @layer, @container) or a <style media="..."> element.
    conditional: bool = False
    # True when the rule sits inside an @layer block, at any depth. A layered
    # !important declaration beats an unlayered one, so the font-floor waiver
    # never clears a layered declaration.
    layered: bool = False


@dataclass
class CssParseResult:
    rules: list[CssRule] = field(default_factory=list)
    reduced_motion_rules: list[CssRule] = field(default_factory=list)
    has_reduced_motion_block: bool = False


@dataclass
class SvgInfo:
    index: int
    line: int
    attrs: dict[str, str]
    figure_index: int | None
    is_narrow: bool
    has_defs: bool = False
    has_visible_content: bool = False

    @property
    def is_hidden_defs_only(self) -> bool:
        return (
            self.attrs.get("aria-hidden", "").strip().lower() == "true"
            and self.has_defs
            and not self.has_visible_content
        )


@dataclass
class DomNode:
    tag: str
    attrs: dict[str, str]
    classes: frozenset[str]
    elem_id: str
    parent: DomNode | None
    sibling_index: int
    prev_sibling: DomNode | None
    svg_owner: SvgInfo | None
    in_non_render_svg: bool
    in_hidden: bool
    in_foreign_object: bool
    has_svg_text_descendant: bool = False


@dataclass
class SectionInfo:
    index: int
    line: int
    section_id: str
    has_figure: bool = False
    outside_chunks: list[str] = field(default_factory=list)


@dataclass
class TextBlock:
    location: str
    text: str


@dataclass(frozen=True)
class AttrCondition:
    name: str
    op: str  # "", "=", "~=", "|=", "^=", "$=", "*="
    value: str
    case_insensitive: bool = False


@dataclass
class CompoundSelector:
    tag: str | None = None  # None or "*" or lowercase tag name
    ids: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    attrs: list[AttrCondition] = field(default_factory=list)
    not_groups: list[list[ParsedSelector]] = field(default_factory=list)
    any_groups: list[list[ParsedSelector]] = field(default_factory=list)  # :is / :where
    pseudo_classes: list[str] = field(default_factory=list)
    has_pseudo_element: bool = False
    specificity: tuple[int, int, int] = (0, 0, 0)


@dataclass
class ParsedSelector:
    # Sequence from left to right: compounds[0] (combinators[0]) compounds[1] ...
    compounds: list[CompoundSelector]
    combinators: list[str]  # length == len(compounds) - 1; each in {" ", ">", "+", "~"}
    specificity: tuple[int, int, int]
    has_pseudo_element: bool

    @property
    def is_universal_element(self) -> bool:
        if self.has_pseudo_element or len(self.compounds) != 1:
            return False
        c = self.compounds[0]
        return (
            c.tag in (None, "*")
            and not c.ids
            and not c.classes
            and not c.attrs
            and not c.not_groups
            and not c.any_groups
            and not c.pseudo_classes
        )


def is_external_resource_url(url: str) -> bool:
    """Return True if a resource URL references an out-of-file dependency.

    Allows empty strings, same-document #fragments, inline data: URIs,
    about:blank, and standard XML namespace URIs. Rejects both remote URLs
    (http://, https://, //) and relative/local file dependencies.
    """
    cleaned = url.strip()
    if not cleaned:
        return False
    lower = cleaned.lower()
    if lower in ALLOWED_XMLNS_URIS:
        return False
    if lower.startswith("#") or lower.startswith("data:") or lower == "about:blank":
        return False
    return True


def parse_srcset_urls(srcset: str) -> list[str]:
    """Parse candidate URLs from an HTML srcset attribute per HTML5 rules.

    Correctly handles both descriptor-bearing and descriptorless data: URLs
    (which contain internal commas), as well as standard relative/remote URLs.
    """
    urls: list[str] = []
    i = 0
    n = len(srcset)
    while i < n:
        while i < n and (srcset[i].isspace() or srcset[i] == ","):
            i += 1
        if i >= n:
            break

        start = i
        if srcset[i : i + 5].lower() == "data:":
            # Per HTML5 srcset spec, read non-whitespace token.
            # If it ends with a comma, that comma terminates this candidate (no descriptor).
            while i < n and not srcset[i].isspace():
                i += 1
            raw_url = srcset[start:i]
            if raw_url.endswith(","):
                candidate = raw_url.rstrip(",")
                if candidate:
                    urls.append(candidate)
                continue
            if raw_url:
                urls.append(raw_url)
        else:
            while i < n and not srcset[i].isspace() and srcset[i] != ",":
                i += 1
            candidate = srcset[start:i]
            if candidate:
                urls.append(candidate)
            if i < n and srcset[i] == ",":
                i += 1
                continue

        # Skip optional descriptor up to the next comma outside parentheses.
        paren_depth = 0
        while i < n:
            ch = srcset[i]
            if ch == "(":
                paren_depth += 1
            elif ch == ")" and paren_depth > 0:
                paren_depth -= 1
            elif ch == "," and paren_depth == 0:
                i += 1
                break
            i += 1
    return urls


def is_cjk_letter(ch: str) -> bool:
    """Return True for CJK letters/ideographs (including halfwidth kana), excluding punctuation."""
    if not ch.isalpha():
        return False
    code = ord(ch)
    return (
        0x3040 <= code <= 0x30FF  # Hiragana & Katakana letters
        or 0x3100 <= code <= 0x312F  # Bopomofo
        or 0x3130 <= code <= 0x318F  # Hangul Compatibility Jamo
        or 0x31A0 <= code <= 0x31BF  # Bopomofo Extended
        or 0x31F0 <= code <= 0x31FF  # Katakana Phonetic Extensions
        or 0x3400 <= code <= 0x4DBF  # CJK Unified Ideographs Extension A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0xAC00 <= code <= 0xD7AF  # Hangul Syllables
        or 0x1100 <= code <= 0x11FF  # Hangul Jamo
        or 0xF900 <= code <= 0xFAFF  # CJK Compatibility Ideographs
        or 0xFF66 <= code <= 0xFF9F  # Halfwidth Katakana
        or 0xFFA0 <= code <= 0xFFDC  # Halfwidth Hangul
        or 0x20000 <= code <= 0x323AF  # CJK Extensions B-G
    )


def strip_css_comments(css: str) -> str:
    """Remove CSS /* ... */ comments outside quoted strings while preserving line numbers."""
    out: list[str] = []
    i = 0
    n = len(css)
    quote: str | None = None
    while i < n:
        ch = css[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                out.append(css[i])
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and css[i + 1] == "*":
            end = css.find("*/", i + 2)
            if end == -1:
                out.append("\n" * css[i:].count("\n"))
                break
            out.append("\n" * css[i : end + 2].count("\n"))
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level(text: str, delimiter: str) -> list[str]:
    """Split text on delimiter outside quotes, parentheses, and square brackets."""
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    paren_depth = 0
    bracket_depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                buf.append(text[i])
            elif ch == quote:
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
                buf.append(ch)
            elif ch == "(":
                paren_depth += 1
                buf.append(ch)
            elif ch == ")" and paren_depth > 0:
                paren_depth -= 1
                buf.append(ch)
            elif ch == "[":
                bracket_depth += 1
                buf.append(ch)
            elif ch == "]" and bracket_depth > 0:
                bracket_depth -= 1
                buf.append(ch)
            elif ch == delimiter and paren_depth == 0 and bracket_depth == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _read_quoted_string(text: str, start: int) -> tuple[str, int]:
    """Read a CSS quoted string starting at quote char text[start]; return (unquoted, next_idx)."""
    quote = text[start]
    i = start + 1
    n = len(text)
    buf: list[str] = []
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        if ch == quote:
            return "".join(buf), i + 1
        buf.append(ch)
        i += 1
    return "".join(buf), n


def _read_css_url_token(text: str, lparen_idx: int) -> tuple[str, int]:
    """Read argument inside url(...), starting at '('; return (url_value, index_after_rparen)."""
    i = lparen_idx + 1
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return "", n
    if text[i] in ("'", '"'):
        url_val, i = _read_quoted_string(text, i)
        while i < n and text[i] != ")":
            i += 1
        return url_val.strip(), min(i + 1, n)

    start = i
    while i < n and text[i] != ")":
        if text[i] == "\\" and i + 1 < n:
            i += 2
            continue
        i += 1
    return text[start:i].strip(), min(i + 1, n)


def extract_css_external_urls(
    css: str,
    start_line: int,
) -> list[tuple[int, str, str]]:
    """Scan comment-stripped CSS tokens for out-of-file @import and url(...) references.

    Quoted strings outside @import/url() (such as `content: "url(https://...)"`)
    are skipped so literal text inside CSS strings is never falsely flagged.
    """
    clean = strip_css_comments(css)
    hits: list[tuple[int, str, str]] = []
    i = 0
    n = len(clean)
    line = start_line

    while i < n:
        ch = clean[i]
        if ch == "\n":
            line += 1
            i += 1
            continue

        # Skip standalone CSS string literals (e.g. content: "url(...)").
        if ch in ("'", '"'):
            start = i
            _, end = _read_quoted_string(clean, i)
            line += clean[start:end].count("\n")
            i = end
            continue

        # Check @import
        if ch == "@" and clean[i : i + 7].lower() == "@import" and (
            i + 7 >= n or not (clean[i + 7].isalnum() or clean[i + 7] in ("-", "_"))
        ):
            import_line = line
            j = i + 7
            while j < n and clean[j].isspace():
                if clean[j] == "\n":
                    line += 1
                j += 1
            if j < n and clean[j] in ("'", '"'):
                url_val, end = _read_quoted_string(clean, j)
                line += clean[j:end].count("\n")
                if is_external_resource_url(url_val):
                    hits.append((import_line, "@import", url_val.strip()))
                i = end
                continue
            if clean[j : j + 4].lower() == "url(":
                url_val, end = _read_css_url_token(clean, j + 3)
                line += clean[j:end].count("\n")
                if is_external_resource_url(url_val):
                    hits.append((import_line, "@import", url_val.strip()))
                i = end
                continue
            i = j
            continue

        # Check url(...) function token (not preceded by identifier char)
        if (
            ch in ("u", "U")
            and clean[i : i + 4].lower() == "url("
            and (i == 0 or not (clean[i - 1].isalnum() or clean[i - 1] in ("-", "_")))
        ):
            url_line = line
            url_val, end = _read_css_url_token(clean, i + 3)
            line += clean[i:end].count("\n")
            if is_external_resource_url(url_val):
                hits.append((url_line, "url()", url_val.strip()))
            i = end
            continue

        # Check image-set(...) / -webkit-image-set(...) function tokens (quoted string or url() candidates)
        matched_imageset_len = 0
        if i == 0 or not (clean[i - 1].isalnum() or clean[i - 1] in ("-", "_")):
            if clean[i : i + 10].lower() == "image-set(":
                matched_imageset_len = 10
            elif clean[i : i + 18].lower() == "-webkit-image-set(":
                matched_imageset_len = 18
        if matched_imageset_len:
            j = i + matched_imageset_len
            line += clean[i:j].count("\n")
            depth = 1
            while j < n and depth > 0:
                c = clean[j]
                if c == "\n":
                    line += 1
                    j += 1
                    continue
                if c in ("'", '"'):
                    cand_line = line
                    cand_val, end = _read_quoted_string(clean, j)
                    line += clean[j:end].count("\n")
                    if depth == 1 and is_external_resource_url(cand_val):
                        hits.append((cand_line, "image-set()", cand_val.strip()))
                    j = end
                    continue
                if (
                    c in ("u", "U")
                    and clean[j : j + 4].lower() == "url("
                    and (j == 0 or not (clean[j - 1].isalnum() or clean[j - 1] in ("-", "_")))
                ):
                    url_line = line
                    url_val, end = _read_css_url_token(clean, j + 3)
                    line += clean[j:end].count("\n")
                    if is_external_resource_url(url_val):
                        hits.append((url_line, "image-set()", url_val.strip()))
                    j = end
                    continue
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                j += 1
            i = j
            continue

        i += 1

    return hits


def parse_declarations(block: str, start_line: int) -> list[CssDeclaration]:
    """Parse CSS property:value declarations inside a declaration block."""
    decls: list[CssDeclaration] = []
    cur_line = start_line
    for raw_item in _split_top_level(block, ";"):
        leading = raw_item[: len(raw_item) - len(raw_item.lstrip())]
        item_line = cur_line + leading.count("\n")
        cur_line += raw_item.count("\n")
        stripped = raw_item.strip()
        if not stripped or ":" not in stripped:
            continue
        name, value = stripped.split(":", 1)
        prop = name.strip().lower()
        val = value.strip()
        if prop:
            decls.append(
                CssDeclaration(
                    name=prop,
                    value=val,
                    line=item_line,
                    important=bool(IMPORTANT_RE.search(val)),
                )
            )
    return decls


def _read_balanced_braces(css: str, open_idx: int) -> int:
    """Given index of '{', return index of matching '}' (or len(css) if unclosed)."""
    depth = 0
    quote: str | None = None
    i = open_idx
    n = len(css)
    while i < n:
        ch = css[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return n


def parse_css(
    css: str,
    start_line: int = 1,
    in_reduced_motion: bool = False,
    conditional: bool = False,
) -> CssParseResult:
    """Iteratively parse CSS into rules, handling arbitrary nesting without recursion."""
    result = CssParseResult()
    clean_css = strip_css_comments(css)

    # Explicit stack of frames:
    # (slice_text, index, line, in_reduced_motion, conditional, layered)
    frames: list[tuple[str, int, int, bool, bool, bool]] = [
        (clean_css, 0, start_line, in_reduced_motion, conditional, False)
    ]

    while frames:
        text, i, line, in_rm, in_cond, in_layer = frames.pop()
        n = len(text)

        while i < n:
            while i < n and text[i].isspace():
                if text[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                break

            if text[i] == "@":
                header_start = i
                quote: str | None = None
                while i < n:
                    ch = text[i]
                    if quote is not None:
                        if ch == "\\" and i + 1 < n:
                            line += text[i : i + 2].count("\n")
                            i += 2
                            continue
                        if ch == quote:
                            quote = None
                    else:
                        if ch in ("'", '"'):
                            quote = ch
                        elif ch in ("{", ";"):
                            break
                    if ch == "\n":
                        line += 1
                    i += 1

                prelude = text[header_start:i].strip()
                if i >= n:
                    break
                if text[i] == ";":
                    i += 1
                    continue

                block_start_line = line
                close_idx = _read_balanced_braces(text, i)
                inner_css = text[i + 1 : close_idx]
                next_line = line + text[i : close_idx + 1].count("\n")
                next_i = close_idx + 1

                at_match = re.match(r"^@([a-zA-Z0-9_-]+)", prelude)
                at_name = at_match.group(1).lower() if at_match else ""
                if at_name in ("media", "supports", "layer", "container"):
                    is_rm = in_rm or (
                        at_name == "media" and _is_positive_reduced_motion_media(prelude)
                    )
                    if is_rm:
                        result.has_reduced_motion_block = True
                    # Push remainder of current frame first, then inner block so inner runs next.
                    if next_i < n:
                        frames.append((text, next_i, next_line, in_rm, in_cond, in_layer))
                    frames.append(
                        (inner_css, 0, block_start_line, is_rm, True, in_layer or at_name == "layer")
                    )
                    break

                # Skip non-rule at-rule bodies (@keyframes, @font-face, @page, etc.).
                i = next_i
                line = next_line
                continue

            # Regular style rule: selector(s) { declarations }
            sel_start = i
            sel_line = line
            quote = None
            while i < n:
                ch = text[i]
                if quote is not None:
                    if ch == "\\" and i + 1 < n:
                        line += text[i : i + 2].count("\n")
                        i += 2
                        continue
                    if ch == quote:
                        quote = None
                else:
                    if ch in ("'", '"'):
                        quote = ch
                    elif ch == "{":
                        break
                    elif ch == "}":
                        i += 1
                        break
                if ch == "\n":
                    line += 1
                i += 1

            if i >= n or text[i] != "{":
                continue

            selector_text = text[sel_start:i].strip()
            block_start_line = line
            close_idx = _read_balanced_braces(text, i)
            decl_text = text[i + 1 : close_idx]
            line += text[i : close_idx + 1].count("\n")
            i = close_idx + 1

            selectors = [s.strip() for s in _split_top_level(selector_text, ",") if s.strip()]
            if not selectors:
                continue
            decls = parse_declarations(decl_text, block_start_line)
            rule = CssRule(
                selectors=selectors,
                declarations=decls,
                line=sel_line,
                in_reduced_motion=in_rm,
                conditional=in_cond,
                layered=in_layer,
            )
            result.rules.append(rule)
            if in_rm:
                result.reduced_motion_rules.append(rule)

    return result


def extract_font_size_px(prop: str, value: str, allow_unitless: bool = False) -> float | None:
    """Extract an absolute font size in px from a CSS font-size/font value or SVG attribute."""
    if prop == "font-size":
        m = FONT_SIZE_VALUE_RE.match(value)
        if not m:
            return None
        num = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if not unit:
            # In CSS, unitless 0 is a valid length; in SVG presentation attributes, any number is px.
            if allow_unitless or num == 0.0:
                return num
            return None
        if unit == "pt":
            return num * 4.0 / 3.0
        return num

    if prop == "font":
        cleaned = re.sub(r"""(?:"[^"]*"|'[^']*')""", " ", value)
        m = FONT_SHORTHAND_SIZE_RE.search(cleaned)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "pt":
            return num * 4.0 / 3.0
        return num

    return None


def _strip_attribute_selectors(selector: str) -> str:
    """Remove [...] attribute selector blocks so values like [type="text"] don't look like tags."""
    out: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    n = len(selector)
    while i < n:
        ch = selector[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch == "[":
                depth += 1
                out.append(" ")
            elif ch == "]" and depth > 0:
                depth -= 1
                out.append(" ")
            elif depth == 0:
                out.append(ch)
        i += 1
    return "".join(out)


def _add_spec(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int, int]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _read_ident(text: str, idx: int) -> tuple[str, int]:
    """Read a CSS identifier (handling simple backslash escapes) starting at idx."""
    n = len(text)
    buf: list[str] = []
    i = idx
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        if ch.isalnum() or ch in ("-", "_") or ord(ch) >= 0x80:
            buf.append(ch)
            i += 1
        else:
            break
    return "".join(buf), i


def _read_balanced_delim(text: str, open_idx: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    """Read balanced (...) or [...] starting at open_idx; return (inner_text, index_after_close)."""
    depth = 0
    quote: str | None = None
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in ("'", '"'):
                quote = ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[open_idx + 1 : i], i + 1
        i += 1
    return text[open_idx + 1 :], n


def _parse_attr_condition(inner: str) -> AttrCondition | None:
    s = inner.strip()
    if not s:
        return None
    name, i = _read_ident(s, 0)
    if not name:
        return None
    name = name.lower()
    n = len(s)
    while i < n and s[i].isspace():
        i += 1
    if i >= n:
        return AttrCondition(name=name, op="", value="")

    op = ""
    if s[i : i + 2] in ("~=", "|=", "^=", "$=", "*="):
        op = s[i : i + 2]
        i += 2
    elif s[i] == "=":
        op = "="
        i += 1
    else:
        return None

    while i < n and s[i].isspace():
        i += 1
    if i >= n:
        return AttrCondition(name=name, op=op, value="")

    if s[i] in ("'", '"'):
        val, i = _read_quoted_string(s, i)
    else:
        start = i
        while i < n and not s[i].isspace():
            i += 1
        val = s[start:i]

    while i < n and s[i].isspace():
        i += 1
    case_insensitive = i < n and s[i] in ("i", "I")
    return AttrCondition(name=name, op=op, value=val, case_insensitive=case_insensitive)


def parse_selector(selector: str, _depth: int = 0) -> ParsedSelector | None:
    """Parse a single CSS complex selector into compounds, combinators, and specificity."""
    if _depth > _MAX_SELECTOR_DEPTH:
        return None
    s = selector.strip()
    if not s:
        return None

    compounds: list[CompoundSelector] = []
    combinators: list[str] = []
    i = 0
    n = len(s)

    while i < n:
        comp = CompoundSelector()
        spec = (0, 0, 0)
        consumed_any = False

        # Optional leading type selector or '*'.
        if i < n and s[i] == "*":
            comp.tag = "*"
            i += 1
            consumed_any = True
        elif i < n and (s[i].isalpha() or s[i] in ("_", "-") or ord(s[i]) >= 0x80):
            tag_name, i = _read_ident(s, i)
            if tag_name:
                comp.tag = tag_name.lower()
                spec = _add_spec(spec, (0, 0, 1))
                consumed_any = True

        # Zero or more simple selectors attached without whitespace/combinator.
        while i < n:
            ch = s[i]
            if ch == "#":
                ident, next_i = _read_ident(s, i + 1)
                if not ident:
                    return None
                comp.ids.append(ident)
                spec = _add_spec(spec, (1, 0, 0))
                i = next_i
                consumed_any = True
            elif ch == ".":
                ident, next_i = _read_ident(s, i + 1)
                if not ident:
                    return None
                comp.classes.append(ident)
                spec = _add_spec(spec, (0, 1, 0))
                i = next_i
                consumed_any = True
            elif ch == "[":
                inner, next_i = _read_balanced_delim(s, i, "[", "]")
                cond = _parse_attr_condition(inner)
                if cond is None:
                    return None
                comp.attrs.append(cond)
                spec = _add_spec(spec, (0, 1, 0))
                i = next_i
                consumed_any = True
            elif ch == ":":
                is_double = i + 1 < n and s[i + 1] == ":"
                ident, next_i = _read_ident(s, i + (2 if is_double else 1))
                if not ident:
                    return None
                lname = ident.lower()
                i = next_i
                consumed_any = True
                if is_double or lname in _PSEUDO_ELEMENT_NAMES:
                    comp.has_pseudo_element = True
                    spec = _add_spec(spec, (0, 0, 1))
                    if i < n and s[i] == "(":
                        _, i = _read_balanced_delim(s, i, "(", ")")
                elif i < n and s[i] == "(":
                    arg_text, i = _read_balanced_delim(s, i, "(", ")")
                    if lname in ("not", "is", "where"):
                        sub_sels = [
                            ps
                            for raw in _split_top_level(arg_text, ",")
                            if raw.strip()
                            for ps in [parse_selector(raw, _depth + 1)]
                            if ps is not None
                        ]
                        if lname == "not":
                            comp.not_groups.append(sub_sels)
                        else:
                            comp.any_groups.append(sub_sels)
                        if lname != "where" and sub_sels:
                            max_sub = max(ps.specificity for ps in sub_sels)
                            spec = _add_spec(spec, max_sub)
                    else:
                        comp.pseudo_classes.append(f"{lname}({arg_text.strip()})")
                        spec = _add_spec(spec, (0, 1, 0))
                else:
                    comp.pseudo_classes.append(lname)
                    spec = _add_spec(spec, (0, 1, 0))
            else:
                break

        if not consumed_any:
            return None

        comp.specificity = spec
        compounds.append(comp)

        if i >= n:
            break

        # Read combinator between compounds.
        saw_ws = False
        while i < n and s[i].isspace():
            saw_ws = True
            i += 1
        if i >= n:
            break

        if s[i] in (">", "+", "~"):
            comb = s[i]
            i += 1
            while i < n and s[i].isspace():
                i += 1
            if i >= n:
                return None
            combinators.append(comb)
        elif saw_ws:
            combinators.append(" ")
        else:
            return None

    if not compounds or len(combinators) != len(compounds) - 1:
        return None

    total_spec = (0, 0, 0)
    for c in compounds:
        total_spec = _add_spec(total_spec, c.specificity)
    has_pe = any(c.has_pseudo_element for c in compounds)
    return ParsedSelector(
        compounds=compounds,
        combinators=combinators,
        specificity=total_spec,
        has_pseudo_element=has_pe,
    )


def _attr_matches(cond: AttrCondition, attrs: dict[str, str]) -> bool:
    if cond.name not in attrs:
        return False
    if not cond.op:
        return True
    actual = attrs[cond.name]
    expected = cond.value
    if cond.case_insensitive:
        actual = actual.lower()
        expected = expected.lower()
    if cond.op == "=":
        return actual == expected
    if cond.op == "~=":
        return bool(expected) and expected in actual.split()
    if cond.op == "|=":
        return actual == expected or actual.startswith(expected + "-")
    if cond.op == "^=":
        return bool(expected) and actual.startswith(expected)
    if cond.op == "$=":
        return bool(expected) and actual.endswith(expected)
    if cond.op == "*=":
        return bool(expected) and expected in actual
    return False


def _node_classes(node: DomNode, js_active: bool) -> frozenset[str]:
    if js_active and node.tag in ("html", "body"):
        return node.classes | frozenset({"js"})
    return node.classes


def _compound_matches(
    comp: CompoundSelector,
    node: DomNode,
    js_active: bool = False,
    _depth: int = 0,
) -> bool:
    if _depth > _MAX_SELECTOR_DEPTH or comp.has_pseudo_element:
        return False
    if comp.tag is not None and comp.tag != "*" and node.tag != comp.tag:
        return False
    for req_id in comp.ids:
        if node.elem_id != req_id:
            return False
    classes = _node_classes(node, js_active)
    for req_cls in comp.classes:
        if req_cls not in classes:
            return False
    for cond in comp.attrs:
        if not _attr_matches(cond, node.attrs):
            return False
    for pc in comp.pseudo_classes:
        if pc == "root" and node.tag != "html" and node.parent is not None:
            return False
        if pc == "first-child" and node.sibling_index != 0:
            return False
    for group in comp.not_groups:
        if any(selector_matches(ps, node, js_active=js_active, _depth=_depth + 1) for ps in group):
            return False
    for group in comp.any_groups:
        if group and not any(
            selector_matches(ps, node, js_active=js_active, _depth=_depth + 1) for ps in group
        ):
            return False
    return True


_STATIC_PSEUDO_CLASSES = frozenset({"root", "first-child"})


def _state_independent(parsed: ParsedSelector, _depth: int = 0) -> bool:
    """True when the selector uses only pseudo-classes that selector_matches evaluates
    (:root, :first-child), so a match holds in every interaction state."""
    if _depth > _MAX_SELECTOR_DEPTH:
        return False
    for comp in parsed.compounds:
        if any(pc not in _STATIC_PSEUDO_CLASSES for pc in comp.pseudo_classes):
            return False
        for group in comp.not_groups + comp.any_groups:
            if not all(_state_independent(ps, _depth + 1) for ps in group):
                return False
    return True


def _is_positive_reduced_motion_media(prelude: str) -> bool:
    """Return True if at least one comma-separated @media query positively targets prefers-reduced-motion: reduce."""
    body = re.sub(r"^@media\b", "", prelude, flags=re.IGNORECASE).strip()
    if not body:
        return False
    for query in _split_top_level(body, ","):
        q = query.strip()
        if not q:
            continue
        m = CSS_REDUCED_MOTION_RE.search(q)
        if not m:
            continue
        # Reject negated media queries (e.g. `not (prefers-reduced-motion: reduce)` or `not all and (...)`).
        prefix = q[: m.start()]
        if re.search(r"(?<![a-zA-Z0-9_-])not(?![a-zA-Z0-9_-])", prefix, re.IGNORECASE):
            continue
        return True
    return False


def selector_matches(
    parsed: ParsedSelector,
    node: DomNode,
    js_active: bool = False,
    _depth: int = 0,
) -> bool:
    """Return True if parsed CSS selector matches node in the DOM tree (iterative)."""
    if _depth > _MAX_SELECTOR_DEPTH or parsed.has_pseudo_element:
        return False

    stack: list[tuple[int, DomNode]] = [(len(parsed.compounds) - 1, node)]
    visited: set[tuple[int, int]] = set()
    while stack:
        comp_idx, cur = stack.pop()
        state = (comp_idx, id(cur))
        if state in visited:
            continue
        visited.add(state)
        if not _compound_matches(parsed.compounds[comp_idx], cur, js_active=js_active, _depth=_depth):
            continue
        if comp_idx == 0:
            return True
        comb = parsed.combinators[comp_idx - 1]
        if comb == ">":
            if cur.parent is not None:
                stack.append((comp_idx - 1, cur.parent))
        elif comb == " ":
            anc = cur.parent
            while anc is not None:
                stack.append((comp_idx - 1, anc))
                anc = anc.parent
        elif comb == "+":
            if cur.prev_sibling is not None:
                stack.append((comp_idx - 1, cur.prev_sibling))
        elif comb == "~":
            sib = cur.prev_sibling
            while sib is not None:
                stack.append((comp_idx - 1, sib))
                sib = sib.prev_sibling
    return False


def _normalize_selector(sel: str) -> str:
    return re.sub(r"\s+", " ", sel.strip())


def _compound_generalizes(general: CompoundSelector, specific: CompoundSelector) -> bool:
    """Return True if every constraint in `general` is implied by `specific`."""
    if general.has_pseudo_element != specific.has_pseudo_element:
        return False
    if general.tag not in (None, "*") and general.tag != specific.tag:
        return False
    if not set(general.ids).issubset(set(specific.ids)):
        return False
    if not set(general.classes).issubset(set(specific.classes)):
        return False
    if not set(general.attrs).issubset(set(specific.attrs)):
        return False
    if general.not_groups and general.not_groups != specific.not_groups:
        return False
    if general.any_groups and general.any_groups != specific.any_groups:
        return False
    if not set(general.pseudo_classes).issubset(set(specific.pseudo_classes)):
        return False
    return True


def _selector_structurally_covers(rm_parsed: ParsedSelector, src_parsed: ParsedSelector) -> bool:
    """Return True when rm_parsed covers src_parsed structurally (used when 0 DOM nodes match)."""
    if rm_parsed.is_universal_element:
        return True
    if rm_parsed.has_pseudo_element != src_parsed.has_pseudo_element:
        return False
    if not _compound_generalizes(rm_parsed.compounds[-1], src_parsed.compounds[-1]):
        return False
    # Every earlier compound in rm_parsed must generalize an earlier compound in src_parsed in order.
    r_idx = len(rm_parsed.compounds) - 2
    s_idx = len(src_parsed.compounds) - 2
    while r_idx >= 0:
        found = False
        while s_idx >= 0:
            if _compound_generalizes(rm_parsed.compounds[r_idx], src_parsed.compounds[s_idx]):
                s_idx -= 1
                found = True
                break
            s_idx -= 1
        if not found:
            return False
        r_idx -= 1
    return True


def _is_motion_disabled_duration(value: str) -> bool:
    """Return True if a CSS duration value is effectively zero (<= 0.01s)."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        return False
    for part in parts:
        m = DURATION_RE.match(part)
        if not m:
            return False
        num = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        seconds = num / 1000.0 if unit == "ms" else num
        if seconds > 0.01:
            return False
    return True


def _strip_important(value: str) -> str:
    return IMPORTANT_RE.sub("", value).strip()


def _is_none_value(value: str) -> bool:
    return _strip_important(value).lower() == "none"


def _parse_opacity_value(value: str) -> float | None:
    cleaned = _strip_important(value).strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("%"):
            num = float(cleaned[:-1].strip()) / 100.0
        else:
            num = float(cleaned)
    except ValueError:
        return None
    return num if math.isfinite(num) else None


def _is_zero_opacity(value: str) -> bool:
    num = _parse_opacity_value(value)
    return num is not None and num <= 0.0


def _is_restored_opacity(value: str) -> bool:
    cleaned = _strip_important(value).lower()
    if cleaned in ("initial", "unset", "revert"):
        return True
    num = _parse_opacity_value(cleaned)
    return num is not None and num > 0.0


def _validate_viewbox(value: str) -> tuple[bool, str]:
    """Validate an SVG viewBox string (4 finite numbers, width > 0, height > 0)."""
    stripped = value.strip()
    if not stripped:
        return False, "empty viewBox attribute"
    tokens = re.split(r"\s*,\s*|\s+", stripped)
    if len(tokens) != 4:
        return False, f"expected 4 numbers in viewBox, got {len(tokens)} ({value!r})"
    nums: list[float] = []
    for tok in tokens:
        if not NUMBER_RE.match(tok):
            return False, f"non-numeric or non-finite value {tok!r} in viewBox ({value!r})"
        val = float(tok)
        if not math.isfinite(val):
            return False, f"non-finite value {tok!r} in viewBox ({value!r})"
        nums.append(val)
    if nums[2] <= 0 or nums[3] <= 0:
        return (
            False,
            f"viewBox width ({nums[2]:g}) and height ({nums[3]:g}) must both be > 0",
        )
    return True, ""


def _fmt_num(val: float) -> str:
    return f"{val:g}"


class VisualHTMLAnalyzer(HTMLParser):
    """Single-pass HTML/SVG parser building a lightweight DOM for all checks."""

    def __init__(self, filename: str, config: CheckConfig) -> None:
        super().__init__(convert_charrefs=True)
        self.filename = filename
        self.config = config
        self.failures: list[Failure] = []

        self._node_stack: list[DomNode] = []
        self._child_counts: dict[int | None, int] = {None: 0}
        self._last_child: dict[int | None, DomNode | None] = {None: None}
        self.all_nodes: list[DomNode] = []

        # (start line, text chunks, conditional: the <style> has a media attribute)
        self._style_blocks: list[tuple[int, list[str], bool]] = []
        self._in_style = False
        self._in_script = False
        self._template_depth = 0
        self._noscript_depth = 0
        self._unresolved_font_size = False

        self._figure_counter = 0
        self._figure_stack: list[int] = []

        self._svg_depth = 0
        self._svg_non_render_depth = 0
        self._svg_counter = 0
        self._current_svg: SvgInfo | None = None
        self.svgs: list[SvgInfo] = []

        self._svg_text_depth = 0
        self._svg_text_line = 0
        self._svg_text_chunks: list[str] = []
        self.svg_text_nodes: list[TextBlock] = []

        self._section_counter = 0
        self._section_stack: list[SectionInfo] = []
        self.sections: list[SectionInfo] = []

        self._html_text_blocks: list[TextBlock] = []
        self._cur_html_chunks: list[str] = []
        self._cur_html_line = 1

        self.aria_labels: list[tuple[str, str]] = []
        self.inline_motion_nodes: list[tuple[DomNode, int, str]] = []
        self._inline_svg_fonts: list[tuple[SvgInfo, int, str, str, float]] = []

    def _in_hidden_subtree(self) -> bool:
        return bool(self._node_stack and self._node_stack[-1].in_hidden)

    def _in_foreign_object(self) -> bool:
        return bool(self._node_stack and self._node_stack[-1].in_foreign_object)

    def _flush_html_text_block(self) -> None:
        if self._cur_html_chunks:
            text = "".join(self._cur_html_chunks)
            if text.strip():
                self._html_text_blocks.append(
                    TextBlock(location=f"HTML text near line {self._cur_html_line}", text=text)
                )
            self._cur_html_chunks = []

    def _add_failure(
        self,
        location: str,
        check: str,
        problem: str,
        expected: str,
        fix: str,
    ) -> None:
        self.failures.append(
            Failure(
                file=self.filename,
                location=location,
                check=check,
                problem=problem,
                expected=expected,
                fix=fix,
            )
        )

    def _check_external_attr(
        self,
        tag: str,
        attr_name: str,
        value: str,
        line: int,
    ) -> None:
        if self.config.allow_external_assets:
            return
        if is_external_resource_url(value):
            self._add_failure(
                location=f"line {line}, <{tag} {attr_name}>",
                check="external-asset",
                problem=f"Out-of-file resource URL {value!r} found in <{tag} {attr_name}>.",
                expected="Self-contained single-file HTML with no out-of-file resource dependencies (inline CSS/SVG/JS, data: URIs, and same-document #fragments only; ordinary <a href> navigation links are allowed).",
                fix=f"Inline the resource or embed it as a data: URI, remove the external <{tag}>, or pass --allow-external-assets if out-of-file assets are intentionally required.",
            )

    def _check_svg_url_ref_attr(
        self,
        tag: str,
        attr_name: str,
        value: str,
        line: int,
    ) -> None:
        if self.config.allow_external_assets or "url(" not in value.lower():
            return
        for _, _, url in extract_css_external_urls(value, line):
            self._add_failure(
                location=f"line {line}, <{tag} {attr_name}>",
                check="external-asset",
                problem=f"Out-of-file SVG paint/reference url({url!r}) found in <{tag} {attr_name}>.",
                expected="SVG paint and reference attributes must only reference same-document #fragments or data: URIs.",
                fix=f"Move the referenced SVG definition into an inline <defs> block in this file and reference it with url(#id), or pass --allow-external-assets if external assets are intentionally required.",
            )

    def _check_inline_style(
        self,
        node: DomNode,
        tag: str,
        style_value: str,
        line: int,
    ) -> None:
        if not self.config.allow_external_assets:
            for css_line, kind, url in extract_css_external_urls(style_value, line):
                self._add_failure(
                    location=f"line {css_line}, <{tag} style>",
                    check="external-asset",
                    problem=f"Out-of-file resource URL {url!r} found in inline style {kind} on <{tag}>.",
                    expected="Self-contained single-file styles with no out-of-file resource URLs.",
                    fix="Replace the external URL with an inline SVG/data: URI or same-document #fragment, or pass --allow-external-assets if external assets are intentionally required.",
                )

        decls = parse_declarations(strip_css_comments(style_value), line)
        for decl in decls:
            if decl.name in ("transition", "transition-property", "transition-duration"):
                if not _is_none_value(decl.value) and not (
                    decl.name == "transition-duration" and _is_motion_disabled_duration(decl.value)
                ):
                    self.inline_motion_nodes.append((node, line, "transition"))
            elif decl.name in ("animation", "animation-name", "animation-duration"):
                if not _is_none_value(decl.value) and not (
                    decl.name == "animation-duration" and _is_motion_disabled_duration(decl.value)
                ):
                    self.inline_motion_nodes.append((node, line, "animation"))

            if (
                self._svg_depth > 0
                and self._current_svg is not None
                and not node.in_foreign_object
            ):
                if decl.name in ("font-size", "font"):
                    size_px = extract_font_size_px(decl.name, decl.value, allow_unitless=False)
                    if size_px is not None:
                        self._inline_svg_fonts.append(
                            (
                                self._current_svg,
                                line,
                                f'<{tag} style="{decl.name}: {decl.value}">',
                                decl.name,
                                size_px,
                            )
                        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, _ = self.getpos()
        tag = tag.lower()

        parent = self._node_stack[-1] if self._node_stack else None
        parent_in_foreign = parent.in_foreign_object if parent is not None else False
        is_html_context = self._svg_depth == 0 or parent_in_foreign

        if tag in BLOCK_HTML_ELEMENTS and is_html_context:
            self._flush_html_text_block()
            if (
                self._svg_depth == 0
                and self._section_stack
                and not self._figure_stack
                and not self._in_hidden_subtree()
            ):
                for sec in self._section_stack:
                    sec.outside_chunks.append(" ")

        # Detect duplicate attributes on <svg> and its SVG descendants.
        in_svg_scope = (self._svg_depth > 0 and not parent_in_foreign) or tag == "svg"
        attr_map: dict[str, str] = {}
        seen_attrs: set[str] = set()
        reported_dups: set[str] = set()
        for name, val in attrs:
            key = name.lower()
            if key in seen_attrs:
                if in_svg_scope and key not in reported_dups:
                    reported_dups.add(key)
                    self._add_failure(
                        location=f"line {line}, <{tag}>",
                        check="svg-duplicate-attr",
                        problem=f"Duplicate attribute {key!r} on SVG element <{tag}>.",
                        expected="Every attribute name on <svg> and its descendants must appear at most once.",
                        fix=f"Remove or merge the duplicate {key!r} attribute on <{tag}> at line {line}.",
                    )
            else:
                seen_attrs.add(key)
                attr_map[key] = "" if val is None else val

        in_hidden = (parent.in_hidden if parent is not None else False) or ("hidden" in attr_map)

        if "aria-label" in attr_map and not in_hidden and self._template_depth == 0:
            self.aria_labels.append((f"line {line}, <{tag}> aria-label", attr_map["aria-label"]))

        # Out-of-file resource checks on HTML & SVG elements.
        if tag == "script" and "src" in attr_map:
            self._check_external_attr(tag, "src", attr_map["src"], line)
        elif tag == "link":
            rel_tokens = set(attr_map.get("rel", "").lower().split())
            is_nav_link = bool(rel_tokens) and rel_tokens.issubset(NAVIGATION_LINK_RELS)
            if not is_nav_link:
                if "href" in attr_map:
                    self._check_external_attr(tag, "href", attr_map["href"], line)
                if "imagesrcset" in attr_map:
                    for url in parse_srcset_urls(attr_map["imagesrcset"]):
                        self._check_external_attr(tag, "imagesrcset", url, line)
        elif tag in ("img", "source"):
            if "src" in attr_map:
                self._check_external_attr(tag, "src", attr_map["src"], line)
            if "srcset" in attr_map:
                for url in parse_srcset_urls(attr_map["srcset"]):
                    self._check_external_attr(tag, "srcset", url, line)
        elif tag == "input" and "src" in attr_map:
            self._check_external_attr(tag, "src", attr_map["src"], line)
        elif tag in ("iframe", "audio", "embed", "track") and "src" in attr_map:
            self._check_external_attr(tag, "src", attr_map["src"], line)
        elif tag == "video":
            if "src" in attr_map:
                self._check_external_attr(tag, "src", attr_map["src"], line)
            if "poster" in attr_map:
                self._check_external_attr(tag, "poster", attr_map["poster"], line)
        elif tag == "object" and "data" in attr_map:
            self._check_external_attr(tag, "data", attr_map["data"], line)
        elif in_svg_scope and tag in ("image", "use", "feimage"):
            for href_attr in ("href", "xlink:href"):
                if href_attr in attr_map:
                    self._check_external_attr(tag, href_attr, attr_map[href_attr], line)

        if in_svg_scope:
            for ref_attr in SVG_URL_REF_ATTRS:
                if ref_attr in attr_map:
                    self._check_svg_url_ref_attr(tag, ref_attr, attr_map[ref_attr], line)

        # Enter <svg> context before creating DomNode / checking inline styles.
        if tag == "svg":
            if self._svg_depth == 0:
                self._flush_html_text_block()
            self._svg_depth += 1
            if self._svg_depth == 1:
                self._svg_counter += 1
                classes = {c.lower() for c in attr_map.get("class", "").split()}
                data_layout = attr_map.get("data-layout", "").strip().lower()
                is_narrow = bool(classes & {"n", "narrow"}) or data_layout == "narrow"
                active_fig = self._figure_stack[-1] if self._figure_stack else None
                info = SvgInfo(
                    index=self._svg_counter,
                    line=line,
                    attrs=attr_map,
                    figure_index=active_fig,
                    is_narrow=is_narrow,
                )
                self._current_svg = info
                self.svgs.append(info)
        elif self._svg_depth > 0:
            if tag == "foreignobject" and not self.config.allow_foreign_object:
                self._add_failure(
                    location=f"line {line}, <foreignObject>",
                    check="svg-forbidden-element",
                    problem="Found <foreignObject> inside <svg>.",
                    expected="Native SVG primitives (<text>, <tspan>, shapes) without <foreignObject> for consistent cross-browser and offline rendering.",
                    fix="Replace <foreignObject> with native SVG elements, or pass --allow-foreign-object if HTML embedding inside SVG is intentionally required.",
                )
            elif tag == "script":
                self._in_script = True
                self._add_failure(
                    location=f"line {line}, <svg> > <script>",
                    check="svg-forbidden-element",
                    problem="Found <script> element inside <svg>.",
                    expected="SVG diagrams must be declarative and contain no embedded <script> elements.",
                    fix="Remove <script> from inside <svg> and place any progressive-enhancement script at document level outside <svg>.",
                )

            if self._current_svg is not None and not parent_in_foreign:
                if tag == "defs":
                    self._current_svg.has_defs = True
                if tag in NON_RENDERING_SVG_CONTAINERS:
                    self._svg_non_render_depth += 1
                elif self._svg_non_render_depth == 0 and tag in VISIBLE_SVG_ELEMENTS:
                    self._current_svg.has_visible_content = True

            if tag == "text" and not parent_in_foreign:
                if self._svg_text_depth == 0:
                    self._svg_text_line = line
                    self._svg_text_chunks = []
                self._svg_text_depth += 1

        node_in_foreign = parent_in_foreign or (self._svg_depth > 0 and tag == "foreignobject")
        if tag == "foreignobject" and self._svg_depth > 0:
            self._flush_html_text_block()

        # Construct DomNode for selector matching.
        parent_key = id(parent) if parent is not None else None
        sib_idx = self._child_counts.get(parent_key, 0)
        prev_sib = self._last_child.get(parent_key)
        node = DomNode(
            tag=tag,
            attrs=attr_map,
            classes=frozenset(attr_map.get("class", "").split()),
            elem_id=attr_map.get("id", "").strip(),
            parent=parent,
            sibling_index=sib_idx,
            prev_sibling=prev_sib,
            svg_owner=self._current_svg if self._svg_depth > 0 else None,
            in_non_render_svg=self._svg_non_render_depth > 0,
            in_hidden=in_hidden,
            in_foreign_object=node_in_foreign,
        )
        self._child_counts[parent_key] = sib_idx + 1
        self._last_child[parent_key] = node
        self.all_nodes.append(node)

        # Mark SVG ancestors of <text>/<tspan>/<textPath> for accurate font-size inheritance checks.
        if (
            self._svg_depth > 0
            and self._current_svg is not None
            and not node.in_non_render_svg
            and not node.in_foreign_object
            and tag in ("text", "tspan", "textpath")
        ):
            anc = node.parent
            while anc is not None and anc.svg_owner is self._current_svg:
                anc.has_svg_text_descendant = True
                anc = anc.parent

        if "style" in attr_map:
            self._check_inline_style(node, tag, attr_map["style"], line)

        if (
            self._svg_depth > 0
            and self._current_svg is not None
            and not node.in_foreign_object
            and "font-size" in attr_map
        ):
            size_px = extract_font_size_px("font-size", attr_map["font-size"], allow_unitless=True)
            if size_px is not None:
                self._inline_svg_fonts.append(
                    (
                        self._current_svg,
                        line,
                        f'<{tag} font-size="{attr_map["font-size"]}">',
                        "font-size",
                        size_px,
                    )
                )

        # Track document-wide <style> (including <svg><style>) and HTML containers.
        if tag == "style":
            self._in_style = True
            media = (attr_map.get("media") or "").strip().lower()
            # A <noscript> stylesheet applies only with scripting disabled.
            self._style_blocks.append(
                (line, [], media not in ("", "all") or self._noscript_depth > 0)
            )
        elif tag == "noscript":
            self._noscript_depth += 1
        elif tag == "script" and self._svg_depth == 0:
            self._in_script = True
        elif tag == "template":
            self._template_depth += 1

        if self._svg_depth == 0:
            if tag == "section":
                self._section_counter += 1
                sec = SectionInfo(
                    index=self._section_counter,
                    line=line,
                    section_id=attr_map.get("id", "").strip(),
                )
                self._section_stack.append(sec)
                self.sections.append(sec)
            elif tag == "figure":
                self._figure_counter += 1
                self._figure_stack.append(self._figure_counter)
                for sec in self._section_stack:
                    sec.has_figure = True

        if not (is_html_context and tag in VOID_HTML_ELEMENTS):
            self._node_stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        in_html_context = self._svg_depth == 0 or self._in_foreign_object()
        if in_html_context and tag in VOID_HTML_ELEMENTS:
            return
        if not any(n.tag == tag for n in self._node_stack):
            return

        while self._node_stack:
            popped = self._node_stack.pop()
            self._on_close_node(popped)
            if popped.tag == tag:
                break

    def _on_close_node(self, node: DomNode) -> None:
        tag = node.tag
        if tag == "style":
            self._in_style = False
        elif tag == "script":
            self._in_script = False
        elif tag == "template" and self._template_depth > 0:
            self._template_depth -= 1
        elif tag == "noscript" and self._noscript_depth > 0:
            self._noscript_depth -= 1

        if tag == "svg" and self._svg_depth > 0:
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None
                self._svg_non_render_depth = 0
                self._svg_text_depth = 0
                self._svg_text_chunks = []
            return

        if self._svg_depth > 0:
            if node.in_foreign_object:
                if tag == "foreignobject" or tag in BLOCK_HTML_ELEMENTS:
                    self._flush_html_text_block()
                return
            if tag in NON_RENDERING_SVG_CONTAINERS and self._svg_non_render_depth > 0:
                self._svg_non_render_depth -= 1
            if tag == "text" and self._svg_text_depth > 0:
                self._svg_text_depth -= 1
                if self._svg_text_depth == 0:
                    joined = "".join(self._svg_text_chunks)
                    if joined.strip() and not node.in_hidden:
                        self.svg_text_nodes.append(
                            TextBlock(
                                location=f"line {self._svg_text_line}, SVG <text>",
                                text=joined,
                            )
                        )
                    self._svg_text_chunks = []
            return

        if tag in BLOCK_HTML_ELEMENTS:
            self._flush_html_text_block()
            if self._section_stack and not self._figure_stack and not node.in_hidden:
                for sec in self._section_stack:
                    sec.outside_chunks.append(" ")

        if tag == "figure" and self._figure_stack:
            self._figure_stack.pop()
        elif tag == "section" and self._section_stack:
            self._section_stack.pop()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._in_style:
            if self._style_blocks:
                self._style_blocks[-1][1].append(data)
            return
        if self._in_script or self._template_depth > 0 or self._in_hidden_subtree():
            return

        if self._svg_depth > 0:
            if self._in_foreign_object():
                if not self._cur_html_chunks and data.strip():
                    self._cur_html_line, _ = self.getpos()
                self._cur_html_chunks.append(data)
                return
            if self._svg_text_depth > 0:
                self._svg_text_chunks.append(data)
            return

        # Visible HTML text outside <style>, <script>, <template>, [hidden], <svg>.
        if not self._cur_html_chunks and data.strip():
            self._cur_html_line, _ = self.getpos()
        self._cur_html_chunks.append(data)

        if self._section_stack and not self._figure_stack:
            for sec in self._section_stack:
                sec.outside_chunks.append(data)

    def finalize(self) -> None:
        """Flush remaining state and run cross-element and stylesheet checks."""
        self._flush_html_text_block()
        self._check_svgs()
        self._check_dual_layout_parity()
        self._check_inline_svg_fonts()
        self._check_stylesheets()
        self._check_sections()
        self._check_forbidden_terms()

    def _check_svgs(self) -> None:
        for svg in self.svgs:
            if svg.is_hidden_defs_only:
                continue
            loc = f"line {svg.line}, <svg> #{svg.index}"
            role = svg.attrs.get("role", "").strip()
            if role != "img":
                self._add_failure(
                    location=loc,
                    check="svg-accessibility",
                    problem=f"Diagram <svg> has role={role!r} instead of 'img'.",
                    expected='Every visible diagram <svg> must declare role="img".',
                    fix=f'Add role="img" to <svg> at line {svg.line} (or mark a definition-only <svg> with aria-hidden="true" and keep only <defs>).',
                )
            aria_label = svg.attrs.get("aria-label", "").strip()
            if not aria_label:
                self._add_failure(
                    location=loc,
                    check="svg-accessibility",
                    problem="Diagram <svg> is missing a non-empty aria-label.",
                    expected="Every visible diagram <svg> must provide a descriptive, non-empty aria-label.",
                    fix=f'Add a concise, descriptive aria-label="..." summarizing the diagram on <svg> at line {svg.line}.',
                )
            if "viewbox" not in svg.attrs:
                self._add_failure(
                    location=loc,
                    check="svg-viewbox",
                    problem="Diagram <svg> is missing a viewBox attribute.",
                    expected='Every visible diagram <svg> must define viewBox="minX minY width height" with finite numbers and width > 0, height > 0.',
                    fix=f'Add a valid viewBox="0 0 <width> <height>" matching the diagram coordinate system on <svg> at line {svg.line}.',
                )
            else:
                ok, reason = _validate_viewbox(svg.attrs["viewbox"])
                if not ok:
                    self._add_failure(
                        location=loc,
                        check="svg-viewbox",
                        problem=f"Invalid viewBox on diagram <svg>: {reason}.",
                        expected='viewBox must contain 4 finite numbers "minX minY width height" with width > 0 and height > 0.',
                        fix=f"Replace viewBox on <svg> at line {svg.line} with 4 finite numbers where width > 0 and height > 0.",
                    )

    def _check_dual_layout_parity(self) -> None:
        by_figure: dict[int, list[SvgInfo]] = {}
        for svg in self.svgs:
            if svg.is_hidden_defs_only or svg.figure_index is None:
                continue
            by_figure.setdefault(svg.figure_index, []).append(svg)

        for fig_idx, fig_svgs in sorted(by_figure.items()):
            if len(fig_svgs) < 2:
                continue
            labeled = [
                (svg, " ".join(svg.attrs.get("aria-label", "").split()))
                for svg in fig_svgs
                if svg.attrs.get("aria-label", "").strip()
            ]
            if len(labeled) < 2:
                continue
            baseline_svg, baseline_label = labeled[0]
            for other_svg, other_label in labeled[1:]:
                if other_label != baseline_label:
                    self._add_failure(
                        location=(
                            f"<figure> #{fig_idx} (<svg> #{baseline_svg.index} line "
                            f"{baseline_svg.line} vs <svg> #{other_svg.index} line {other_svg.line})"
                        ),
                        check="svg-parity",
                        problem=(
                            f"Dual-layout SVGs in <figure> #{fig_idx} have mismatched aria-label text "
                            f"(first: {baseline_label[:60]!r}, other: {other_label[:60]!r})."
                        ),
                        expected="All diagram <svg> variants inside the same <figure> must share matching non-empty aria-label text (ignoring whitespace differences).",
                        fix="Synchronize the aria-label values across the wide and narrow <svg> variants in this <figure>.",
                    )

    def _check_inline_svg_fonts(self) -> None:
        for svg, line, elem_desc, prop, size_px in self._inline_svg_fonts:
            if svg.is_hidden_defs_only:
                continue
            floor = self.config.min_narrow_font if svg.is_narrow else self.config.min_wide_font
            layout_kind = "narrow" if svg.is_narrow else "wide/default"
            if size_px + 1e-9 < floor:
                self._add_failure(
                    location=f"line {line}, {elem_desc}",
                    check="svg-font-size",
                    problem=(
                        f"Inline SVG {prop} is {_fmt_num(size_px)}px inside a {layout_kind} <svg>, "
                        f"below the {_fmt_num(floor)}px minimum."
                    ),
                    expected=f"SVG font sizes in {layout_kind} layouts must be at least {_fmt_num(floor)}px.",
                    fix=(
                        f"Raise {prop} on {elem_desc} to at least {_fmt_num(floor)}px "
                        f"(or adjust --min-{'narrow' if svg.is_narrow else 'wide'}-font if a smaller floor is intended)."
                    ),
                )

    def _svg_text_related_nodes(self) -> list[DomNode]:
        return [
            node
            for node in self.all_nodes
            if node.svg_owner is not None
            and not node.svg_owner.is_hidden_defs_only
            and not node.in_non_render_svg
            and not node.in_foreign_object
            and (node.tag in ("svg", "text", "tspan", "textpath") or node.has_svg_text_descendant)
        ]

    def _classify_svg_font_layouts(
        self,
        sel: str,
        parsed: ParsedSelector | None,
        svg_text_nodes: list[DomNode],
        diagram_svgs: list[SvgInfo],
    ) -> list[str]:
        """Return matched SVG layout categories (subset of ['wide_svg', 'narrow_svg']) or [] for HTML."""
        # 1. Primary: match against actual visible SVG text-bearing/inheriting DOM nodes.
        if parsed is not None and svg_text_nodes:
            matched_svgs = {
                node.svg_owner.index: node.svg_owner
                for node in svg_text_nodes
                if node.svg_owner is not None and selector_matches(parsed, node)
            }
            if matched_svgs:
                layouts: list[str] = []
                if any(not svg.is_narrow for svg in matched_svgs.values()):
                    layouts.append("wide_svg")
                if any(svg.is_narrow for svg in matched_svgs.values()):
                    layouts.append("narrow_svg")
                return layouts

        # 2. Fallback for unmatched SVG-explicit selectors (e.g. declared SVG rules without
        #    matching instances in a minimal snippet).
        has_narrow_attr = bool(NARROW_ATTR_PATTERN.search(sel))
        has_wide_attr = bool(WIDE_ATTR_PATTERN.search(sel))
        stripped = _strip_attribute_selectors(sel)
        if not SVG_TYPE_SELECTOR_PATTERN.search(stripped):
            return []

        has_narrow_class = bool(NARROW_CLASS_PATTERN.search(stripped))
        has_wide_class = bool(WIDE_CLASS_PATTERN.search(stripped))
        if has_narrow_attr or has_narrow_class:
            return ["narrow_svg"]
        if has_wide_attr or has_wide_class:
            return ["wide_svg"]
        if diagram_svgs:
            layouts = []
            if any(not svg.is_narrow for svg in diagram_svgs):
                layouts.append("wide_svg")
            if any(svg.is_narrow for svg in diagram_svgs):
                layouts.append("narrow_svg")
            return layouts
        return ["wide_svg"]

    def _check_svg_font_sizes(
        self,
        font_decls: list[tuple[str, ParsedSelector | None, float, CssDeclaration, bool, int, bool]],
        svg_text_nodes: list[DomNode],
        diagram_svgs: list[SvgInfo],
    ) -> None:
        floors = {"wide_svg": self.config.min_wide_font, "narrow_svg": self.config.min_narrow_font}
        for sel, parsed, size_px, decl, _conditional, order, layered in font_decls:
            kinds = self._classify_svg_font_layouts(
                sel=sel,
                parsed=parsed,
                svg_text_nodes=svg_text_nodes,
                diagram_svgs=diagram_svgs,
            )
            for kind in kinds:
                floor = floors[kind]
                if size_px + 1e-9 >= floor:
                    continue
                if parsed is not None and not layered and not self._unresolved_font_size and self._font_size_overridden(
                    parsed, decl.important, order, kind, floor, font_decls, svg_text_nodes
                ):
                    continue
                is_narrow = kind == "narrow_svg"
                layout_label = "narrow" if is_narrow else "wide/default"
                self._add_failure(
                    location=f"line {decl.line}, CSS `{sel}` ({decl.name})",
                    check="svg-font-size",
                    problem=(
                        f"CSS selector `{sel}` sets SVG {decl.name} to "
                        f"{_fmt_num(size_px)}px for a {layout_label} layout, "
                        f"below the {_fmt_num(floor)}px minimum."
                    ),
                    expected=f"SVG font sizes in {layout_label} layouts must be at least {_fmt_num(floor)}px.",
                    fix=(
                        f"Increase {decl.name} for `{sel}` to at least {_fmt_num(floor)}px. "
                        f"If the rule is meant for another layout, scope its selector to that "
                        f"layout, for example `svg.narrow text`, or "
                        + (
                            "move it out of @layer and "
                            if layered
                            else ""
                        )
                        + f"set this layout's size in a "
                        f"rule that wins the cascade over it outside any at-rule block "
                        f"(or adjust --min-{'narrow' if is_narrow else 'wide'}-font if a smaller "
                        f"floor is intended)."
                    ),
                )

    @staticmethod
    def _font_size_overridden(
        parsed: ParsedSelector,
        important: bool,
        order: int,
        kind: str,
        floor: float,
        font_decls: list[tuple[str, ParsedSelector | None, float, CssDeclaration, bool, int, bool]],
        svg_text_nodes: list[DomNode],
    ) -> bool:
        """True when every node of this layout that the rule sets also gets a font size at or
        above the floor from an unconditional rule that wins the cascade over it. The caller
        never asks this for a declaration inside @layer, whose cascade layer this does not model,
        or when a font size uses var(), whose value this does not resolve."""
        # The checker models neither the match set nor the specificity of a pseudo-class that
        # selector_matches does not evaluate, so a rule that uses one is never cleared.
        if not _state_independent(parsed):
            return False
        is_narrow = kind == "narrow_svg"
        nodes = [
            node
            for node in svg_text_nodes
            if node.svg_owner is not None
            and node.svg_owner.is_narrow == is_narrow
            and selector_matches(parsed, node)
        ]
        if not nodes:
            return False
        low_key = (important, parsed.specificity, order)
        winners = [
            o_parsed
            for _s, o_parsed, o_size, o_decl, o_conditional, o_order, _o_layered in font_decls
            if o_parsed is not None
            and not o_conditional
            and _state_independent(o_parsed)
            and o_size + 1e-9 >= floor
            and (o_decl.important, o_parsed.specificity, o_order) > low_key
        ]
        return all(any(selector_matches(w, node) for w in winners) for node in nodes)

    def _check_stylesheets(self) -> None:
        diagram_svgs = [svg for svg in self.svgs if not svg.is_hidden_defs_only]
        svg_text_nodes = self._svg_text_related_nodes()

        all_rules: list[CssRule] = []
        has_rm_block = False

        for start_line, chunks, block_conditional in self._style_blocks:
            css = "".join(chunks)
            if not self.config.allow_external_assets:
                for css_line, kind, url in extract_css_external_urls(css, start_line):
                    self._add_failure(
                        location=f"line {css_line}, <style> {kind}",
                        check="external-asset",
                        problem=f"Out-of-file resource URL {url!r} found in <style> {kind}.",
                        expected="Self-contained single-file <style> with no out-of-file resource URLs.",
                        fix="Remove the external CSS resource or inline it with a data: URI, or pass --allow-external-assets if external assets are intentionally required.",
                    )

            parsed_css = parse_css(css, start_line=start_line, conditional=block_conditional)
            if parsed_css.has_reduced_motion_block:
                has_rm_block = True
            all_rules.extend(parsed_css.rules)

        # Collect motion/hiding sources & reduced-motion overrides, and check SVG font sizes.
        # Source entries: (raw_sel, parsed_sel, important, order, line)
        # Override entries: (raw_sel, parsed_sel, important, order)
        transition_sources: list[tuple[str, ParsedSelector | None, bool, int, int]] = []
        animation_sources: list[tuple[str, ParsedSelector | None, bool, int, int]] = []
        js_opacity_sources: list[tuple[str, ParsedSelector | None, bool, int, int]] = []

        rm_transition_overrides: list[tuple[str, ParsedSelector | None, bool, int]] = []
        rm_animation_overrides: list[tuple[str, ParsedSelector | None, bool, int]] = []
        rm_opacity_overrides: list[tuple[str, ParsedSelector | None, bool, int]] = []

        selector_cache: dict[str, ParsedSelector | None] = {}

        def get_parsed(sel: str) -> ParsedSelector | None:
            if sel not in selector_cache:
                selector_cache[sel] = parse_selector(sel)
            return selector_cache[sel]

        # Font-size entries: (raw_sel, parsed_sel, size_px, decl, conditional, order, layered)
        font_decls: list[
            tuple[str, ParsedSelector | None, float, CssDeclaration, bool, int, bool]
        ] = []

        decl_order = 0
        for rule in all_rules:
            if rule.in_reduced_motion:
                for decl in rule.declarations:
                    decl_order += 1
                    if (
                        (decl.name in ("transition", "transition-property") and _is_none_value(decl.value))
                        or (
                            decl.name == "transition-duration"
                            and _is_motion_disabled_duration(decl.value)
                        )
                    ):
                        for sel in rule.selectors:
                            rm_transition_overrides.append(
                                (sel, get_parsed(sel), decl.important, decl_order)
                            )
                    elif (
                        (decl.name in ("animation", "animation-name") and _is_none_value(decl.value))
                        or (
                            decl.name == "animation-duration"
                            and _is_motion_disabled_duration(decl.value)
                        )
                    ):
                        for sel in rule.selectors:
                            rm_animation_overrides.append(
                                (sel, get_parsed(sel), decl.important, decl_order)
                            )
                    elif decl.name == "opacity" and _is_restored_opacity(decl.value):
                        for sel in rule.selectors:
                            rm_opacity_overrides.append(
                                (sel, get_parsed(sel), decl.important, decl_order)
                            )
            else:
                for decl in rule.declarations:
                    decl_order += 1
                    if decl.name in ("transition", "transition-property", "transition-duration"):
                        if not _is_none_value(decl.value) and not (
                            decl.name == "transition-duration"
                            and _is_motion_disabled_duration(decl.value)
                        ):
                            for sel in rule.selectors:
                                transition_sources.append(
                                    (sel, get_parsed(sel), decl.important, decl_order, decl.line)
                                )
                    elif decl.name in ("animation", "animation-name", "animation-duration"):
                        if not _is_none_value(decl.value) and not (
                            decl.name == "animation-duration"
                            and _is_motion_disabled_duration(decl.value)
                        ):
                            for sel in rule.selectors:
                                animation_sources.append(
                                    (sel, get_parsed(sel), decl.important, decl_order, decl.line)
                                )
                    elif decl.name == "opacity" and _is_zero_opacity(decl.value):
                        for sel in rule.selectors:
                            if JS_CLASS_PATTERN.search(_strip_attribute_selectors(sel)):
                                js_opacity_sources.append(
                                    (sel, get_parsed(sel), decl.important, decl_order, decl.line)
                                )

            # Collect font sizes for the SVG font-size floor check (document-wide scope).
            for decl in rule.declarations:
                if decl.name not in ("font-size", "font"):
                    continue
                size_px = extract_font_size_px(decl.name, decl.value, allow_unitless=False)
                if size_px is None:
                    if "var(" in decl.value.lower():
                        self._unresolved_font_size = True
                    continue
                for sel in rule.selectors:
                    font_decls.append(
                        (
                            sel, get_parsed(sel), size_px, decl, rule.conditional,
                            len(font_decls), rule.layered,
                        )
                    )

        self._check_svg_font_sizes(font_decls, svg_text_nodes, diagram_svgs)

        self._check_reduced_motion(
            has_rm_block=has_rm_block,
            transition_sources=transition_sources,
            animation_sources=animation_sources,
            js_opacity_sources=js_opacity_sources,
            rm_transition_overrides=rm_transition_overrides,
            rm_animation_overrides=rm_animation_overrides,
            rm_opacity_overrides=rm_opacity_overrides,
        )

    def _source_covered_by_rm(
        self,
        src_sel: str,
        src_parsed: ParsedSelector | None,
        src_imp: bool,
        src_order: int,
        overrides: list[tuple[str, ParsedSelector | None, bool, int]],
    ) -> bool:
        """Return True if reduced-motion overrides cover src_sel in DOM (or structurally)."""
        if not overrides:
            return False

        src_spec = src_parsed.specificity if src_parsed is not None else (0, 0, 0)
        matched_nodes: list[DomNode] = []
        if src_parsed is not None and self.all_nodes:
            matched_nodes = [
                n for n in self.all_nodes if selector_matches(src_parsed, n, js_active=True)
            ]

        def can_win(rm_parsed: ParsedSelector | None, rm_imp: bool, rm_order: int) -> bool:
            rm_spec = rm_parsed.specificity if rm_parsed is not None else (0, 0, 0)
            return (rm_imp, rm_spec, rm_order) >= (src_imp, src_spec, src_order)

        if matched_nodes:
            for node in matched_nodes:
                covered = False
                for _, rm_parsed, rm_imp, rm_order in overrides:
                    if rm_parsed is None:
                        continue
                    if not can_win(rm_parsed, rm_imp, rm_order):
                        continue
                    if rm_parsed.is_universal_element or selector_matches(
                        rm_parsed, node, js_active=True
                    ):
                        covered = True
                        break
                if not covered:
                    return False
            return True

        # Fallback when the source selector matches 0 DOM elements in a minimal fixture.
        norm_src = _normalize_selector(src_sel)
        for rm_sel, rm_parsed, rm_imp, rm_order in overrides:
            if not can_win(rm_parsed, rm_imp, rm_order):
                continue
            if _normalize_selector(rm_sel) == norm_src:
                return True
            if rm_parsed is not None and src_parsed is not None:
                if _selector_structurally_covers(rm_parsed, src_parsed):
                    return True
        return False

    def _inline_motion_covered(
        self,
        node: DomNode,
        overrides: list[tuple[str, ParsedSelector | None, bool, int]],
    ) -> bool:
        for _, rm_parsed, rm_imp, _ in overrides:
            if not rm_imp or rm_parsed is None:
                continue
            if rm_parsed.is_universal_element or selector_matches(rm_parsed, node, js_active=True):
                return True
        return False

    def _check_reduced_motion(
        self,
        has_rm_block: bool,
        transition_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        animation_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        js_opacity_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        rm_transition_overrides: list[tuple[str, ParsedSelector | None, bool, int]],
        rm_animation_overrides: list[tuple[str, ParsedSelector | None, bool, int]],
        rm_opacity_overrides: list[tuple[str, ParsedSelector | None, bool, int]],
    ) -> None:
        inline_transitions = [(n, ln) for n, ln, k in self.inline_motion_nodes if k == "transition"]
        inline_animations = [(n, ln) for n, ln, k in self.inline_motion_nodes if k == "animation"]

        if not (
            transition_sources
            or animation_sources
            or js_opacity_sources
            or inline_transitions
            or inline_animations
        ):
            return

        if not has_rm_block:
            first_loc = self._first_motion_location(
                transition_sources,
                animation_sources,
                js_opacity_sources,
                inline_transitions,
                inline_animations,
            )
            self._add_failure(
                location=first_loc,
                check="reduced-motion",
                problem="Page uses CSS transitions/animations or .js opacity-hiding without a @media (prefers-reduced-motion: reduce) block.",
                expected="Pages with CSS transitions, animations, or .js opacity-hiding must include a @media (prefers-reduced-motion: reduce) block neutralizing motion and restoring hidden .js reveal elements.",
                fix="Add `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }` and set each `.js` opacity-hidden target to `opacity: 1; transform: none;`.",
            )
            return

        # Check every transition source is neutralized.
        for sel, parsed, imp, order, line in transition_sources:
            if not self._source_covered_by_rm(sel, parsed, imp, order, rm_transition_overrides):
                self._add_failure(
                    location=f"line {line}, CSS `{sel}`",
                    check="reduced-motion",
                    problem=f"Transition on `{sel}` is not neutralized inside @media (prefers-reduced-motion: reduce).",
                    expected="Every CSS transition rule must be neutralized under @media (prefers-reduced-motion: reduce) by a matching selector with equal/higher specificity or !important (`transition: none`, `transition-property: none`, or `transition-duration: 0s`).",
                    fix=f"Add a rule inside @media (prefers-reduced-motion: reduce) covering `{sel}` (or `*, *::before, *::after`) with `transition: none !important;` or `transition-property: none;`.",
                )

        for node, line in inline_transitions:
            if not self._inline_motion_covered(node, rm_transition_overrides):
                self._add_failure(
                    location=f"line {line}, <{node.tag} style>",
                    check="reduced-motion",
                    problem=f"Inline transition on <{node.tag}> is not neutralized by an !important override in @media (prefers-reduced-motion: reduce).",
                    expected="Inline transitions must be neutralized under @media (prefers-reduced-motion: reduce) with an !important rule.",
                    fix="Add `*, *::before, *::after { transition: none !important; }` inside @media (prefers-reduced-motion: reduce), or move the transition to a CSS class.",
                )

        # Check every animation source is neutralized.
        for sel, parsed, imp, order, line in animation_sources:
            if not self._source_covered_by_rm(sel, parsed, imp, order, rm_animation_overrides):
                self._add_failure(
                    location=f"line {line}, CSS `{sel}`",
                    check="reduced-motion",
                    problem=f"Animation on `{sel}` is not neutralized inside @media (prefers-reduced-motion: reduce).",
                    expected="Every CSS animation rule must be neutralized under @media (prefers-reduced-motion: reduce) by a matching selector with equal/higher specificity or !important (`animation: none`, `animation-name: none`, or `animation-duration: 0s`).",
                    fix=f"Add a rule inside @media (prefers-reduced-motion: reduce) covering `{sel}` (or `*, *::before, *::after`) with `animation: none !important;` or `animation-name: none;`.",
                )

        for node, line in inline_animations:
            if not self._inline_motion_covered(node, rm_animation_overrides):
                self._add_failure(
                    location=f"line {line}, <{node.tag} style>",
                    check="reduced-motion",
                    problem=f"Inline animation on <{node.tag}> is not neutralized by an !important override in @media (prefers-reduced-motion: reduce).",
                    expected="Inline animations must be neutralized under @media (prefers-reduced-motion: reduce) with an !important rule.",
                    fix="Add `*, *::before, *::after { animation: none !important; }` inside @media (prefers-reduced-motion: reduce), or move the animation to a CSS class.",
                )

        # Check every .js opacity-hiding source is restored to visible opacity under reduced motion.
        for sel, parsed, imp, order, line in js_opacity_sources:
            if not self._source_covered_by_rm(sel, parsed, imp, order, rm_opacity_overrides):
                self._add_failure(
                    location=f"line {line}, CSS `{sel}`",
                    check="reduced-motion",
                    problem=f"`.js` reveal rule `{sel}` sets opacity: 0 without restoring visible opacity inside @media (prefers-reduced-motion: reduce).",
                    expected="Every `.js` opacity-hiding rule must be explicitly restored (e.g. `opacity: 1`) for that target inside @media (prefers-reduced-motion: reduce) so content cannot stay invisible.",
                    fix=f"Inside @media (prefers-reduced-motion: reduce), add `{sel} {{ opacity: 1; transform: none; }}`.",
                )

    @staticmethod
    def _first_motion_location(
        transition_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        animation_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        js_opacity_sources: list[tuple[str, ParsedSelector | None, bool, int, int]],
        inline_transitions: list[tuple[DomNode, int]],
        inline_animations: list[tuple[DomNode, int]],
    ) -> str:
        for sources in (transition_sources, animation_sources, js_opacity_sources):
            if sources:
                sel, _, _, _, line = sources[0]
                return f"line {line}, CSS `{sel}`"
        for inline in (inline_transitions, inline_animations):
            if inline:
                node, line = inline[0]
                return f"line {line}, <{node.tag} style>"
        return "<style>"

    def _check_sections(self) -> None:
        for sec in self.sections:
            if not sec.has_figure:
                continue
            text = "".join(sec.outside_chunks)
            stripped_no_ws = re.sub(r"\s+", "", text)
            if not stripped_no_ws:
                continue

            letters = sum(1 for ch in stripped_no_ws if ch.isalpha())
            cjk_chars = sum(1 for ch in stripped_no_ws if is_cjk_letter(ch))
            is_cjk_dominant = letters > 0 and (cjk_chars / letters) >= 0.25

            sec_label = f"#{sec.section_id}" if sec.section_id else f"#{sec.index}"
            loc = f"line {sec.line}, <section> {sec_label}"

            if is_cjk_dominant:
                if self.config.max_section_chars <= 0:
                    continue
                char_count = len(stripped_no_ws)
                if char_count > self.config.max_section_chars:
                    self._add_failure(
                        location=loc,
                        check="section-text-budget",
                        problem=(
                            f"Section {sec_label} has {char_count} non-whitespace characters "
                            f"outside <figure>, exceeding the CJK limit of "
                            f"{self.config.max_section_chars}."
                        ),
                        expected=f"At most {self.config.max_section_chars} non-whitespace characters outside <figure> in a CJK-dominant visual section.",
                        fix=(
                            "Trim explanatory prose outside <figure> to a brief heading, one-line lead, "
                            "and source links (move detailed notes into linked docs or diagram labels), "
                            "or adjust --max-section-chars."
                        ),
                    )
            else:
                if self.config.max_section_words <= 0:
                    continue
                word_count = len(text.split())
                if word_count > self.config.max_section_words:
                    self._add_failure(
                        location=loc,
                        check="section-text-budget",
                        problem=(
                            f"Section {sec_label} has {word_count} words outside <figure>, "
                            f"exceeding the Latin-script limit of {self.config.max_section_words}."
                        ),
                        expected=f"At most {self.config.max_section_words} words outside <figure> in a Latin-script visual section.",
                        fix=(
                            "Shorten explanatory prose outside <figure> to a concise heading, single lead "
                            "sentence, and source links (keep details in linked docs or diagram labels), "
                            "or adjust --max-section-words."
                        ),
                    )

    def _check_forbidden_terms(self) -> None:
        if not self.config.forbid:
            return

        targets: list[tuple[str, str]] = []
        for blk in self._html_text_blocks:
            targets.append((blk.location, blk.text))
        for blk in self.svg_text_nodes:
            targets.append((blk.location, blk.text))
        for loc, label in self.aria_labels:
            targets.append((loc, label))

        for term in self.config.forbid:
            term_no_ws = re.sub(r"\s+", "", term)
            for loc, content in targets:
                content_no_ws = re.sub(r"\s+", "", content)
                matched = (term in content) or (bool(term_no_ws) and term_no_ws in content_no_ws)
                if matched:
                    snippet = " ".join(content.split())
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    self._add_failure(
                        location=loc,
                        check="forbidden-term",
                        problem=f"Forbidden term {term!r} matched in {loc} ({snippet!r}).",
                        expected=f"Visible HTML text, SVG <text> (including <tspan>), and aria-label attributes must not contain {term!r}.",
                        fix=f"Replace or remove {term!r} at {loc} (check split <tspan> nodes and aria-label copies too).",
                    )


def check_html(
    html: str,
    filename: str = "<string>",
    config: CheckConfig | None = None,
) -> list[Failure]:
    """Validate an HTML document string and return all detected failures."""
    cfg = config if config is not None else CheckConfig()
    analyzer = VisualHTMLAnalyzer(filename=filename, config=cfg)
    analyzer.feed(html)
    analyzer.close()
    analyzer.finalize()
    return analyzer.failures


def check_file(path: Path, config: CheckConfig) -> list[Failure]:
    """Read and validate an HTML file from disk. Raises OSError / UnicodeDecodeError on I/O errors."""
    html = path.read_text(encoding="utf-8")
    return check_html(html, filename=str(path), config=config)


def format_text(files: Sequence[str], failures: Sequence[Failure]) -> str:
    """Format validation results as concise human/agent-readable text."""
    if not failures:
        return f"OK: checked {len(files)} file(s), 0 failure(s)."

    lines = [f"FAIL: checked {len(files)} file(s), {len(failures)} failure(s)."]
    for fail in failures:
        lines.append("")
        lines.append(f"[{fail.check}] {fail.file} ({fail.location})")
        lines.append(f"  Problem: {fail.problem}")
        lines.append(f"  Expected: {fail.expected}")
        lines.append(f"  Try: {fail.fix}")
    return "\n".join(lines)


def format_json(files: Sequence[str], failures: Sequence[Failure]) -> str:
    """Format validation results as structured JSON."""
    payload = {
        "ok": len(failures) == 0,
        "files": list(files),
        "failures": [f.to_dict() for f in failures],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="check_visual_html.py",
        description="Validate self-contained visual HTML documents with embedded inline SVGs.",
    )
    parser.add_argument(
        "files",
        metavar="HTML_FILE",
        nargs="+",
        help="Path(s) to HTML file(s) to validate.",
    )
    parser.add_argument(
        "--min-wide-font",
        type=float,
        default=14.0,
        help="Minimum SVG font size in px for wide/default SVGs (default: 14.0).",
    )
    parser.add_argument(
        "--min-narrow-font",
        type=float,
        default=12.5,
        help="Minimum SVG font size in px for narrow SVGs (default: 12.5).",
    )
    parser.add_argument(
        "--max-section-chars",
        type=int,
        default=220,
        help="Max non-whitespace chars outside <figure> in CJK-dominant <section> (0 disables; default: 220).",
    )
    parser.add_argument(
        "--max-section-words",
        type=int,
        default=65,
        help="Max words outside <figure> in Latin-dominant <section> (0 disables; default: 65).",
    )
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        metavar="TEXT",
        help="Forbidden/retired text checked in visible HTML, SVG <text>/<tspan>, and aria-label (repeatable).",
    )
    parser.add_argument(
        "--allow-external-assets",
        action="store_true",
        help="Opt out of offline single-file resource checks.",
    )
    parser.add_argument(
        "--allow-foreign-object",
        action="store_true",
        help="Opt out of SVG <foreignObject> prohibition.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format: text or json (default: text).",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> str | None:
    if not math.isfinite(args.min_wide_font) or args.min_wide_font < 0:
        return (
            f"Invalid --min-wide-font value {args.min_wide_font!r}. "
            "Expected a finite non-negative number (e.g. 14.0). "
            "Try passing --min-wide-font 14.0."
        )
    if not math.isfinite(args.min_narrow_font) or args.min_narrow_font < 0:
        return (
            f"Invalid --min-narrow-font value {args.min_narrow_font!r}. "
            "Expected a finite non-negative number (e.g. 12.5). "
            "Try passing --min-narrow-font 12.5."
        )
    if args.max_section_chars < 0:
        return (
            f"Invalid --max-section-chars value {args.max_section_chars!r}. "
            "Expected a non-negative integer (0 disables). "
            "Try passing --max-section-chars 220 or 0."
        )
    if args.max_section_words < 0:
        return (
            f"Invalid --max-section-words value {args.max_section_words!r}. "
            "Expected a non-negative integer (0 disables). "
            "Try passing --max-section-words 65 or 0."
        )
    for term in args.forbid:
        if not term:
            return (
                "Empty string passed to --forbid. "
                "Expected a non-empty string to forbid. "
                "Try omitting empty --forbid flags or specifying the exact retired term."
            )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning exit code 0 (pass), 1 (failure), or 2 (usage/I/O error)."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    arg_err = _validate_args(args)
    if arg_err is not None:
        print(f"ERROR: {arg_err}", file=sys.stderr)
        return 2

    config = CheckConfig(
        min_wide_font=args.min_wide_font,
        min_narrow_font=args.min_narrow_font,
        max_section_chars=args.max_section_chars,
        max_section_words=args.max_section_words,
        forbid=tuple(args.forbid),
        allow_external_assets=args.allow_external_assets,
        allow_foreign_object=args.allow_foreign_object,
    )

    all_failures: list[Failure] = []
    file_strs: list[str] = []

    for raw_path in args.files:
        path = Path(raw_path)
        try:
            st = path.stat()
        except FileNotFoundError:
            print(
                f"ERROR: Input file not found: {raw_path}\n"
                "  Expected: An existing UTF-8 HTML file path.\n"
                "  Try: Check the file path or run from the repository root.",
                file=sys.stderr,
            )
            return 2
        except (OSError, ValueError) as exc:
            print(
                f"ERROR: Could not access {raw_path}: {exc}\n"
                "  Expected: A valid, accessible UTF-8 HTML file path.\n"
                "  Try: Verify the path length, characters, and file permissions.",
                file=sys.stderr,
            )
            return 2

        if not stat.S_ISREG(st.st_mode):
            print(
                f"ERROR: Input path is not a regular file: {raw_path}\n"
                "  Expected: A path to an HTML file, not a directory or special file.\n"
                "  Try: Pass explicit .html file paths (e.g. docs/overview.html).",
                file=sys.stderr,
            )
            return 2

        try:
            failures = check_file(path, config)
        except (OSError, UnicodeDecodeError) as exc:
            print(
                f"ERROR: Could not read {raw_path}: {exc}\n"
                "  Expected: A readable UTF-8 encoded HTML file.\n"
                "  Try: Verify file permissions and ensure the file is valid UTF-8.",
                file=sys.stderr,
            )
            return 2
        file_strs.append(str(path))
        all_failures.extend(failures)

    output = (
        format_json(file_strs, all_failures)
        if args.format == "json"
        else format_text(file_strs, all_failures)
    )
    print(output)
    return 0 if not all_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
