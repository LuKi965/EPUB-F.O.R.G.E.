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
    # A screen smaller than the smallest window this program has is not
    # something the window can honour — and that is the case here at 200 %,
    # where Qt's offscreen platform reports a 400x400 logical desktop. So the
    # rule is: never larger than the screen, or than the minimum, whichever is
    # the larger of the two.
    fits = (
        window.width() <= max(available.width(), MIN_WINDOW[0]) + 1
        and window.height() <= max(available.height(), MIN_WINDOW[1]) + 1
    )
    opened = [window.width(), window.height()]
    window.resize(min(SIZE[0], available.width()), min(SIZE[1], available.height()))
    settle(app, 0.2)

    problems: list[str] = []
    for route in ("home", "tools", "history", "settings"):
        window.navigate(route)
        settle(app, 0.2)
        problems += [f"{route}: {said}" for said in problems_with(window.pages[route])]

    window.navigate("rebuild")
    window.rebuild.start(BOOKS)
    wait_for(app, window, Stage.PLAN)
    problems += [
        f"plan: {said}"
        for said in problems_with(window.rebuild, main_action=window.rebuild.run_button)
    ]

    window.rebuild.run()
    wait_for(app, window, Stage.RESULTS)
    problems += [f"wyniki: {said}" for said in problems_with(window.rebuild)]

    for name in ("library", "diagnostics", "corpus"):
        window.navigate("tools")
        window.tools.open_tool(name)
        settle(app, 0.2)
        page = window.tools.router.currentWidget()
        problems += [f"{name}: {said}" for said in problems_with(page)]

    window.rebuild.runner.stop()
    window.rebuild.runner.wait_for_idle()
    window.close()
    print(json.dumps({
        "scale": os.environ.get("QT_SCALE_FACTOR", "1.0"),
        "size": [window.width(), window.height()],
        "screen": [available.width(), available.height()],
        "minimum": list(MIN_WINDOW),
        "opened": opened,
        "fits": fits,
        "problems": problems,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
