"""Generates the application icon.

Kept as a script rather than a committed binary blob nobody can diff, though the
resulting .ico is committed too so a build never depends on running this.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
BACKGROUND = (33, 46, 68)
BACKGROUND_EDGE = (22, 31, 47)
PAGE = (247, 249, 252)
PAGE_SHADE = (203, 213, 226)
SPARK = (240, 168, 62)

ICO_SIZES = [(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]


def draw_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=96, fill=BACKGROUND_EDGE)
    draw.rounded_rectangle([6, 6, SIZE - 7, SIZE - 13], radius=92, fill=BACKGROUND)

    # An open book: two page blocks meeting at a central spine.
    top, bottom = 150, 372
    spine, left, right = SIZE // 2, 78, SIZE - 78
    lift = 26

    draw.polygon(
        [(spine, top), (left + 12, top + lift), (left, bottom - lift), (spine, bottom)],
        fill=PAGE,
    )
    draw.polygon(
        [(spine, top), (right - 12, top + lift), (right, bottom - lift), (spine, bottom)],
        fill=PAGE_SHADE,
    )
    draw.line([(spine, top), (spine, bottom)], fill=BACKGROUND, width=10)

    # Text lines, so the mark still reads as a book at small sizes.
    for index in range(4):
        offset = top + 58 + index * 42
        inset = 30 + index * 4
        draw.line([(left + inset + 22, offset), (spine - 30, offset - 8)], fill=PAGE_SHADE, width=9)
        draw.line([(spine + 30, offset - 8), (right - inset - 22, offset)], fill=PAGE, width=9)

    # Forge spark.
    cx, cy, arm = SIZE - 132, SIZE - 132, 54
    draw.polygon(
        [
            (cx, cy - arm), (cx + 14, cy - 14), (cx + arm, cy),
            (cx + 14, cy + 14), (cx, cy + arm), (cx - 14, cy + 14),
            (cx - arm, cy), (cx - 14, cy - 14),
        ],
        fill=SPARK,
    )
    return image


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "epubforge.ico"
    icon = draw_icon()
    target.parent.mkdir(parents=True, exist_ok=True)
    icon.save(target, format="ICO", sizes=ICO_SIZES)
    icon.resize((256, 256), Image.LANCZOS).save(target.with_suffix(".png"), format="PNG")
    print(f"wrote {target} and {target.with_suffix('.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
