"""Draw the states the acceptance list asks for, so they can be looked at.

    QT_QPA_PLATFORM=offscreen python tools/ui_screenshots.py [OUT_DIR]
    QT_SCALE_FACTOR=1.5 python tools/ui_screenshots.py OUT_DIR   # and 2.0

Every picture here is the **real window on the real backends**, reading books
and documents that exist on disk — `tools/ui_fixtures.py` writes them just
before the run. That is not a detail of how the tool is built: the handoff says
in as many words that a `DemoBackend` run is not evidence about the production
adapter, and a screenshot of a demo would be a screenshot of the demo.

So a plan here shows three covers because three EPUBs each carry a different
one; a book with no cover shows a placeholder because that book has no cover;
the results card names two folders because the batch was written beside sources
that live in two; and the converter refuses a scan because that PDF genuinely
has no text layer.

Each state is taken at a wide size and a narrow one, so a layout that clips a
long Polish label shows up here rather than in front of somebody. The scaled
runs are separate processes because Qt reads `QT_SCALE_FACTOR` once, before the
first `QApplication`.

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
from epubforge.gui.shell.backend import EngineBackend  # noqa: E402
from epubforge.gui.shell.models import Stage  # noqa: E402
from epubforge.gui.shell import state  # noqa: E402
from epubforge.gui.shell.pdf_backend import PdfBackend  # noqa: E402
from epubforge.gui.shell.window import MainWindow  # noqa: E402
from tools import ui_fixtures  # noqa: E402

#: Wide and narrow. The narrow one is the smallest window this interface
#: promises to work in, which is the one worth a picture.
WIDE = (1440, 900)
NARROW = (900, 600)

#: Where a Chromium may be sitting when nothing said. The rebuild's look check
#: is a real check with a real browser; without one every book comes out
#: blocked, which makes a truthful picture of a broken environment and a
#: useless picture of the interface.
CHROMES = (
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
)


def find_a_browser() -> str:
    """Point `EPUBFORGE_CHROME` at a browser if the environment has not."""
    if os.environ.get("EPUBFORGE_CHROME"):
        return os.environ["EPUBFORGE_CHROME"]
    for candidate in CHROMES:
        if pathlib.Path(candidate).exists():
            os.environ["EPUBFORGE_CHROME"] = candidate
            return candidate
    return ""


def watch_for_questions(app) -> None:
    """Never wait for an answer nobody is here to give.

    A book with an unresolvable reference makes the window ask, which is
    exactly right and completely fatal to an unattended run: `QDialog.exec`
    starts an event loop of its own and the loop below never gets another
    turn. The fixtures avoid provoking one, but "avoids" is not "cannot", so
    anything modal that does appear is named on the console and dismissed —
    a run that ends with a line saying which question it refused is worth more
    than one that hangs until a timeout kills it.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    def look() -> None:
        modal = app.activeModalWidget()
        if isinstance(modal, QDialog):
            print(f"  UWAGA: pytanie bez odpowiadajacego — {modal.windowTitle()!r}, odrzucone")
            modal.reject()

    timer = QTimer(app)
    timer.timeout.connect(look)
    timer.start(500)


