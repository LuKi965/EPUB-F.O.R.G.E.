"""EPUB F.O.R.G.E. — Factory for Overhauling and Renovating Glitchy EPUBs.

Rebuilds any EPUB into a clean EPUB 3.3 without losing how it looks.
"""

from .model import Book
from .pipeline import Result, rebuild
from .policy import Policy
from .report import Level, Report

__version__ = "0.8.1"

__all__ = ["rebuild", "Result", "Policy", "Report", "Level", "Book", "__version__"]
