"""The 2026 interface: task first, mechanism second.

The old window put the machine on the screen — four tabs named after
subsystems and a column of forty switches, all of it visible before anybody
had said what they wanted to do. This package is the information architecture
the owner approved instead: **Start · Przebudowa · Narzędzia · Historia ·
Ustawienia**, with the rebuild itself a four-step flow (files, analysis, plan,
results) and the whole policy behind one searchable drawer.

The engine does not move. Everything here talks to `backend.ForgeUiBackend`,
which hands out plain dataclasses; no widget in this package imports `Policy`,
`Report` or the pipeline, and nothing here decides what a rebuild does.
"""

from __future__ import annotations

__all__ = ["run"]


def run(argv: "list[str] | None" = None) -> int:
    """Start the new window. Imported lazily so `epubforge.gui` costs nothing."""
    from .window import run as _run

    return _run(argv)
