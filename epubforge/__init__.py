"""EPUB F.O.R.G.E. — Factory for Overhauling and Renovating Glitchy EPUBs.

Rebuilds any EPUB into a clean EPUB 3.3 without losing how it looks.
"""

from .model import Book
from .pipeline import Result, Status, rebuild
from .policy import Policy
from .report import Level, Report

__version__ = "0.2.6"

#: Maturity, stated outright because the version number is not a proxy for it.
#: A number climbing towards 1.0 reads as progress towards release whether or
#: not anybody meant it that way; this says what the software actually is.
#: The stages and what it takes to leave each one are in CONTRIBUTING.md.
__stage__ = "alpha"


def version_string() -> str:
    """Version as shown to a human: never the bare number before 1.0."""
    return f"{__version__} ({__stage__})" if __stage__ else __version__


__all__ = [
    "rebuild",
    "Result",
    "Status",
    "Policy",
    "Report",
    "Level",
    "Book",
    "__version__",
    "__stage__",
    "version_string",
]
