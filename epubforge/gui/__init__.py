"""Desktop interface (optional; requires PySide6).

Two windows live here for now. `shell/` is the interface as it is meant to be
— Start, Przebudowa, Narzędzia, Historia, Ustawienia — and `app.py` is the one
it replaces, kept behind `EPUBFORGE_LEGACY_UI=1` until the parity tests have
been read by somebody and the flag can go. Both talk to the same engine; the
old one directly, the new one through `shell.backend`.
"""

from __future__ import annotations

import os

#: The escape hatch, and the only thing that reaches the old window now.
LEGACY_FLAG = "EPUBFORGE_LEGACY_UI"


def legacy_wanted() -> bool:
    return os.environ.get(LEGACY_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def run(argv: "list[str] | None" = None) -> int:
    """Start the interface: the new shell, or the old window on request."""
    if legacy_wanted():
        from .app import run as legacy_run

        return legacy_run(argv)
    from .shell import run as shell_run

    return shell_run(argv)
