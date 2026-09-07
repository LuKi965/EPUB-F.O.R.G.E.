"""One consistent set of single-stroke glyphs, drawn in whatever colour asks.

The reference prototype used text stand-ins (`⌂`, `◇`, `▦`); the design
package says to replace them with the host project's icon set. The host
project draws its icons as SVG written to a temp file — that is how the old
window's navigation glyphs work, and QSS, `QIcon` and a `<img>` in rich text
can all read the same file, with nothing to bundle into the frozen build.

Status glyphs are here for a reason the accessibility checklist states: a
status may never be carried by colour alone, so every badge in this interface
pairs its colour with one of these shapes and a word.
"""

from __future__ import annotations

import hashlib
import pathlib
import tempfile

#: 16×16 viewBox, `{c}` is the stroke colour.
PATHS = {
    # A house — Start.
    "home": '<path d="M2.6 7.4 L8 3 l5.4 4.4 M4.2 6.6 V13 h7.6 V6.6" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    # A hammer over the anvil block, carried over from the old window so the
    # rebuild keeps the glyph people already associate with it.
    "rebuild": '<path d="M4 12.5 L9 7.5 M7.5 3.5 h5 v3.5 h-5 z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    # A four-square grid — Tools.
    "tools": '<path d="M3 3 h4.5 v4.5 h-4.5 z M8.5 3 h4.5 v4.5 h-4.5 z M3 8.5 h4.5 v4.5 h-4.5 z M8.5 8.5 h4.5 v4.5 h-4.5 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    # A clock — History.
    "history": '<circle cx="8" cy="8" r="5.4" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M8 4.8 V8 l2.4 1.6" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    # A gear, deliberately simple: six teeth read as a gear at 16 px, eight do not.
    "settings": '<circle cx="8" cy="8" r="2.4" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M8 1.8 v1.6 M8 12.6 v1.6 M1.8 8 h1.6 M12.6 8 h1.6 M3.6 3.6 l1.2 1.2 M11.2 11.2 l1.2 1.2 M12.4 3.6 l-1.2 1.2 M4.8 11.2 l-1.2 1.2" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    # An arrow into a tray — the drop zone.
    "drop": '<path d="M8 2.5 v6 M5.5 6 L8 8.8 L10.5 6 M3 10.5 v2 a1 1 0 0 0 1 1 h8 a1 1 0 0 0 1 -1 v-2" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    # Shelf spines — the library tool.
    "library": '<path d="M3.5 3 v10 M7 3 v10 M10 3.6 l3 0.8 -2.6 9.6" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    # A pulse — diagnostics.
    "diagnostics": '<path d="M2.5 8.5 h3 l1.6 -4 2 7 1.6 -3 h2.8" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    # Two pages becoming one — merging damaged copies.
    "merge": '<path d="M3 3 v7 a2 2 0 0 0 2 2 h6 M13 13 V6 a2 2 0 0 0 -2 -2 H5 M8.6 9.6 L11 12 l-2.4 2.4" fill="none" stroke="{c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
    # A folder.
    "folder": '<path d="M2.5 12.5 v-8 a1 1 0 0 1 1 -1 h3 l1.4 1.6 h4.6 a1 1 0 0 1 1 1 v6.4 a1 1 0 0 1 -1 1 h-9 a1 1 0 0 1 -1 -1 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    # A book — one title in a list.
    "book": '<path d="M3.5 3 h6 a2 2 0 0 1 2 2 v8 h-6.5 a1.5 1.5 0 0 1 -1.5 -1.5 z M11.5 5 h1 v8" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    # A magnifier over a page — inspecting one file.
    "inspect": '<path d="M4 2.5 h5 l3 3 v3.4 M4 2.5 v11 h4" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/><circle cx="10.6" cy="10.6" r="2.4" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M12.4 12.4 L14 14" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>',
    # A shield — the safety statement and the validation category.
    "shield": '<path d="M8 2.2 l4.6 1.8 v3.6 c0 3 -2 5 -4.6 6.2 -2.6 -1.2 -4.6 -3.2 -4.6 -6.2 V4 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    # Status: done, attention, refused, running, cancelled.
    "check": '<path d="M3.2 8.4 L6.4 11.6 L12.8 4.8" fill="none" stroke="{c}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
    "warning": '<path d="M8 2.6 L14.2 13.2 H1.8 z M8 6.6 v3.2 M8 11.4 v0.1" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "error": '<circle cx="8" cy="8" r="5.6" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M5.6 5.6 L10.4 10.4 M10.4 5.6 L5.6 10.4" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "running": '<path d="M8 2.6 a5.4 5.4 0 1 1 -5.4 5.4" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "queued": '<circle cx="8" cy="8" r="5.4" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M8 5.2 V8 h2.6" fill="none" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>',
    # A right chevron — "open this".
    "chevron": '<path d="M6 3.5 L10.5 8 L6 12.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "search": '<circle cx="7" cy="7" r="4.2" fill="none" stroke="{c}" stroke-width="1.5"/><path d="M10.2 10.2 L13.5 13.5" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "close": '<path d="M4 4 L12 12 M12 4 L4 12" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "restore": '<path d="M3 8 a5 5 0 1 1 1.6 3.7 M3 12.4 V8.6 h3.8" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "sliders": '<path d="M3 4.5 h10 M3 8 h10 M3 11.5 h10" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/><circle cx="6" cy="4.5" r="1.6" fill="none" stroke="{c}" stroke-width="1.4"/><circle cx="10.5" cy="8" r="1.6" fill="none" stroke="{c}" stroke-width="1.4"/><circle cx="5.2" cy="11.5" r="1.6" fill="none" stroke="{c}" stroke-width="1.4"/>',
    "play": '<path d="M5 3.4 L12.4 8 L5 12.6 z" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "save": '<path d="M3 3.6 h7.4 L13 6.2 v6.2 a1 1 0 0 1 -1 1 H4 a1 1 0 0 1 -1 -1 z M5.4 3.6 v3.2 h4.4 V3.6 M5.4 13.4 V9.6 h5.2 v3.8" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "plus": '<path d="M8 3.4 v9.2 M3.4 8 h9.2" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "trash": '<path d="M3.4 4.6 h9.2 M6.4 4.6 V3.2 h3.2 v1.4 M4.8 4.6 l0.7 8.2 h5 l0.7 -8.2" fill="none" stroke="{c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "text": '<path d="M3 4 h10 M8 4 v9 M5.6 13 h4.8" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "compat": '<path d="M2.6 4 h7 a1 1 0 0 1 1 1 v6 a1 1 0 0 1 -1 1 h-7 a1 1 0 0 1 -1 -1 V5 a1 1 0 0 1 1 -1 z M12 6.4 h1.6 a0.8 0.8 0 0 1 0.8 0.8 v4 a0.8 0.8 0 0 1 -0.8 0.8 H12" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "image": '<path d="M2.6 3.4 h10.8 v9.2 H2.6 z M2.6 10.4 L6 7.4 l2.6 2.2 2-1.8 2.8 2.4" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/><circle cx="6" cy="5.8" r="1" fill="none" stroke="{c}" stroke-width="1.2"/>',
    "tag": '<path d="M7.4 2.6 H13.4 v6 l-6.6 6.6 -6 -6 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/><circle cx="10.6" cy="5.4" r="1.1" fill="none" stroke="{c}" stroke-width="1.3"/>',
    "expert": '<path d="M8 2.4 l1.7 3.6 3.9 0.5 -2.9 2.7 0.8 3.9 L8 11.2 4.5 13.1 5.3 9.2 2.4 6.5 6.3 6 z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
}


def path(name: str, color: str) -> str:
    """A file path for glyph *name*, drawn in *color*, written once and cached."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        + PATHS[name].format(c=color)
        + "</svg>"
    )
    directory = pathlib.Path(tempfile.gettempdir()) / "epubforge-ui"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"shell-{name}-{hashlib.md5(svg.encode()).hexdigest()[:8]}.svg"
    if not target.exists():
        target.write_text(svg, encoding="utf-8")
    return target.as_posix()


def icon(name: str, color: str):
    """The same glyph as a `QIcon`."""
    from PySide6.QtGui import QIcon

    return QIcon(path(name, color))


def rich(name: str, color: str, size: int = 16) -> str:
    """The same glyph as an `<img>` for a rich-text label."""
    return f'<img src="{path(name, color)}" width="{size}" height="{size}"/>'
