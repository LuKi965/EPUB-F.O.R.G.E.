"""Lay the window out at this process's display scale and report what is wrong.

    QT_SCALE_FACTOR=1.5 QT_QPA_PLATFORM=offscreen python tools/ui_check_layout.py

Prints one line of JSON: the layout problems found and whether the window fits
the screen it was given. It is a separate program because Qt reads the scale
factor once, before the first `QApplication` exists — so the only honest way to
test 150 % is to *start* at 150 %.

`tests/test_shell_layout.py` runs this four times, at 1.0, 1.25, 1.5 and 2.0.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.tokens import MIN_WINDOW  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import Stage  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402
from tests.geometry import problems_with  # noqa: E402

#: Big enough to be a normal window, small enough to be a real laptop.
SIZE = (1180, 720)
BOOKS = ["Powiesc_przykladowa.epub", "Zbior_opowiadan.epub"]


def settle(app, seconds: float = 0.3) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, window, stage, limit: float = 15.0) -> None:
    end = time.time() + limit
    while time.time() < end and window.rebuild.stage is not stage:
        app.processEvents()
        time.sleep(0.01)
    settle(app, 0.2)


def main() -> int:
    # Settings of this run's own. Without it the check reads the geometry the
    # last run left behind — which is how it came to report a window larger
    # than the screen and blame the layout for it.
    room = tempfile.mkdtemp(prefix="epubforge-uicheck-")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, room)

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(tokens_module.stylesheet(tokens_module.DARK))

    window = MainWindow(tokens_module.DARK, backend=DemoBackend())
    window.show()
    settle(app)
    screen = window.screen() or app.primaryScreen()
    available = screen.availableGeometry()
    # The question high DPI asks is whether the window this program *opens*
    # fits the screen it opens on: at 200 % a 1440-pixel window is 2880 device
    # pixels, and its right-hand column is off the desktop where nothing can
    # drag it back. Measured before anything resizes it.
    #
    # **Literally, and including the frame** (F07). This used to allow
    # `max(screen, MIN_WINDOW)`, which is to say: a window larger than the
    # desktop passed as long as it was no larger than the size the program
    # wished for. That is not what "fits" means to somebody who cannot reach
    # the right-hand column, and it made the one screen where the answer
    # matters — a small one — the one screen the check could not fail on.
    frame = window.frameGeometry()
    fits = (
        frame.width() <= available.width() + 1
        and frame.height() <= available.height() + 1
    )
    opened = [window.width(), window.height()]
    # A screen too small for the size this interface would like is the one case
    # the handoff allows an emergency scroll bar in: *„Na ekstremalnie małym
    # ekranie dopuszczalny awaryjny scroll, nie niedostępne kontrolki."* So the
    # sideways rule is relaxed exactly there — and every other rule stays,
    # including the one that says the main action must be reachable, because
    # "you can scroll to it" is not the same as "it is not there".
    squeezed = (
        available.width() < MIN_WINDOW[0] or available.height() < MIN_WINDOW[1]
    )
    window.resize(min(SIZE[0], available.width()), min(SIZE[1], available.height()))
    settle(app, 0.2)

    def wrong(page, **kwargs):
        return problems_with(page, allow_sideways=squeezed, **kwargs)

    problems: list[str] = []
    for route in ("home", "tools", "history", "settings"):
        window.navigate(route)
        settle(app, 0.2)
        problems += [f"{route}: {said}" for said in wrong(window.pages[route])]

    window.navigate("rebuild")
    window.rebuild.start(BOOKS)
    wait_for(app, window, Stage.PLAN)
    problems += [
        f"plan: {said}"
        for said in wrong(window.rebuild, main_action=window.rebuild.run_button)
    ]

    window.rebuild.run()
    wait_for(app, window, Stage.RESULTS)
    problems += [f"wyniki: {said}" for said in wrong(window.rebuild)]

    for name in ("library", "diagnostics", "corpus"):
        window.navigate("tools")
        window.tools.open_tool(name)
        settle(app, 0.2)
        page = window.tools.router.currentWidget()
        problems += [f"{name}: {said}" for said in wrong(page)]

    window.rebuild.runner.stop()
    window.rebuild.runner.wait_for_idle()
    window.close()
    print(json.dumps({
        "scale": os.environ.get("QT_SCALE_FACTOR", "1.0"),
        "size": [window.width(), window.height()],
        "screen": [available.width(), available.height()],
        "frame": [frame.width(), frame.height()],
        "minimum": list(MIN_WINDOW),
        # What the window promised on *this* screen, which on a small one is
        # smaller than the wish above.
        "floor": list(window.minimumSize().toTuple()),
        "opened": opened,
        "fits": fits,
        # Whether this screen is too small for the size the interface wishes
        # for, and therefore whether an emergency scroll was allowed above.
        "squeezed": squeezed,
        "problems": problems,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
