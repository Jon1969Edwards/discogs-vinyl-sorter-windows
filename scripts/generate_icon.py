#!/usr/bin/env python3
"""Generate assets/spindle.ico for Windows packaging."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "spindle.ico"


def main() -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Install Pillow to generate the icon.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (10, 14, 26, 255))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=(108, 99, 255, 255),
        outline=(241, 245, 249, 255),
        width=max(1, size // 32),
    )
    hole = size // 3
    cx = cy = size // 2
    draw.ellipse(
        (cx - hole // 2, cy - hole // 2, cx + hole // 2, cy + hole // 2),
        fill=(10, 14, 26, 255),
    )
    # Pillow downscales the master image into each ICO frame.
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(OUT, format="ICO", sizes=sizes)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
