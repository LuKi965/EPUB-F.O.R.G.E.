"""The six destinations. Each page renders models and emits intent."""

from __future__ import annotations

from .history import HistoryPage
from .home import HomePage
from .pdf_conversion import PdfConversionPage
from .rebuild import RebuildPage
from .settings import SettingsPage
from .tools import ToolsPage

__all__ = [
    "HistoryPage", "HomePage", "PdfConversionPage", "RebuildPage", "SettingsPage",
    "ToolsPage",
]
