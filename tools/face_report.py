"""Say what face the window draws in, on this machine, in numbers.

The Windows runner measured the interface about 1.9 times wider than this
was written on (Tests (Windows) #73: a radio button reaching 749 px for a
sentence 358 px wide here, both at 16 pt), and nothing in a failing test
said which face it was drawing or how it had scaled it. `QFontInfo` on
Windows answers -1 for the pixel size of a point-sized font, so a failure
message alone cannot carry the number.

Run under the shell's own stylesheet, this prints what the tests cannot:
the family the stylesheet asks for and the one Qt resolves it to, the
families the machine has that could stand in, the DPI, and the advance of
one Polish sentence at the two sizes the layout tests use. Read the output
beside the same run on another machine; the ratio between them is the
number every layout failure on the runner has been missing.

Never fails: it is a report, not a test.
"""

from __future__ import annotations

import os
import sys

SENTENCE = "Tekst dopasowujący się do ekranu"


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics
    from PySide6.QtWidgets import QApplication, QLabel

    from epubforge.gui.shell import tokens

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(tokens.stylesheet(tokens.DARK))
    screen = app.primaryScreen()
    print(f"platform: {sys.platform}; Qt platform: {app.platformName()}")
    if screen is not None:
        print(
            f"screen: logical dpi {screen.logicalDotsPerInch():.1f}, physical dpi "
            f"{screen.physicalDotsPerInch():.1f}, device pixel ratio {screen.devicePixelRatio()}"
        )
    print(f"application font: {app.font().family()!r} {app.font().pointSizeF()} pt")
    families = QFontDatabase.families()
    of_interest = [
        family for family in families
        if any(word in family.lower() for word in ("segoe", "inter", "noto sans", "dejavu", "arial", "liberation"))
    ]
    print(f"families on this machine: {len(families)}; of interest: {of_interest[:20]}")
    for points in (10, 16):
        label = QLabel(SENTENCE)
        label.setObjectName("muted")
        label.setStyleSheet(f"font-size: {points}pt")
        label.ensurePolished()
        font = label.font()
        info = QFontInfo(font)
        metrics = QFontMetrics(font)
        print(
            f"{points} pt: asked {font.family()!r} -> resolved {info.family()!r}, "
            f"{info.pointSizeF()} pt / {info.pixelSize()} px (QFontInfo), "
            f"height {metrics.height()} px, sentence {metrics.horizontalAdvance(SENTENCE)} px, "
            f"'M' {metrics.horizontalAdvance('M')} px"
        )
        # The same sentence in the plain default font, so a stylesheet that
        # resolves to something odd can be told apart from a machine that
        # draws everything wide.
        plain = QFont()
        plain.setPointSize(points)
        print(
            f"{points} pt, default font {QFontInfo(plain).family()!r}: "
            f"sentence {QFontMetrics(plain).horizontalAdvance(SENTENCE)} px"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
