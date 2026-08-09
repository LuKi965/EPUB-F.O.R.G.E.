#!/usr/bin/env python3
"""Draw the application icon, at every size Windows and Qt ask for.

Kept as a script rather than as a pair of binaries because an icon that only
exists as a PNG can only ever be edited by whoever still has the source file.
This one is the source file.

The mark has to survive 16×16 in a taskbar, which is the whole design brief.
Everything is drawn at 1024 and downsampled with Lanczos, so the curves stay
smooth; anything with more than three shapes turns to porridge at that size, so
there are three shapes.
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw

#: Kept from the icon this replaces. The application is dark-themed and the
#: installer shows it against both light and dark shells, so the tile is its own
#: background rather than transparent.
NAVY = (35, 45, 69, 255)
PAPER = (240, 242, 247, 255)
PAPER_SHADE = (206, 214, 228, 255)
EMBER = (232, 163, 61, 255)
EMBER_HOT = (245, 208, 130, 255)

SIZE = 1024
#: Windows wants all of these inside one .ico, and picks per context: 16 in the
#: title bar, 32 in the taskbar, 256 on the desktop at large-icon settings.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def tile(draw: ImageDraw.ImageDraw) -> None:
    """The rounded square everything sits on."""
    draw.rounded_rectangle((0, 0, SIZE, SIZE), radius=int(SIZE * 0.22), fill=NAVY)


def anvil(draw: ImageDraw.ImageDraw, *, colour=PAPER, shade=PAPER_SHADE) -> None:
    """A blacksmith's anvil, side on.

    Drawn as a silhouette rather than an outline: at 16 pixels an outline is a
    grey smudge, and a silhouette is still an anvil.

    The proportions are the whole job, and the first attempt got them wrong —
    a short horn on a symmetric waist reads as a pedestal or a table. What makes
    the shape unmistakable is the asymmetry: a **long** horn tapering off one
    end, a squared heel at the other, and a body that sits back towards the
    heel rather than under the middle.
    """
    face_top, face_bottom = 0.34 * SIZE, 0.455 * SIZE
    heel = 0.80 * SIZE
    body_left, body_right = 0.30 * SIZE, heel

    # The face: a slab with a squared heel, sitting proud of the body.
    draw.polygon(
        [(body_left, face_top), (heel, face_top),
         (heel, face_bottom), (body_left, face_bottom)],
        fill=colour,
    )
    # The horn: long, tapering, and slightly nose-down, which is what an anvil
    # looks like and what a table does not.
    draw.polygon(
        [(body_left + 0.005 * SIZE, face_top),
         (body_left + 0.005 * SIZE, face_bottom),
         (0.10 * SIZE, face_bottom - 0.005 * SIZE),
         (0.115 * SIZE, face_top + 0.045 * SIZE)],
        fill=colour,
    )
    # The undercut and waist, set back towards the heel.
    draw.polygon(
        [(0.42 * SIZE, face_bottom), (0.70 * SIZE, face_bottom),
         (0.655 * SIZE, 0.60 * SIZE), (0.465 * SIZE, 0.60 * SIZE)],
        fill=shade,
    )
    # The foot: chunky, and wider than the waist by a clear margin.
    draw.polygon(
        [(0.445 * SIZE, 0.60 * SIZE), (0.675 * SIZE, 0.60 * SIZE),
         (0.745 * SIZE, 0.735 * SIZE), (0.375 * SIZE, 0.735 * SIZE)],
        fill=colour,
    )


def pages(draw: ImageDraw.ImageDraw) -> None:
    """An open book, laid on the anvil's face.

    Two leaves meeting at a spine, in the same paper as the anvil so the two
    read as one object at a distance and as two up close.
    """
    top, bottom = 0.16 * SIZE, 0.345 * SIZE
    spine = 0.52 * SIZE
    draw.polygon(
        [(spine - 0.01 * SIZE, top + 0.02 * SIZE), (0.28 * SIZE, top + 0.06 * SIZE),
         (0.28 * SIZE, bottom), (spine - 0.01 * SIZE, bottom - 0.02 * SIZE)],
        fill=PAPER,
    )
    draw.polygon(
        [(spine + 0.01 * SIZE, top + 0.02 * SIZE), (0.76 * SIZE, top + 0.06 * SIZE),
         (0.76 * SIZE, bottom), (spine + 0.01 * SIZE, bottom - 0.02 * SIZE)],
        fill=PAPER_SHADE,
    )


def spark(draw: ImageDraw.ImageDraw, x: float, y: float, radius: float, colour) -> None:
    """A four-pointed spark. Concave sides, so it reads as a glint and not a plus."""
    points = []
    for index in range(8):
        # Long point, short point, long point … around the circle.
        length = radius if index % 2 == 0 else radius * 0.30
        angle = index * 3.14159265 / 4
        import math

        points.append((x + length * math.sin(angle), y - length * math.cos(angle)))
    draw.polygon(points, fill=colour)


def sparks(draw: ImageDraw.ImageDraw) -> None:
    """Struck metal throws sparks upward and outward, so these do too."""
    spark(draw, 0.815 * SIZE, 0.235 * SIZE, 0.080 * SIZE, EMBER)
    spark(draw, 0.700 * SIZE, 0.150 * SIZE, 0.042 * SIZE, EMBER_HOT)
    spark(draw, 0.885 * SIZE, 0.120 * SIZE, 0.028 * SIZE, EMBER)


def glow(image: Image.Image) -> None:
    """Heat under the anvil: a soft ember wash, no hard edge."""
    from PIL import ImageDraw as _Draw, ImageFilter

    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    _Draw.Draw(layer).ellipse(
        (0.24 * SIZE, 0.68 * SIZE, 0.76 * SIZE, 0.86 * SIZE), fill=(232, 120, 40, 150)
    )
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(SIZE * 0.05)))


def variant_anvil() -> Image.Image:
    """A. The anvil alone. The strongest signal at 16 pixels."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    tile(draw)
    glow(image)
    anvil(ImageDraw.Draw(image))
    sparks(ImageDraw.Draw(image))
    return image


