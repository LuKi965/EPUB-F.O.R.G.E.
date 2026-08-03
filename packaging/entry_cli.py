"""Frozen entry point for the console application."""

import multiprocessing
import sys

from epubforge.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
