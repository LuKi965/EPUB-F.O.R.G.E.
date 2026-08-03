"""EPUB-Forge — rebuild any EPUB into a clean EPUB 3.3 without losing its look."""

from .model import Book
from .pipeline import Result, rebuild
from .policy import Policy
from .report import Level, Report

__version__ = "0.2.0"

__all__ = ["rebuild", "Result", "Policy", "Report", "Level", "Book", "__version__"]
