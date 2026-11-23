#!/usr/bin/env python3
"""Unit tests for check_visual_html.py (Python 3 standard library only)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "check_visual_html.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_visual_html as checker  # noqa: E402


CLEAN_DUAL_CJK_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>系统架构图解</title>
<style>
body { font: 16px/1.6 sans-serif; }
.tag { font-size: 12px; }
.num { font: 600 12px/1 monospace; }
footer { font-size: 12px; }
svg text { font-size: 15px; }
svg .ts { font-size: 14px; }
svg .nb .nbt { font: 700 14px sans-serif; }
svg.n text { font-size: 13.5px; }
svg.n .ts { font-size: 12.5px; }
svg.n .nb .nbt { font-size: 12.5px; }
.js .act:not(.in) figure { opacity: 0; transform: translateY(8px); }
.js .act figure { transition: opacity .6s ease, transform .6s ease; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .js .act:not(.in) figure { opacity: 1; transform: none; }
}
@media (max-width: 820px) {
  figure > svg.w { display: none; }
  figure > svg.n { display: block; }
}
</style>
</head>
<body>
<svg class="defs" aria-hidden="true" width="0" height="0">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5">
      <path d="M0,0 L10,5 L0,10 z" />
    </marker>
  </defs>
</svg>
<main>
  <section id="fig-1" class="act">
    <header>
      <span class="num">图 1</span>
      <h2>模块分层与数据流</h2>
      <p>请求自接口层进入，经编排层调度后落入存储层。</p>
      <span class="tag">已核实</span>
      <a href="https://example.com/spec">参考文档</a>
      <a href="sibling.html">本地导航</a>
    </header>
    <figure>
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
           viewBox="0 0 800 320" role="img"
           aria-label="模块分层图：请求经过接口层与编排层写入存储层。" class="w">
        <rect x="20" y="20" width="200" height="80" rx="8" />
        <text x="120" y="60" class="ts" font-size="14">接口层</text>
        <path d="M220 60 H300" marker-end="url(#arrow)" />
      </svg>
      <svg xmlns="http://www.w3.org/2000/svg"
           viewBox="0 0 340 420" role="img"
           aria-label="模块分层图：请求经过接口层与编排层写入存储层。" class="n">
        <rect x="16" y="16" width="308" height="72" rx="8" />
        <text x="170" y="52" class="ts" font-size="12.5">接口层</text>
      </svg>
    </figure>
  </section>
</main>
<footer><a href="https://example.com/about">说明</a></footer>
</body>
</html>
"""


CLEAN_SINGLE_EN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pipeline Overview</title>
<style>
body { font: 16px/1.5 sans-serif; }
.badge { font-size: 11px; }
svg text { font-size: 15px; }
svg .sub { font-size: 14px; }
</style>
</head>
<body>
<main>
  <section id="overview">
    <h2>Pipeline Overview</h2>
    <p>Events flow from ingestion through validation into durable storage.</p>
    <a href="https://example.com/docs">Design note</a>
    <figure>
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 -10 640 240" role="img"
           aria-label="Pipeline diagram showing ingestion, validation, and storage.">
        <rect x="0" y="0" width="160" height="60" rx="6" />
        <text x="80" y="30" class="sub">Ingestion</text>
      </svg>
    </figure>
  </section>
</main>
</body>
</html>
"""


CLEAN_DUAL_EN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Dual Layout English</title>
<style>
.meta { font-size: 12px; }
svg text { font-size: 14px; }
svg[data-layout="narrow"] text { font-size: 12.5px; }
</style>
</head>
<body>
<section id="s1">
  <h2>Service Topology</h2>
  <p>Gateways route traffic to stateless workers backed by a shared queue.</p>
  <figure>
    <svg viewBox="0 0 900 300" role="img" aria-label="Topology: gateway to workers and queue.">
      <rect x="10" y="10" width="120" height="60" />
      <text x="70" y="40">Gateway</text>
    </svg>
    <svg viewBox="0 0 340 480" role="img" data-layout="narrow"
         aria-label="Topology:  gateway\n to workers and queue.">
      <rect x="10" y="10" width="120" height="60" />
      <text x="70" y="40">Gateway</text>
    </svg>
  </figure>
</section>
</body>
</html>
"""


