"""Desktop interface (optional; requires PySide6).

Two windows live here for now. `shell/` is the interface as it is meant to be
— Start, Przebudowa, Narzędzia, Historia, Ustawienia — and `app.py` is the one
it replaces, kept behind `EPUBFORGE_LEGACY_UI=1` until the parity tests have
been read by somebody and the flag can go. Both talk to the same engine; the
old one directly, the new one through `shell.backend`.

**This module is the only door.** The command line, the frozen executable and
the tests all come through `run()`; a caller that imports a window module
directly gets whichever window it named and no dispatch at all. That is not a
hypothetical: 0.4.0 shipped an installer whose entry script imported
`gui.app.run`, so every packaged copy opened the old window while the whole
suite exercised the new one.
"""

from __future__ import annotations

import os

#: The escape hatch, and the only thing that reaches the old window now.
LEGACY_FLAG = "EPUBFORGE_LEGACY_UI"

#: Set to a file path to have `run()` build the window, write which interface
#: it built into that file, and exit without showing anything. It exists for
#: one reason: a windowed executable has no console, so the only way for the
#: build's own smoke test to prove *which* window the frozen program opens is
#: to have the program say so in a file.
SELFTEST_VARIABLE = "EPUBFORGE_UI_SELFTEST"


def legacy_wanted() -> bool:
    return os.environ.get(LEGACY_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def which() -> str:
    """`"legacy"` or `"shell"` — the interface `run()` would start."""
    return "legacy" if legacy_wanted() else "shell"


def _selftest(target: str) -> int:
    """Build the chosen window offscreen, say what it was, and stop.

    Nothing is shown and no event loop runs. What this proves is exactly what
    the packaged build needs proving about it: the interface it would open can
    be imported and constructed *in this build*.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    name = which()
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    tools = 0
    if name == "legacy":
        from . import theme
        from .app import MainWindow

        window = MainWindow(theme.active_palette(app))
    else:
        from .shell import tokens as tokens_module
        from .shell.window import MainWindow, chosen_tokens

        window = MainWindow(chosen_tokens(app) or tokens_module.DARK)
        # And every specialist tool is opened once. They are built on demand,
        # so a tool page missing from a frozen build would fail the first time
        # somebody pressed its tile and nowhere before that — the same shape of
        # defect as EF-094, one floor down.
        for tool in ("library", "diagnostics", "corpus"):
            window.tools.open_tool(tool)
            tools += 1
    from .. import version_string

    with open(target, "w", encoding="utf-8") as handle:
        handle.write(
            f"{name} {type(window).__module__} {version_string()} tools={tools}\n"
        )
    window.close()
    return 0


def run(argv: "list[str] | None" = None) -> int:
    """Start the interface: the new shell, or the old window on request."""
    target = os.environ.get(SELFTEST_VARIABLE, "").strip()
    if target:
        return _selftest(target)
    if legacy_wanted():
        from .app import run as legacy_run

        return legacy_run(argv)
    from .shell import run as shell_run

    return shell_run(argv)
