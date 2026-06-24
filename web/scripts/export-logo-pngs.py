#!/usr/bin/env python3
"""Rasterize Olune fork logo SVGs to the PNG sizes referenced by manifest/layout/sw."""

from __future__ import annotations

import cairosvg
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"

FORK_LIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <path d="M124 104 L256 300 L256 440 M388 104 L256 300" fill="none" stroke="{stroke}" stroke-width="88" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="222" y="266" width="68" height="68" rx="8" transform="rotate(45 256 300)" fill="#14539C"/>
</svg>"""

FORK_MASKABLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <g transform="translate(256 256) scale(0.67) translate(-256 -256)">
    <path d="M124 104 L256 300 L256 440 M388 104 L256 300" fill="none" stroke="{stroke}" stroke-width="88" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="222" y="266" width="68" height="68" rx="8" transform="rotate(45 256 300)" fill="#14539C"/>
  </g>
</svg>"""

SPLASH = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1170 2532">
  <rect width="1170" height="2532" fill="{bg}"/>
  <g transform="translate(585 1266) scale(1.35) translate(-256 -272)">
    <path d="M124 104 L256 300 L256 440 M388 104 L256 300" fill="none" stroke="{stroke}" stroke-width="88" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="222" y="266" width="68" height="68" rx="8" transform="rotate(45 256 300)" fill="#14539C"/>
  </g>
</svg>"""


def write_png(svg: str, out: Path, size: int | tuple[int, int]) -> None:
    if isinstance(size, int):
        kw = {"output_width": size, "output_height": size}
    else:
        kw = {"output_width": size[0], "output_height": size[1]}
    out.write_bytes(cairosvg.svg2png(bytestring=svg.encode(), **kw))


def main() -> None:
    write_png(FORK_LIGHT.format(stroke="#2079E8"), PUBLIC / "icon-192.png", 192)
    write_png(FORK_LIGHT.format(stroke="#2079E8"), PUBLIC / "icon-512.png", 512)
    write_png(FORK_MASKABLE.format(stroke="#2079E8"), PUBLIC / "icon-maskable-512.png", 512)
    write_png(FORK_LIGHT.format(stroke="#2079E8"), PUBLIC / "apple-touch-icon.png", 180)
    write_png(SPLASH.format(bg="#F9FAFC", stroke="#2079E8"), PUBLIC / "splash-1170x2532-light.png", (1170, 2532))
    write_png(SPLASH.format(bg="#080B11", stroke="#5BA0F2"), PUBLIC / "splash-1170x2532-dark.png", (1170, 2532))
    print("exported PNGs to", PUBLIC)


if __name__ == "__main__":
    main()