class TestVisualHtmlChecker(unittest.TestCase):
    """Test suite covering all validation rules and CLI contracts."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_temp(self, tmpdir: str, name: str, content: str) -> Path:
        path = Path(tmpdir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_clean_dual_layout_cjk_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_file = self._write_temp(tmp, "cjk.html", CLEAN_DUAL_CJK_HTML)
            proc = self._run_cli(str(html_file))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("OK:", proc.stdout)

    def test_clean_single_and_dual_english_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            single = self._write_temp(tmp, "single.html", CLEAN_SINGLE_EN_HTML)
            dual = self._write_temp(tmp, "dual.html", CLEAN_DUAL_EN_HTML)
            proc = self._run_cli(str(single), str(dual))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("checked 2 file(s), 0 failure(s)", proc.stdout)

    def test_external_assets_remote_relative_svg_paint_srcset_and_css_content(self) -> None:
        html = """<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="https://cdn.example.com/site.css">
  <link rel="stylesheet" href="./local-theme.css">
  <link rel="canonical" href="https://example.com/page">
  <script src="//cdn.example.com/app.js"></script>
  <script src="assets/local.js"></script>
  <style>
    /* ignored comment: url(https://ignored.example.com/x.png) */
    @import url("https://fonts.example.com/css2?family=Sans");
    @import "partials/tokens.css";
    .bg { background: url(http://cdn.example.com/bg.png); }
    .local-bg { background: url(./pattern.png); }
    .ok-data { background: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>"); }
    .literal-content::after { content: "See url(https://not-loaded.example.com/x.png) and @import 'nope.css'"; }
  </style>
</head>
<body>
  <a href="https://example.com/nav">External link allowed</a>
  <a href="other-page.html">Relative nav link allowed</a>
  <img src="https://cdn.example.com/pic.png"
       srcset="data:image/png;base64,AAAA, https://cdn.example.com/pic2.png 2x">
  <img src="images/local-diagram.png">
  <iframe src="https://example.com/embed"></iframe>
  <div style="background-image: url('https://cdn.example.com/inline.png')"></div>
  <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
       viewBox="0 0 100 100" role="img" aria-label="Sample">
    <image href="https://cdn.example.com/svg.png" xlink:href="https://cdn.example.com/svg2.png" />
    <rect x="0" y="0" width="20" height="20"
          fill="url(defs.svg#grad)" stroke="url(https://cdn.example.com/p.svg#s)"
          filter="url(fx.svg#blur)" clip-path="url(clips.svg#c)" mask="url(masks.svg#m)" />
    <path d="M0 0 L10 10" marker-end="url(arrows.svg#tip)" marker-start="url(#local-marker)" />
    <use href="#local-symbol" />
  </svg>
</body>
</html>
"""
        failures = checker.check_html(html, filename="ext.html")
        ext_failures = [f for f in failures if f.check == "external-asset"]
        # Expect 20 hits:
        # 1. link remote css, 2. link local css, 3. script remote, 4. script local,
        # 5. @import remote, 6. @import local, 7. .bg remote url, 8. .local-bg local url,
        # 9. img remote src, 10. img srcset after descriptorless data: URL,
        # 11. img local src, 12. iframe src, 13. inline style url,
        # 14. svg image href, 15. svg image xlink:href,
        # 16-20. svg rect fill/stroke/filter/clip-path/mask + 21. path marker-end => 21 hits!
        self.assertEqual(len(ext_failures), 21, ext_failures)
        urls_flagged = " ".join(f.problem for f in ext_failures)
        self.assertIn("local-theme.css", urls_flagged)
        self.assertIn("assets/local.js", urls_flagged)
        self.assertIn("images/local-diagram.png", urls_flagged)
        self.assertIn("pic2.png", urls_flagged)
        self.assertIn("defs.svg#grad", urls_flagged)
        self.assertIn("arrows.svg#tip", urls_flagged)
        self.assertNotIn("not-loaded.example.com", urls_flagged)
        self.assertNotIn("nope.css", urls_flagged)
        self.assertNotIn("example.com/nav", urls_flagged)
        self.assertNotIn("other-page.html", urls_flagged)
        self.assertNotIn("example.com/page", urls_flagged)
        self.assertNotIn("w3.org/2000/svg", urls_flagged)
        self.assertNotIn("ignored.example.com", urls_flagged)
        self.assertNotIn("data:image", urls_flagged)
        self.assertNotIn("#local-marker", urls_flagged)

        # Opting out with allow_external_assets clears all external-asset failures.
        cfg = checker.CheckConfig(allow_external_assets=True)
        allowed_failures = checker.check_html(html, filename="ext.html", config=cfg)
        self.assertEqual([f for f in allowed_failures if f.check == "external-asset"], [])

    def test_svg_accessibility_viewbox_and_duplicate_attrs(self) -> None:
        html = """<!doctype html>
<html><body>
  <svg class="defs" aria-hidden="true"><defs><marker id="m"><path d="M0 0L4 4"/></marker></defs></svg>
  <svg viewBox="0 0 100 100" aria-label="Missing role"><rect width="10" height="10"/></svg>
  <svg role="img" viewBox="0 0 100 100" aria-label="   "><rect width="10" height="10"/></svg>
  <svg role="img" aria-label="Bad viewBox NaN" viewBox="0 0 NaN 100"><rect width="10" height="10"/></svg>
  <svg role="img" aria-label="Non-positive viewBox" viewBox="0 0 100 0"><rect width="10" height="10"/></svg>
  <svg role="img" aria-label="Missing viewBox"><rect width="10" height="10"/></svg>
  <svg role="img" aria-label="Duplicate attrs" viewBox="0 0 100 100" class="a" class="b">
    <rect x="0" x="5" y="0" width="10" height="10"/>
  </svg>
  <svg aria-hidden="true"><defs><linearGradient id="g"/></defs><rect width="10" height="10"/></svg>
</body></html>
"""
        failures = checker.check_html(html, filename="svg.html")
        checks = [f.check for f in failures]
        self.assertIn("svg-accessibility", checks)
        self.assertIn("svg-viewbox", checks)
        self.assertEqual(checks.count("svg-duplicate-attr"), 2)
        for f in failures:
            self.assertNotIn("<svg> #1", f.location)
        svg8_failures = [f for f in failures if "<svg> #8" in f.location]
        self.assertGreaterEqual(len(svg8_failures), 2)

    def test_dual_layout_aria_label_parity_and_nested_figures(self) -> None:
        mismatch_html = """<!doctype html>
<html><body>
<figure>
  <svg viewBox="0 0 800 200" role="img" aria-label="Wide overview of system" class="w">
    <rect width="10" height="10"/>
  </svg>
  <svg viewBox="0 0 340 400" role="img" aria-label="Narrow different text" class="n">
    <rect width="10" height="10"/>
  </svg>
</figure>
</body></html>
"""
        failures = checker.check_html(mismatch_html, filename="parity.html")
        self.assertEqual([f.check for f in failures], ["svg-parity"])

        ws_match_html = """<!doctype html>
<html><body>
<figure>
  <svg viewBox="0 0 800 200" role="img" aria-label="Shared   diagram\n description" class="w">
    <rect width="10" height="10"/>
  </svg>
  <svg viewBox="0 0 340 400" role="img" aria-label="Shared diagram description" class="n">
    <rect width="10" height="10"/>
  </svg>
</figure>
</body></html>
"""
        self.assertEqual(checker.check_html(ws_match_html, filename="parity_ok.html"), [])

        # Nested <figure> must form its own parity group independent of outer <figure>.
        nested_ok_html = """<!doctype html>
<html><body>
<figure>
  <svg viewBox="0 0 800 200" role="img" aria-label="Outer diagram" class="w"><rect width="10" height="10"/></svg>
  <svg viewBox="0 0 340 400" role="img" aria-label="Outer diagram" class="n"><rect width="10" height="10"/></svg>
  <figure>
    <svg viewBox="0 0 400 200" role="img" aria-label="Inner diagram" class="w"><rect width="10" height="10"/></svg>
    <svg viewBox="0 0 240 300" role="img" aria-label="Inner diagram" class="n"><rect width="10" height="10"/></svg>
  </figure>
</figure>
</body></html>
"""
        self.assertEqual(checker.check_html(nested_ok_html, filename="nested_ok.html"), [])

        nested_mismatch_html = """<!doctype html>
<html><body>
<figure>
  <svg viewBox="0 0 800 200" role="img" aria-label="Outer diagram"><rect width="10" height="10"/></svg>
  <figure>
    <svg viewBox="0 0 400 200" role="img" aria-label="Inner wide" class="w"><rect width="10" height="10"/></svg>
    <svg viewBox="0 0 240 300" role="img" aria-label="Inner narrow mismatch" class="n"><rect width="10" height="10"/></svg>
  </figure>
</figure>
</body></html>
"""
        nested_failures = checker.check_html(nested_mismatch_html, filename="nested_bad.html")
        self.assertEqual([f.check for f in nested_failures], ["svg-parity"])
        self.assertIn("<figure> #2", nested_failures[0].location)

    def test_svg_font_size_floors_css_and_inline(self) -> None:
        html = """<!doctype html>
<html>
<head>
<style>
  .tag { font-size: 11px; }
  footer { font-size: 12px; }
  .num { font: 600 12px/1 monospace; }
  input[type="text"] { font-size: 11px; }
  .narrow { font-size: 11px; }
  svg text, svg .ok { font-size: 14px; }
  svg .too-small { font-size: 13.5px; }
  svg .shorthand-small { font: 700 13px/1.2 sans-serif; }
  svg.n .ok-narrow, .n text { font-size: 12.5px; }
  @media (max-width: 820px) {
    svg.n .too-small-narrow, svg[data-layout="narrow"] .sub { font-size: 12px; }
  }
</style>
</head>
<body>
  <div class="narrow">HTML narrow text allowed at 11px</div>
  <figure>
    <svg viewBox="0 0 600 200" role="img" aria-label="Diagram" class="w">
      <text x="10" y="20" font-size="14">OK wide</text>
      <text x="10" y="40" font-size="13">Too small wide attr</text>
      <text x="10" y="60" style="font-size: 12px">Too small wide style</text>
    </svg>
    <svg viewBox="0 0 340 300" role="img" aria-label="Diagram" class="n">
      <text x="10" y="20" font-size="12.5">OK narrow</text>
      <text x="10" y="40" font-size="12">Too small narrow attr</text>
      <text x="10" y="60" style="font: 600 11.5px sans-serif">Too small narrow style</text>
    </svg>
  </figure>
</body>
</html>
"""
        failures = checker.check_html(html, filename="fonts.html")
        font_failures = [f for f in failures if f.check == "svg-font-size"]
        self.assertEqual(len(font_failures), 8, font_failures)
        joined = "\n".join(f.location for f in font_failures)
        self.assertNotIn(".tag", joined)
        self.assertNotIn("footer", joined)
        self.assertNotIn(".num", joined)
        self.assertNotIn("input", joined)
        self.assertNotIn("`.narrow`", joined)

    def test_svg_font_class_rule_unitless_zero_narrow_only_and_doc_wide_svg_style(self) -> None:
        # 1. Plain `.label` class applied to SVG <text> and unitless `font-size: 0` both fail.
        class_and_zero_html = """<!doctype html>
<html>
<head><style>
  .label { font-size: 12px; }
  .zero-lbl { font-size: 0; }
</style></head>
<body>
  <svg viewBox="0 0 400 200" role="img" aria-label="Class font test">
    <text x="10" y="30" class="label">Undersized class label</text>
    <text x="10" y="60" class="zero-lbl">Zero font</text>
  </svg>
</body>
</html>
"""
        failures = checker.check_html(class_and_zero_html, filename="class_zero.html")
        self.assertEqual([f.check for f in failures], ["svg-font-size", "svg-font-size"])

        # 2. Generic `svg text` at 13px PASSES on a narrow-only page, but FAILS on single-layout wide page.
        narrow_only_html = """<!doctype html>
<html>
<head><style>svg text { font-size: 13px; }</style></head>
<body>
  <svg class="n" viewBox="0 0 340 200" role="img" aria-label="Narrow only">
    <text x="10" y="30">Narrow text at 13px</text>
  </svg>
</body>
</html>
"""
        self.assertEqual(checker.check_html(narrow_only_html, filename="narrow_only.html"), [])

        single_wide_html = """<!doctype html>
<html>
<head><style>svg text { font-size: 13px; }</style></head>
<body>
  <svg viewBox="0 0 600 200" role="img" aria-label="Single layout">
    <text x="10" y="30">Single-layout text at 13px</text>
  </svg>
</body>
</html>
"""
        single_failures = checker.check_html(single_wide_html, filename="single_wide.html")
        self.assertEqual([f.check for f in single_failures], ["svg-font-size"])

        # 3. <style> inside a narrow inline <svg> applies document-wide, including to a wide <svg>.
        doc_wide_style_html = """<!doctype html>
<html><body>
  <figure>
    <svg class="n" viewBox="0 0 340 200" role="img" aria-label="Shared style">
      <style>.shared-lbl { font-size: 13px; }</style>
      <text x="10" y="30" class="shared-lbl">Narrow</text>
    </svg>
    <svg class="w" viewBox="0 0 700 200" role="img" aria-label="Shared style">
      <text x="10" y="30" class="shared-lbl">Wide affected by doc-wide SVG style</text>
    </svg>
  </figure>
</body></html>
"""
        doc_wide_failures = checker.check_html(doc_wide_style_html, filename="doc_wide_svg_style.html")
        self.assertEqual([f.check for f in doc_wide_failures], ["svg-font-size"])

    def test_svg_embedded_style_font_size(self) -> None:
        html = """<!doctype html>
<html><body>
  <svg viewBox="0 0 400 200" role="img" aria-label="Inline style SVG">
    <style>.lbl { font-size: 11px; }</style>
    <text x="10" y="30" class="lbl">Small</text>
  </svg>
</body></html>
"""
        failures = checker.check_html(html, filename="svg_style.html")
        self.assertEqual([f.check for f in failures], ["svg-font-size"])

    def test_section_text_budget_cjk_english_halfwidth_kana_and_punctuation(self) -> None:
        long_cjk = "架构演进说明" * 45  # 270 non-whitespace CJK chars (> 220)
        long_en = " ".join(f"word{i}" for i in range(80))  # 80 words (> 65)
        long_halfwidth_kana = "ｱｲｳｴｵ" * 44 + "ｱ"  # 221 halfwidth kana (> 220)
        # Latin text with many katakana middle dots (punctuation) must stay Latin-dominant.
        latin_with_cjk_punct = " ".join(["Alpha・・・"] * 25)  # 25 words (<= 65), 250+ chars if misclassified
        huge_figure_text = " ".join(f"diagramlabel{i}" for i in range(200))

        html = f"""<!doctype html>
<html><body>
  <section id="cjk-over">
    <h2>标题</h2>
    <p>{long_cjk}</p>
    <figure>
      <svg viewBox="0 0 400 200" role="img" aria-label="CJK diagram">
        <text x="10" y="30">{long_cjk}</text>
      </svg>
    </figure>
  </section>
  <section id="en-over">
    <h2>Heading</h2>
    <p>{long_en}</p>
    <figure>
      <svg viewBox="0 0 400 200" role="img" aria-label="EN diagram">
        <text x="10" y="30">{huge_figure_text}</text>
      </svg>
    </figure>
  </section>
  <section id="hw-kana-over">
    <p>{long_halfwidth_kana}</p>
    <figure>
      <svg viewBox="0 0 400 200" role="img" aria-label="Halfwidth kana diagram">
        <text x="10" y="30">OK</text>
      </svg>
    </figure>
  </section>
  <section id="cjk-punct-latin-ok">
    <p>{latin_with_cjk_punct}</p>
    <figure>
      <svg viewBox="0 0 400 200" role="img" aria-label="Latin with punctuation">
        <text x="10" y="30">OK</text>
      </svg>
    </figure>
  </section>
  <section id="figure-text-excluded">
    <h2>Brief Title</h2>
    <p>Short lead sentence.</p>
    <figure>
      <svg viewBox="0 0 400 200" role="img" aria-label="Diagram with long caption">
        <text x="10" y="30">{huge_figure_text}</text>
      </svg>
      <figcaption>{huge_figure_text}</figcaption>
    </figure>
  </section>
  <section id="no-figure-prose">
    <p>{long_en}</p>
  </section>
</body></html>
"""
        failures = checker.check_html(html, filename="budget.html")
        budget_failures = [f for f in failures if f.check == "section-text-budget"]
        self.assertEqual(len(budget_failures), 3, budget_failures)
        locs = " ".join(f.location for f in budget_failures)
        self.assertIn("#cjk-over", locs)
        self.assertIn("#en-over", locs)
        self.assertIn("#hw-kana-over", locs)
        self.assertNotIn("#cjk-punct-latin-ok", locs)
        self.assertNotIn("#figure-text-excluded", locs)
        self.assertNotIn("#no-figure-prose", locs)

        # Disabling both caps with 0 suppresses all budget failures.
        cfg = checker.CheckConfig(max_section_chars=0, max_section_words=0)
        self.assertEqual(checker.check_html(html, filename="budget.html", config=cfg), [])

    def test_foreign_object_and_svg_script(self) -> None:
        html = """<!doctype html>
<html><body>
  <svg viewBox="0 0 400 200" role="img" aria-label="Unsafe SVG">
    <foreignObject x="0" y="0" width="100" height="40"><div>HTML</div></foreignObject>
    <script>console.log("bad");</script>
  </svg>
</body></html>
"""
        failures = checker.check_html(html, filename="unsafe.html")
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(f.check == "svg-forbidden-element" for f in failures))

        # --allow-foreign-object allows foreignObject but NEVER allows <script> inside <svg>.
        cfg = checker.CheckConfig(allow_foreign_object=True)
        after = checker.check_html(html, filename="unsafe.html", config=cfg)
        self.assertEqual(len(after), 1)
        self.assertIn("<script>", after[0].problem)

    def test_reduced_motion_safety_and_js_reveal_restoration(self) -> None:
        # Missing @media (prefers-reduced-motion: reduce)
        missing_rm = """<!doctype html>
<html><head><style>
  .card { transition: opacity 0.4s ease; }
</style></head><body><div class="card">Hello</div></body></html>
"""
        self.assertEqual(
            [f.check for f in checker.check_html(missing_rm, filename="motion.html")],
            ["reduced-motion"],
        )

        # Unrelated selector in reduced-motion must NOT satisfy .card transition override.
        unrelated_rm = """<!doctype html>
<html><head><style>
  .card { transition: opacity 0.4s ease; }
  @media (prefers-reduced-motion: reduce) {
    .unrelated { transition: none !important; }
  }
</style></head><body><div class="card">Hello</div><div class="unrelated">Other</div></body></html>
"""
        self.assertEqual(
            [f.check for f in checker.check_html(unrelated_rm, filename="unrelated.html")],
            ["reduced-motion"],
        )

        # .js reveal rule with opacity: 0 + transition MUST fail when reduced-motion disables transition only.
        js_hidden_without_opacity_restore = """<!doctype html>
<html><head><style>
  .js .reveal { opacity: 0; transition: opacity 0.4s ease; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition: none !important; }
  }
</style></head><body><div class="reveal">Hidden under reduced motion</div></body></html>
"""
        rm_failures = checker.check_html(js_hidden_without_opacity_restore, filename="js_hidden.html")
        self.assertEqual([f.check for f in rm_failures], ["reduced-motion"])
        self.assertIn("opacity: 0", rm_failures[0].problem)

        # .js reveal restored on an unrelated selector MUST still fail.
        js_unrelated_restore = """<!doctype html>
<html><head><style>
  .js .reveal { opacity: 0; }
  @media (prefers-reduced-motion: reduce) {
    .other { opacity: 1 !important; }
  }
</style></head><body><div class="reveal">Still hidden</div><div class="other">X</div></body></html>
"""
        self.assertEqual(
            [f.check for f in checker.check_html(js_unrelated_restore, filename="js_unrel.html")],
            ["reduced-motion"],
        )

        # Longhands `transition-property: none` and `animation-name: none` + matching opacity restore PASS.
        longhand_ok = """<!doctype html>
<html><head><style>
  .js .reveal { opacity: 0; transition: opacity 0.4s ease; animation: fade 1s ease; }
  @media (prefers-reduced-motion: reduce) {
    .js .reveal { opacity: 1; transition-property: none; animation-name: none; }
  }
</style></head><body><div class="reveal">Visible</div></body></html>
"""
        self.assertEqual(checker.check_html(longhand_ok, filename="longhand_ok.html"), [])

    def test_forbid_html_tspan_aria_label_hidden_and_foreign_object(self) -> None:
        html = """<!doctype html>
<html>
<head><style>/* OldTerm in comment ignored */</style></head>
<body>
  <!-- OldTerm in HTML comment ignored -->
  <div hidden><p>HiddenTerm</p><span aria-label="HiddenTerm">ignored</span></div>
  <p>Uses Legacy  Widget here.</p>
  <svg viewBox="0 0 400 200" role="img" aria-label="Flow for Retired\nCode path">
    <text x="10" y="30"><tspan>Old</tspan><tspan>Term</tspan></text>
    <foreignObject x="0" y="50" width="200" height="80">
      <div><p>Foreign  Term</p><span hidden>HiddenTerm</span></div>
    </foreignObject>
  </svg>
</body>
</html>
"""
        cfg = checker.CheckConfig(
            forbid=("Legacy Widget", "Old Term", "Retired Code", "Foreign Term", "HiddenTerm"),
            allow_foreign_object=True,
        )
        failures = checker.check_html(html, filename="forbid.html", config=cfg)
        self.assertEqual(len(failures), 4, failures)
        self.assertTrue(all(f.check == "forbidden-term" for f in failures))
        problems = " | ".join(f.problem for f in failures)
        self.assertIn("Legacy Widget", problems)
        self.assertIn("Old Term", problems)
        self.assertIn("Retired Code", problems)
        self.assertIn("Foreign Term", problems)
        self.assertNotIn("HiddenTerm", problems)

    def test_deep_css_nesting_does_not_hit_recursion_error(self) -> None:
        depth = 1500
        deep_css = ("@media all { " * depth) + "svg text { font-size: 12px; }" + (" }" * depth)
        html = f"""<!doctype html>
<html><head><style>{deep_css}</style></head>
<body>
  <svg viewBox="0 0 400 200" role="img" aria-label="Deep CSS test">
    <text x="10" y="30">Small</text>
  </svg>
</body></html>
"""
        failures = checker.check_html(html, filename="deep.html")
        self.assertEqual([f.check for f in failures], ["svg-font-size"])

    def test_cli_json_format_and_exit_codes_including_overlong_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok_file = self._write_temp(tmp, "ok.html", CLEAN_SINGLE_EN_HTML)
            bad_file = self._write_temp(
                tmp,
                "bad.html",
                '<html><body><svg viewBox="0 0 0 0"><foreignObject/></svg></body></html>',
            )

            # Exit 0 + valid JSON schema
            proc_ok = self._run_cli("--format", "json", str(ok_file))
            self.assertEqual(proc_ok.returncode, 0, proc_ok.stderr)
            payload_ok = json.loads(proc_ok.stdout)
            self.assertTrue(payload_ok["ok"])
            self.assertEqual(payload_ok["files"], [str(ok_file)])
            self.assertEqual(payload_ok["failures"], [])

            # Exit 1 + actionable fields in JSON and text
            proc_bad = self._run_cli("--format", "json", str(bad_file))
            self.assertEqual(proc_bad.returncode, 1)
            payload_bad = json.loads(proc_bad.stdout)
            self.assertFalse(payload_bad["ok"])
            self.assertEqual(payload_bad["files"], [str(bad_file)])
            self.assertGreaterEqual(len(payload_bad["failures"]), 4)
            for item in payload_bad["failures"]:
                for key in ("file", "location", "check", "problem", "expected", "fix"):
                    self.assertIn(key, item)
                    self.assertTrue(item[key])

            proc_bad_text = self._run_cli(str(bad_file))
            self.assertEqual(proc_bad_text.returncode, 1)
            self.assertIn("Problem:", proc_bad_text.stdout)
            self.assertIn("Expected:", proc_bad_text.stdout)
            self.assertIn("Try:", proc_bad_text.stdout)

            # Exit 2 on missing file
            missing = Path(tmp) / "does-not-exist.html"
            proc_missing = self._run_cli(str(missing))
            self.assertEqual(proc_missing.returncode, 2)
            self.assertIn("ERROR:", proc_missing.stderr)

            # Exit 2 on overlong filename (OSError ENAMETOOLONG, no traceback)
            overlong = str(Path(tmp) / ("a" * 5000 + ".html"))
            proc_overlong = self._run_cli(overlong)
            self.assertEqual(proc_overlong.returncode, 2)
            self.assertIn("ERROR:", proc_overlong.stderr)
            self.assertNotIn("Traceback", proc_overlong.stderr)

            # Exit 2 on directory path
            proc_dir = self._run_cli(tmp)
            self.assertEqual(proc_dir.returncode, 2)
            self.assertIn("ERROR:", proc_dir.stderr)

            # Exit 2 on negative threshold
            proc_neg = self._run_cli("--min-wide-font", "-1", str(ok_file))
            self.assertEqual(proc_neg.returncode, 2)
            self.assertIn("ERROR:", proc_neg.stderr)

    def test_cli_forbid_repeatable_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_file = self._write_temp(
                tmp,
                "terms.html",
                """<!doctype html>
<html><body>
  <svg viewBox="0 0 200 100" role="img" aria-label="Alpha and Beta">
    <text x="10" y="30"><tspan>Al</tspan><tspan>pha</tspan></text>
  </svg>
</body></html>
""",
            )
            proc = self._run_cli("--forbid", "Alpha", "--forbid", "Beta", "--format", "json", str(html_file))
            self.assertEqual(proc.returncode, 1)
            data = json.loads(proc.stdout)
            self.assertFalse(data["ok"])
            self.assertEqual(len(data["failures"]), 3)

    def test_r2_external_assets_input_preload_and_imageset(self) -> None:
        html = """<!doctype html>
<html>
<head>
  <link rel="preload" as="image" imagesrcset="hero-1x.png 1x, hero-2x.png 2x">
  <style>
    .bg { background-image: image-set("bg.png" 1x, "bg@2x.png" 2x); }
    .literal::after { content: 'image-set("ok.png" 1x)'; }
  </style>
</head>
<body>
  <input type="image" src="submit.png" alt="Submit">
  <svg viewBox="0 0 200 100" role="img" aria-label="Test">
    <text x="10" y="30" font-size="14">OK</text>
  </svg>
</body>
</html>
"""
        failures = checker.check_html(html, filename="ext_r2.html")
        ext_failures = [f for f in failures if f.check == "external-asset"]
        problems = "\n".join(f.problem for f in ext_failures)
        self.assertIn("hero-1x.png", problems)
        self.assertIn("hero-2x.png", problems)
        self.assertIn("bg.png", problems)
        self.assertIn("bg@2x.png", problems)
        self.assertIn("submit.png", problems)
        self.assertNotIn("ok.png", problems)

    def test_r2_dual_layout_custom_narrow_floor(self) -> None:
        html = """<!doctype html>
<html>
<head><style>svg text { font-size: 14px; }</style></head>
<body>
  <figure>
    <svg class="wide" viewBox="0 0 800 200" role="img" aria-label="Dual">
      <text x="10" y="30">Wide</text>
    </svg>
    <svg class="narrow" viewBox="0 0 320 200" role="img" aria-label="Dual">
      <text x="10" y="30">Narrow</text>
    </svg>
  </figure>
</body>
</html>
"""
        cfg = checker.CheckConfig(min_wide_font=14.0, min_narrow_font=16.0)
        failures = checker.check_html(html, filename="narrow_floor.html", config=cfg)
        font_failures = [f for f in failures if f.check == "svg-font-size"]
        self.assertEqual(len(font_failures), 1)
        self.assertIn("narrow", font_failures[0].problem)

    def test_r2_reduced_motion_cascade_negated_media_and_percent_opacity(self) -> None:
        # 1. Lower-specificity !important must NOT beat higher-specificity !important.
        html_spec = """<!doctype html>
<html>
<head><style>
  .js .reveal { opacity: 0 !important; }
  @media (prefers-reduced-motion: reduce) {
    * { opacity: 1 !important; }
  }
</style></head>
<body>
  <div class="reveal">Hidden</div>
  <svg viewBox="0 0 200 100" role="img" aria-label="Test"><text x="10" y="30" font-size="14">OK</text></svg>
</body>
</html>
"""
        failures = checker.check_html(html_spec, filename="rm_spec.html")
        self.assertEqual([f.check for f in failures], ["reduced-motion"])

        # 2. Negated @media not (prefers-reduced-motion: reduce) must NOT satisfy reduced motion.
        html_not = """<!doctype html>
<html>
<head><style>
  .js .reveal { opacity: 0%; }
  @media not (prefers-reduced-motion: reduce) {
    .js .reveal { opacity: 100%; }
  }
</style></head>
<body>
  <div class="reveal">Hidden</div>
  <svg viewBox="0 0 200 100" role="img" aria-label="Test"><text x="10" y="30" font-size="14">OK</text></svg>
</body>
</html>
"""
        failures_not = checker.check_html(html_not, filename="rm_not.html")
        self.assertEqual([f.check for f in failures_not], ["reduced-motion"])

        # 3. Positive percentage restoration opacity: 100% passes.
        html_pct_ok = """<!doctype html>
<html>
<head><style>
  .js .reveal { opacity: 0%; }
  @media (prefers-reduced-motion: reduce) {
    .js .reveal { opacity: 100%; }
  }
</style></head>
<body>
  <div class="reveal">Shown</div>
  <svg viewBox="0 0 200 100" role="img" aria-label="Test"><text x="10" y="30" font-size="14">OK</text></svg>
</body>
</html>
"""
        self.assertEqual(checker.check_html(html_pct_ok, filename="rm_pct_ok.html"), [])

    def test_r2_bopomofo_extended_template_aria_and_deep_selector(self) -> None:
        # Bopomofo Extended (U+31A0) counts as CJK for section text budget; template aria-label skipped.
        bopomofo_text = "\u31a0" * 221
        html = f"""<!doctype html>
<html><body>
  <template><div aria-label="BANNED_IN_TEMPLATE">BANNED_IN_TEMPLATE</div></template>
  <section id="bopo">
    <p>{bopomofo_text}</p>
    <figure><svg viewBox="0 0 200 100" role="img" aria-label="OK"><text x="10" y="30" font-size="14">OK</text></svg></figure>
  </section>
</body></html>
"""
        cfg = checker.CheckConfig(forbid=("BANNED_IN_TEMPLATE",))
        failures = checker.check_html(html, filename="bopo.html", config=cfg)
        self.assertEqual([f.check for f in failures], ["section-text-budget"])

        # 1100-deep child combinator selector with matching SVG ancestors must not hit RecursionError.
        depth = 1100
        sel = " > ".join(["g"] * depth) + " > text"
        open_gs = "<g>" * depth
        close_gs = "</g>" * depth
        deep_sel_html = f"""<!doctype html>
<html><head><style>{sel} {{ font-size: 12px; }}</style></head>
<body>
  <svg viewBox="0 0 200 100" role="img" aria-label="Deep selector">
    {open_gs}<text x="10" y="30">Small</text>{close_gs}
  </svg>
</body></html>
"""
        deep_failures = checker.check_html(deep_sel_html, filename="deep_sel.html")
        self.assertEqual([f.check for f in deep_failures], ["svg-font-size"])


if __name__ == "__main__":
    unittest.main()
