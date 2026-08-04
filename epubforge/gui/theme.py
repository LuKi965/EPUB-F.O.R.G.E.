"""Fluent-flavoured styling for the Qt interface.

This is not WinUI — it is Qt Widgets dressed to sit comfortably on Windows 11:
layered surfaces, 6–8 px radii, Segoe UI Variable, the system accent blue and
restrained borders. Light and dark are both defined; the active one follows the
system palette.
"""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    window: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    fix: str
    preserved: str
    warn: str
    error: str
    info: str


LIGHT = Palette(
    window="#F3F3F3",
    surface="#FFFFFF",
    surface_alt="#FAFAFA",
    border="#E5E5E5",
    border_strong="#D0D0D0",
    text="#1A1A1A",
    text_muted="#5D5D5D",
    accent="#0067C0",
    accent_hover="#005BA1",
    accent_text="#FFFFFF",
    fix="#0F7B36",
    preserved="#0B6A8F",
    warn="#9A6300",
    error="#C42B1C",
    info="#6B6B6B",
)

DARK = Palette(
    window="#202020",
    surface="#2B2B2B",
    surface_alt="#323232",
    border="#3D3D3D",
    border_strong="#4A4A4A",
    text="#F2F2F2",
    text_muted="#A8A8A8",
    accent="#4CC2FF",
    accent_hover="#67CDFF",
    accent_text="#00243D",
    fix="#5FD98A",
    preserved="#6FC9E8",
    warn="#F0C36A",
    error="#FF8A80",
    info="#9A9A9A",
)

FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif'


def _checkmark(color: str) -> str:
    """Write a tick glyph to a temp file and return a QSS-usable URL.

    Qt stylesheets cannot take a data: URI for `image:`, and shipping an asset
    file would need extra handling in the frozen build. Generating it at
    runtime keeps the styling self-contained either way.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    directory = pathlib.Path(tempfile.gettempdir()) / "epubforge-ui"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"check-{hashlib.md5(svg.encode()).hexdigest()[:8]}.svg"
    if not target.exists():
        target.write_text(svg, encoding="utf-8")
    return target.as_posix()


def stylesheet(palette: Palette) -> str:
    p = palette
    tick = _checkmark(p.accent_text)
    return f"""
    QWidget {{
        background-color: {p.window};
        color: {p.text};
        font-family: {FONT_STACK};
        font-size: 10pt;
    }}

    QMainWindow::separator {{ width: 0px; height: 0px; }}

    /* Transparent so text sits on whatever surface contains it, not on a
       window-coloured band across the card. */
    QLabel, QCheckBox, QGroupBox > QWidget, QSplitter {{ background: transparent; }}

    QMenuBar {{ background: transparent; padding: 2px 4px; }}
    QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {p.surface_alt}; }}
    QMenu {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {p.surface_alt}; }}

    /* Cards ------------------------------------------------------------ */
    QGroupBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        margin-top: 14px;
        padding: 14px 12px 12px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 4px;
        color: {p.text_muted};
        font-size: 9pt;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* Buttons ---------------------------------------------------------- */
    QPushButton {{
        background-color: {p.surface};
        border: 1px solid {p.border_strong};
        border-radius: 6px;
        padding: 7px 16px;
        min-height: 18px;
    }}
    QPushButton:hover {{ background-color: {p.surface_alt}; }}
    QPushButton:pressed {{ background-color: {p.border}; }}
    QPushButton:disabled {{ color: {p.text_muted}; border-color: {p.border}; }}

    QPushButton#primary {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: 1px solid {p.accent};
        font-weight: 600;
        font-size: 10.5pt;
        border-radius: 7px;
    }}
    QPushButton#primary:hover {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}
    QPushButton#primary:disabled {{
        background-color: {p.border};
        border-color: {p.border};
        color: {p.text_muted};
    }}

    /* Inputs ----------------------------------------------------------- */
    QLineEdit, QComboBox {{
        background-color: {p.surface};
        border: 1px solid {p.border_strong};
        border-radius: 6px;
        padding: 6px 10px;
        /* Without a floor the box shrinks to the font's ascent and clips the
           descenders — which in Polish means every ą, ę and g in the label. */
        min-height: 20px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 2px solid {p.accent}; padding: 5px 9px; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {p.surface_alt};
        selection-color: {p.text};
        outline: none;
    }}

    QCheckBox {{ spacing: 8px; padding: 3px 0; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border: 1px solid {p.border_strong};
        border-radius: 4px;
        background: {p.surface};
    }}
    QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
    QCheckBox::indicator:checked {{
        background: {p.accent};
        border-color: {p.accent};
        image: url("{tick}");
    }}
    QCheckBox::indicator:disabled {{ background: {p.border}; border-color: {p.border}; }}

    /* Table ------------------------------------------------------------ */
    QTableWidget {{
        background-color: {p.surface};
        alternate-background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
        gridline-color: transparent;
        outline: none;
    }}
    QTableWidget::item {{ padding: 7px 8px; border: none; }}
    QTableWidget::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
    QHeaderView::section {{
        background-color: transparent;
        color: {p.text_muted};
        border: none;
        border-bottom: 1px solid {p.border};
        padding: 8px;
        font-weight: 600;
    }}
    QTableCornerButton::section {{ background: transparent; border: none; }}

    /* Report pane ------------------------------------------------------ */
    QTextEdit {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 8px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_text};
    }}

    QProgressBar {{
        background-color: {p.surface_alt};
        border: none;
        border-radius: 4px;
        height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 4px; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {p.border_strong};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {p.border_strong};
        border-radius: 4px;
        min-width: 28px;
    }}

    QSplitter::handle {{ background: transparent; width: 10px; height: 10px; }}

    QToolTip {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border_strong};
        border-radius: 6px;
        padding: 7px 9px;
    }}

    QStatusBar {{ color: {p.text_muted}; }}
    QStatusBar::item {{ border: none; }}

    QLabel#sectionLabel {{ color: {p.text_muted}; font-size: 9pt; }}
    QLabel#fieldLabel {{ color: {p.text}; font-weight: 600; padding-top: 4px; }}
    """


def is_dark(app) -> bool:
    """True when the system is running a dark colour scheme."""
    window = app.palette().window().color()
    # Perceived luminance; anything below the midpoint reads as a dark surface.
    luminance = (0.299 * window.red() + 0.587 * window.green() + 0.114 * window.blue()) / 255
    return luminance < 0.5


def active_palette(app) -> Palette:
    return DARK if is_dark(app) else LIGHT
