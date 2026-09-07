"""Draw the states the acceptance list asks for, so they can be looked at.

    QT_QPA_PLATFORM=offscreen python tools/ui_screenshots.py [OUT_DIR]
    QT_SCALE_FACTOR=1.5 python tools/ui_screenshots.py OUT_DIR   # and 2.0

Eight states, each at a wide size and a narrow one, taken from the real window
on the demo backend — not mock-ups — so a layout that clips a long Polish label
shows up here rather than in front of somebody. The scaled runs are separate
because Qt reads `QT_SCALE_FACTOR` once, before the first `QApplication`.

`tools/ui_check_layout.py` is the machine's half of the same question: it
measures, this one shows. Both are needed — the checker cannot see that
something is ugly, and a picture cannot prove that nothing overlaps at five
sizes in two languages.
"""

from __future__ import annotations

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
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import Stage  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402

BOOKS = ["Powiesc_przykladowa.epub", "Zbior_opowiadan.epub", "Poradnik_techniczny.epub"]
#: Wide and narrow. The narrow one is the smallest window this interface
#: promises to work in, which is the one worth a picture.
WIDE = (1440, 900)
NARROW = (900, 600)


def settle(app, seconds: float = 0.4) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, window, stage: Stage, limit: float = 15.0) -> None:
    end = time.time() + limit
    while time.time() < end and window.rebuild.stage is not stage:
        app.processEvents()
        time.sleep(0.01)
    settle(app, 0.2)


def shoot(window, out: pathlib.Path, name: str, *, sizes=(WIDE, NARROW)) -> None:
    for size in sizes:
        window.resize(*size)
        QApplication.processEvents()
        settle(QApplication.instance(), 0.25)
        target = out / f"{name}-{size[0]}x{size[1]}.png"
        window.grab().save(str(target))
        print(f"  {target.name}")


def main(argv: "list[str]") -> int:
    out = pathlib.Path(argv[1] if len(argv) > 1 else "runs/zrzuty-ui")
    out.mkdir(parents=True, exist_ok=True)
    scale = os.environ.get("QT_SCALE_FACTOR", "")
    suffix = f"-skala-{scale.replace('.', '_')}" if scale and scale != "1.0" else ""

    # Settings of this run's own: a screenshot tool that reads the real ones
    # opens wherever the last real session left the window.
    room = tempfile.mkdtemp(prefix="epubforge-shots-")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, room)

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    tokens = tokens_module.DARK
    app.setStyleSheet(tokens_module.stylesheet(tokens))

    window = MainWindow(tokens, backend=DemoBackend())
    window.show()
    settle(app)

    shoot(window, out, f"01-start{suffix}")

    window.navigate("rebuild")
    window.rebuild.start(BOOKS)
    settle(app, 0.05)
    shoot(window, out, f"02-analiza{suffix}", sizes=(WIDE,))

    wait_for(app, window, Stage.PLAN)
    shoot(window, out, f"03-plan{suffix}")

    window.rebuild._open_drawer()
    settle(app, 0.2)
    shoot(window, out, f"04-szuflada{suffix}")
    window.rebuild.drawer.close_drawer()
    settle(app, 0.1)

    window.rebuild.run()
    wait_for(app, window, Stage.RESULTS)
    shoot(window, out, f"05-wyniki{suffix}")

    window.navigate("tools")
    settle(app, 0.2)
    shoot(window, out, f"06-narzedzia{suffix}")

    window.tools.open_tool("diagnostics")
    settle(app, 0.3)
    shoot(window, out, f"07-narzedzie-diagnostyka{suffix}")

    window.navigate("history")
    settle(app, 0.2)
    shoot(window, out, f"08-historia{suffix}")

    window.navigate("settings")
    settle(app, 0.2)
    shoot(window, out, f"09-ustawienia{suffix}")

    window.rebuild.runner.stop()
    window.rebuild.runner.wait_for_idle()
    window.close()
    print(f"gotowe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
