#!/usr/bin/env python3
"""Generates the application icon.

Kept as a script rather than a committed binary blob nobody can diff, though the
resulting .ico is committed too so a build never depends on running this.

The mark is an open book with a hammer beside it. It was an open book with a
four-pointed spark, which was a perfectly good mark for a tidying utility and
said nothing about a forge; the owner's note was that the star did not fit, and
that a hammer in the star's own colour would. Nothing else about the icon
changed — same tile, same book, same ember, same corner.
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
#: The spark's colour, kept for the hammer that replaced it.
SPARK = (240, 168, 62)

ICO_SIZES = [(n, n) for n in (16, 24, 32, 48, 64, 128, 256)]

#: The hammer is drawn upright on its own layer and rotated into place, and it
#: is drawn this many times oversize first so the rotation has something to
#: resample. A diagonal edge rendered at final size and then turned is a
#: staircase; rendered at 6× and reduced, it is a line.
SUPERSAMPLE = 6

#: Degrees anticlockwise, so a negative number swings the head up and to the
#: right — into the corner the spark used to occupy, with the handle crossing
#: back under the book. Enough tilt to read as a tool mid-swing rather than as a
#: T lying on its side, not so much that the head leaves the tile.
HAMMER_TILT = -38


def hammer(image: Image.Image, centre: tuple[int, int], span: int) -> None:
    """A club hammer, head up and to the right, handle down and to the left.

    Two rectangles and nothing else. Everything with more shape than that — a
    cross peen, a wedged eye, a wrapped grip — is legible at 256 pixels and mud
    at 16, and 16 is where a taskbar icon actually lives.
    """
    scale = SUPERSAMPLE
    # Local, upright coordinates: a box tall enough for head and handle both.
    width, height = 130 * scale, 168 * scale
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    head_width, head_height = 122 * scale, 52 * scale
    left = (width - head_width) // 2
    draw.rounded_rectangle(
        (left, 4 * scale, left + head_width, 4 * scale + head_height),
        radius=7 * scale,
        fill=SPARK,
    )
    # The handle starts inside the head rather than under it, so the two read as
    # one object when the antialiasing at 16 pixels blurs the joint.
    handle_width = 26 * scale
    handle_left = (width - handle_width) // 2
    draw.rounded_rectangle(
        (handle_left, 4 * scale + head_height - 6 * scale,
         handle_left + handle_width, height - 4 * scale),
        radius=6 * scale,
        fill=SPARK,
    )

    turned = layer.rotate(HAMMER_TILT, resample=Image.BICUBIC, expand=True)
    turned = turned.resize(
        (round(span * turned.width / width), round(span * turned.height / width)),
        Image.LANCZOS,
    )
    image.alpha_composite(
        turned, (centre[0] - turned.width // 2, centre[1] - turned.height // 2)
    )


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

    # Where the spark was, at the size the spark was.
    hammer(image, centre=(SIZE - 128, SIZE - 126), span=132)
    return image


def contact_sheet(icon: Image.Image, target: Path) -> Path:
    """The small sizes side by side, because "does it survive 16 pixels" is the
    only question that matters and it cannot be answered at 256."""
    sizes = (16, 24, 32, 48, 64)
    sheet = Image.new("RGBA", (sum(sizes) + 10 * len(sizes) + 6, 80), (128, 128, 128, 255))
    x = 8
    for size in sizes:
        sheet.alpha_composite(icon.resize((size, size), Image.LANCZOS), (x, 8))
        x += size + 10
    sheet.save(target)
    return target


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