def variant_book_on_anvil() -> Image.Image:
    """B. The book on the anvil. Says both things and costs some clarity."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    tile(draw)
    glow(image)
    draw = ImageDraw.Draw(image)
    anvil(draw)
    pages(draw)
    sparks(draw)
    return image


def variant_hot_book() -> Image.Image:
    """C. The book as it was, with the decorative star traded for real sparks
    and heat from below. The smallest change that stops it being a tidying app."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    tile(draw)
    glow(image)
    draw = ImageDraw.Draw(image)
    top, bottom, spine = 0.30 * SIZE, 0.64 * SIZE, 0.50 * SIZE
    draw.polygon(
        [(spine - 0.015 * SIZE, top + 0.04 * SIZE), (0.20 * SIZE, top),
         (0.20 * SIZE, bottom - 0.04 * SIZE), (spine - 0.015 * SIZE, bottom)],
        fill=PAPER,
    )
    draw.polygon(
        [(spine + 0.015 * SIZE, top + 0.04 * SIZE), (0.80 * SIZE, top),
         (0.80 * SIZE, bottom - 0.04 * SIZE), (spine + 0.015 * SIZE, bottom)],
        fill=PAPER_SHADE,
    )
    sparks(draw)
    return image


VARIANTS = {
    "anvil": variant_anvil,
    "book-on-anvil": variant_book_on_anvil,
    "hot-book": variant_hot_book,
}


def write(image: Image.Image, stem: pathlib.Path) -> None:
    image.resize((256, 256), Image.LANCZOS).save(stem.with_suffix(".png"))
    image.save(stem.with_name(stem.name + "-1024").with_suffix(".png"))
    image.resize((256, 256), Image.LANCZOS).save(
        stem.with_suffix(".ico"), sizes=[(s, s) for s in ICO_SIZES]
    )
    # A contact sheet of the small sizes, because "does it survive 16 pixels" is
    # the only question that matters and it cannot be answered at 256.
    sheet = Image.new("RGBA", (16 + 24 + 32 + 48 + 64 + 60, 72), (128, 128, 128, 255))
    x = 8
    for size in (16, 24, 32, 48, 64):
        sheet.alpha_composite(image.resize((size, size), Image.LANCZOS), (x, 8))
        x += size + 10
    sheet.save(stem.with_name(stem.name + "-male").with_suffix(".png"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="anvil")
    parser.add_argument("--out", default="packaging/epubforge")
    arguments = parser.parse_args()
    write(VARIANTS[arguments.variant](), pathlib.Path(arguments.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
