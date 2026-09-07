"""Frozen entry point for the windowed application.

**Imports the package, not a window.** `epubforge.gui.run` is the one place
that decides which interface starts — the 2026 shell, or the old window under
`EPUBFORGE_LEGACY_UI=1`. This file imported `epubforge.gui.app.run` directly
until 0.4.1, which is how 0.4.0 shipped an installer and a portable build that
opened the old window while every test in the repository exercised the new one:
the frozen build never went through the dispatcher, and PyInstaller — which
follows the imports of *this file* — did not even collect the new package.
"""

import multiprocessing
import sys

from epubforge.gui import run

if __name__ == "__main__":
    # Required before any process spawning in a frozen build, otherwise the
    # child re-runs the whole program instead of the worker.
    multiprocessing.freeze_support()
    sys.exit(run())
