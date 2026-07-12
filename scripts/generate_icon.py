#!/usr/bin/env python3
"""Generate assets/vinyl_shelf_sorter.ico for Windows packaging."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "vinyl_shelf_sorter.ico"


def main() -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Install Pillow to generate the icon.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (10, 14, 26, 255))
        draw = ImageDraw.Draw(img)
        margin = max(2, size // 8)
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
        images.append(img)
    images[0].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
