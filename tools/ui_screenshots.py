"""Draw the states the acceptance list asks for, so they can be looked at.

    QT_QPA_PLATFORM=offscreen python tools/ui_screenshots.py [OUT_DIR]

Seven pictures, each named after the state it shows. They are taken from the
real window on the demo backend — not mock-ups — so a layout that clips a long
Polish label shows up here rather than in front of somebody.

The 150 % picture is taken by asking Qt for that scale factor, which is what a
Windows display at 150 % does to the same window.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.gui.shell import tokens as tokens_module  # noqa: E402
from epubforge.gui.shell.backend import DemoBackend  # noqa: E402
from epubforge.gui.shell.models import Stage  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402

BOOKS = ["Powiesc_przykladowa.epub", "Zbior_opowiadan.epub", "Poradnik_techniczny.epub"]


def settle(app, seconds: float = 0.4) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, window, stage: Stage, limit: float = 8.0) -> None:
    end = time.time() + limit
    while time.time() < end and window.rebuild.stage is not stage:
        app.processEvents()
        time.sleep(0.01)
    settle(app, 0.2)


def shoot(window, out: pathlib.Path, name: str, size) -> None:
    window.resize(*size)
    QApplication.processEvents()
    settle(QApplication.instance(), 0.25)
    target = out / f"{name}.png"
    window.grab().save(str(target))
    print(f"  {target}  ({size[0]}×{size[1]})")


def main(argv: "list[str]") -> int:
    out = pathlib.Path(argv[1] if len(argv) > 1 else "runs/zrzuty-ui")
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    tokens = tokens_module.DARK
    app.setStyleSheet(tokens_module.stylesheet(tokens))

    window = MainWindow(tokens, backend=DemoBackend())
    window.show()
    settle(app)

    shoot(window, out, "01-start-1536x960", (1536, 960))

    window.navigate("rebuild")
    window.rebuild.start(BOOKS)
    settle(app, 0.05)
    shoot(window, out, "02-analiza-1280x800", (1280, 800))

    wait_for(app, window, Stage.PLAN)
    shoot(window, out, "03-plan-1536x960", (1536, 960))

    window.rebuild._open_drawer()
    settle(app, 0.2)
    shoot(window, out, "04-szuflada-1536x960", (1536, 960))
    window.rebuild.drawer.close_drawer()
    settle(app, 0.1)

    window.rebuild.run()
    wait_for(app, window, Stage.RESULTS)
    shoot(window, out, "05-wyniki-1536x960", (1536, 960))

    shoot(window, out, "06-waskie-1100x700", (1100, 700))

    window.navigate("tools")
    settle(app, 0.2)
    shoot(window, out, "07-narzedzia-1536x960", (1536, 960))

    window.navigate("history")
    settle(app, 0.2)
    shoot(window, out, "08-historia-1536x960", (1536, 960))

    window.navigate("settings")
    settle(app, 0.2)
    shoot(window, out, "09-ustawienia-1536x960", (1536, 960))

    if os.environ.get("QT_SCALE_FACTOR"):
        # Run the tool a second time with QT_SCALE_FACTOR=1.5 for the picture
        # the acceptance list asks for; Qt reads it once, at startup.
        window.navigate("home")
        settle(app, 0.2)
        shoot(window, out, "10-skala-150", (1536, 960))

    window.close()
    print(f"gotowe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