def settle(app, seconds: float = 0.4) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, page, stage: Stage, limit: float = 240.0) -> None:
    """Real work takes real time; a picture taken half way through is a lie."""
    end = time.time() + limit
    while time.time() < end and page.stage is not stage:
        app.processEvents()
        time.sleep(0.01)
    settle(app, 0.3)


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

    browser = find_a_browser()
    print(f"przegladarka do kontroli wygladu: {browser or 'BRAK — ksiazki wyjda zablokowane'}")

    # The books and documents these pictures are of. Written into a directory
    # of this run's own, so a rebuild that publishes beside its sources has
    # somewhere to publish and nothing outside is touched.
    shelf_room = pathlib.Path(tempfile.mkdtemp(prefix="epubforge-polka-"))
    shelf = ui_fixtures.shelf(shelf_room)
    print(f"polka: {shelf_room}")

    # Settings of this run's own: a screenshot tool that reads the real ones
    # opens wherever the last real session left the window.
    room = tempfile.mkdtemp(prefix="epubforge-shots-")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, room)
    # And a history of its own. This one is not a `QSettings` file — it lives
    # in the application data directory — so redirecting the settings above
    # leaves it alone, and a screenshot run was writing its fixtures into the
    # history of whoever ran it. Caught by reading the Start page in a picture
    # and finding the previous run's documents on it.
    state.history_path = lambda: pathlib.Path(room) / "history.json"

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    tokens = tokens_module.DARK
    app.setStyleSheet(tokens_module.stylesheet(tokens))
    watch_for_questions(app)

    window = MainWindow(tokens, backend=EngineBackend("pl"), pdf_backend=PdfBackend("pl"))
    window.show()
    settle(app)

    shoot(window, out, f"01-start{suffix}")

    window.navigate("rebuild")
    window.rebuild.start(shelf["covered"])
    settle(app, 0.05)
    shoot(window, out, f"02-analiza{suffix}", sizes=(WIDE,))

    # Three books, three covers, and they are different because the files are.
    wait_for(app, window.rebuild, Stage.PLAN)
    shoot(window, out, f"03-plan{suffix}")

    window.rebuild._open_drawer()
    settle(app, 0.2)
    shoot(window, out, f"04-szuflada{suffix}")
    window.rebuild.drawer.close_drawer()
    settle(app, 0.1)

    # A book with no cover at all and a title that does not fit: the
    # placeholder and the long name in one picture.
    window.rebuild.start(shelf["plain"])
    wait_for(app, window.rebuild, Stage.PLAN)
    shoot(window, out, f"03b-plan-bez-okladki{suffix}")

    # A trial: it reads and reports and publishes nothing, and has to say so.
    window.rebuild.run(plan_only=True)
    wait_for(app, window.rebuild, Stage.RESULTS)
    shoot(window, out, f"05a-proba-bez-zapisu{suffix}")

    # And the publication, beside its sources — which are on two shelves, so
    # the card has two real folders to name.
    window.rebuild.start(shelf["books"])
    wait_for(app, window.rebuild, Stage.PLAN)
    window.rebuild.run()
    wait_for(app, window.rebuild, Stage.RESULTS)
    shoot(window, out, f"05-wyniki{suffix}")

    # The long batch, where the main action used to sit below four hundred
    # rows. Narrow as well as wide, because that is where it went wrong.
    window.rebuild.start(shelf["crowd"])
    wait_for(app, window.rebuild, Stage.PLAN)
    shoot(window, out, f"05b-dluga-partia{suffix}")

    # The converter, which is a module of its own and gets its own pictures.
    window.navigate("pdf")
    settle(app, 0.2)
    shoot(window, out, f"06-pdf-dokumenty{suffix}")

    window.pdf.start(shelf["documents"])
    wait_for(app, window.pdf, Stage.PLAN)
    shoot(window, out, f"06b-pdf-ustawienia{suffix}")

    # One document converts and one is refused, in the same batch, because a
    # picture of a module that only ever succeeds is a picture of half of it.
    window.pdf.run()
    wait_for(app, window.pdf, Stage.RESULTS)
    shoot(window, out, f"06c-pdf-wyniki{suffix}")

    window.navigate("tools")
    settle(app, 0.2)
    shoot(window, out, f"07-narzedzia{suffix}")

    window.tools.open_tool("diagnostics")
    settle(app, 0.3)
    shoot(window, out, f"08-narzedzie-diagnostyka{suffix}")

    window.navigate("history")
    settle(app, 0.2)
    shoot(window, out, f"09-historia{suffix}")

    window.navigate("settings")
    settle(app, 0.2)
    shoot(window, out, f"10-ustawienia{suffix}")

    for page in (window.rebuild, window.pdf):
        page.runner.stop()
        page.runner.wait_for_idle()
    window.close()
    print(f"gotowe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
