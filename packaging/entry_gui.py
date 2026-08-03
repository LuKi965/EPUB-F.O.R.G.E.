"""Frozen entry point for the windowed application."""

import multiprocessing
import sys

from epubforge.gui.app import run

if __name__ == "__main__":
    # Required before any process spawning in a frozen build, otherwise the
    # child re-runs the whole program instead of the worker.
    multiprocessing.freeze_support()
    sys.exit(run())
