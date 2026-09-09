"""The book's own cover, small enough to put in a list.

Deliberately without Qt. Decoding somebody's JPEG and scaling it down is the
expensive half and it happens on the worker thread, where the analysis already
is; the cheap half — turning bytes into a `QPixmap` — is the only part that
needs the GUI thread, and it is in `widgets.py` where it belongs
(02-UI-DESIGN, „Kontrakt miniatur": *dekoduj i zmniejszaj poza GUI*).

What this refuses to do is as much of the contract as what it does. It reads
**bytes the reader already has in hand** — never a path, never an archive
member it goes looking for, never a URL — so there is nothing here that can be
pointed at a file outside the book. A cover it cannot decode, or one so large
that decoding it would cost more than the whole rebuild, produces `None`: the
row then draws its placeholder, and the *book* is not marked failed over a
picture (C03).
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass

#: The largest picture worth decoding. A cover is a cover; ten megabytes of
#: one is a scan somebody dropped in by mistake, and PIL would happily spend a
#: second and a few hundred megabytes on it. Refused, with a placeholder.
MOST_BYTES = 12 * 1024 * 1024

#: And the largest in pixels, which is the number that actually costs memory:
#: a decompressed 8000×8000 image is 256 MB whatever the file weighs. PIL's own
#: decompression-bomb guard sits above this; this is the program's own limit.
MOST_PIXELS = 40_000_000

#: How big a thumbnail is allowed to come out. The list draws 48×72 logical
#: pixels and up to 56×84 in a large view, so 112×168 covers a 2× screen
#: exactly and nothing more is worth carrying between threads.
BIGGEST = (112, 168)

#: How much of these to keep. Sixty covers at ~20 kB is about a megabyte, which
#: is a batch of sixty books on screen; beyond that the oldest goes.
KEEP = 60


@dataclass(frozen=True)
class Thumbnail:
    """A decoded, shrunk cover as bytes a GUI can turn into a pixmap.

    PNG rather than the source's own format: one format to draw means the GUI
    side has no decisions to make, and a thumbnail is small enough that the
    encoding cost does not matter.
    """

    data: bytes
    width: int
    height: int
    #: Where it came from, for the cache and for a test that wants to know.
    key: str = ""

    @property
    def mime(self) -> str:
        return "image/png"


def fingerprint(source, size: int = 0, mtime_ns: int = 0) -> str:
    """What identifies a book's file *as it is now*.

    The path alone is not enough: C04 is a person replacing a book with a new
    edition under the same name, and a cache keyed on the path would go on
    showing the old cover for as long as the window stayed open. Path plus
    length plus modification time changes when the file does.
    """
    path = os.path.abspath(str(source))
    if not size and not mtime_ns:
        try:
            stat = os.stat(path)
            size, mtime_ns = stat.st_size, stat.st_mtime_ns
        except OSError:
            size, mtime_ns = 0, 0
    return hashlib.sha256(
        f"{path}\0{size}\0{mtime_ns}".encode("utf-8", "replace")
    ).hexdigest()[:32]


def shrink(data: bytes, *, key: str = "", biggest: "tuple[int, int]" = BIGGEST
           ) -> "Thumbnail | None":
    """Decode *data* and scale it to fit *biggest*, or say it cannot.

    `None` for every kind of "not a picture this program can draw": an
    encoding PIL does not have, bytes that are not an image at all, a file
    large enough to be a mistake, a decompression bomb. All of them are the
    same thing to the person — a book with no cover to show — and none of them
    is a reason to call the book broken.
    """
    if not data or len(data) > MOST_BYTES:
        return None
    try:
        from PIL import Image
    except ImportError:
        # A window whose Python has no Pillow draws placeholders and says
        # nothing about it: a missing picture library is not a broken book.
        return None
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MOST_PIXELS:
                return None
            picture = opened.convert("RGBA")
            # `contain`, which is the word the design uses: the whole cover
            # inside the box, its own proportions kept, nothing cropped.
            picture.thumbnail(biggest, Image.LANCZOS)
            out = io.BytesIO()
            picture.save(out, format="PNG", optimize=False)
            return Thumbnail(out.getvalue(), picture.width, picture.height, key)
    except Exception:  # noqa: BLE001 — somebody else's picture, in somebody's book
        # PIL raises a dozen different things on a damaged file, and every one
        # of them means the same to this program. The book still rebuilds.
        return None


class Covers:
    """A small, bounded store of thumbnails, keyed on what the file is now.

    Bounded because a shelf of five hundred books would otherwise hold five
    hundred decoded covers for as long as the window is open. Least recently
    asked for goes first, which is the order a person scrolls in.
    """

    def __init__(self, keep: int = KEEP) -> None:
        self.keep = keep
        self._held: "dict[str, Thumbnail | None]" = {}

    def __len__(self) -> int:
        return len(self._held)

    def get(self, key: str) -> "Thumbnail | None":
        found = self._held.get(key, _MISSING)
        if found is _MISSING:
            return None
        # Asked for is used: move it to the end so the oldest is the one that
        # nobody has looked at for longest.
        self._held[key] = self._held.pop(key)
        return found

    def knows(self, key: str) -> bool:
        """Whether this key has an answer — including the answer "no cover".

        Kept apart from `get` on purpose: a book whose cover could not be read
        must not be decoded again on every repaint, and `None` is a real answer
        rather than a cache miss.
        """
        return key in self._held

    def put(self, key: str, thumbnail: "Thumbnail | None") -> "Thumbnail | None":
        self._held.pop(key, None)
        self._held[key] = thumbnail
        while len(self._held) > self.keep:
            self._held.pop(next(iter(self._held)))
        return thumbnail

    def forget(self, key: str) -> None:
        self._held.pop(key, None)

    def clear(self) -> None:
        self._held.clear()


_MISSING = object()
