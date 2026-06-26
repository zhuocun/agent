#!/usr/bin/env python3
"""Rasterize Olune fork badge SVGs to the PNG sizes referenced by manifest/layout/sw."""

from __future__ import annotations

import cairosvg
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"

PLATE_GRADIENT = """
  <defs>
    <linearGradient id="plate" x1="256" y1="0" x2="256" y2="512" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#2079E8"/>
      <stop offset="1" stop-color="#14539C"/>
    </linearGradient>
  </defs>
"""

GLYPH = """
    <path d="M124 104 L256 300 L256 440 M388 104 L256 300" fill="none" stroke="#F9FAFC" stroke-width="88" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="222" y="266" width="68" height="68" rx="8" transform="rotate(45 256 300)" fill="#5BA0F2"/>
"""

ICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
{PLATE_GRADIENT}
  <rect width="512" height="512" rx="114" fill="url(#plate)"/>
  <g transform="translate(256 256) scale(0.70) translate(-256 -272)">
{GLYPH}
  </g>
</svg>"""

MASKABLE_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
{PLATE_GRADIENT}
  <rect width="512" height="512" fill="url(#plate)"/>
  <g transform="translate(256 256) scale(0.58) translate(-256 -272)">
{GLYPH}
  </g>
</svg>"""

APPLE_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
{PLATE_GRADIENT}
  <rect width="512" height="512" fill="url(#plate)"/>
  <g transform="translate(256 256) scale(0.70) translate(-256 -272)">
{GLYPH}
  </g>
</svg>"""

SPLASH = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1170 2532">
  <rect width="1170" height="2532" fill="{bg}"/>
  <g transform="translate(585 1266) scale(1.1)">
    <svg viewBox="0 0 512 512" width="512" height="512">
      <defs>
        <linearGradient id="plate" x1="256" y1="0" x2="256" y2="512" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#2079E8"/>
          <stop offset="1" stop-color="#14539C"/>
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="114" fill="url(#plate)"/>
      <g transform="translate(256 256) scale(0.70) translate(-256 -272)">
        <path d="M124 104 L256 300 L256 440 M388 104 L256 300" fill="none" stroke="#F9FAFC" stroke-width="88" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="222" y="266" width="68" height="68" rx="8" transform="rotate(45 256 300)" fill="#5BA0F2"/>
      </g>
    </svg>
  </g>
</svg>"""


def write_png(svg: str, out: Path, size: int | tuple[int, int]) -> None:
    if isinstance(size, int):
        kw = {"output_width": size, "output_height": size}
    else:
        kw = {"output_width": size[0], "output_height": size[1]}
    out.write_bytes(cairosvg.svg2png(bytestring=svg.encode(), **kw))


def main() -> None:
    write_png(ICON_SVG, PUBLIC / "icon-192.png", 192)
    write_png(ICON_SVG, PUBLIC / "icon-512.png", 512)
    write_png(MASKABLE_SVG, PUBLIC / "icon-maskable-512.png", 512)
    write_png(APPLE_SVG, PUBLIC / "apple-touch-icon.png", 180)
    write_png(SPLASH.format(bg="#F9FAFC"), PUBLIC / "splash-1170x2532-light.png", (1170, 2532))
    write_png(SPLASH.format(bg="#080B11"), PUBLIC / "splash-1170x2532-dark.png", (1170, 2532))
    print("exported PNGs to", PUBLIC)


if __name__ == "__main__":
    main()
