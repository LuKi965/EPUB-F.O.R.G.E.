"""Visual tokens and the one stylesheet built from them.

The palette is the approved one from the design package: a deep blue-grey
canvas, one accent, and three status colours. It is defined twice — dark as
specified, light with the same *roles* — because the old window followed the
system theme and taking that away would be a regression dressed as a redesign.

Nothing here knows about widgets. `stylesheet(tokens)` is a pure function of
the palette, which is what lets a test read a colour rather than a screenshot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tokens:
    """One palette. Field names are roles, never colours."""

    canvas: str
    sidebar: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    #: Backgrounds for the three status tints, at rest on `surface`.
    success_wash: str
    warning_wash: str
    danger_wash: str
    accent_wash: str
    #: The focus ring. Its own token because it must stay legible on every
    #: surface above — a focus state nobody can see is the accessibility
    #: failure this program is least likely to notice on its own.
    focus: str
    dark: bool = True


#: `DESIGN_SPEC.md` values, unchanged. The washes and the focus ring are the
#: only additions: the specification names the ten colours and leaves how a
#: tinted card or a focus ring is drawn to the implementation.
DARK = Tokens(
    canvas="#0D1420",
    sidebar="#101A29",
    surface="#131F30",
    surface_2="#18263A",
    surface_3="#1D2D44",
    border="#2A3B52",
    border_strong="#3B5270",
    text="#F3F6FC",
    muted="#9FB0CA",
    accent="#4F84FF",
    accent_hover="#6594FF",
    accent_text="#08101D",
    success="#29C99A",
    warning="#F0B94F",
    danger="#FF7785",
    success_wash="#0F352F",
    warning_wash="#332B18",
    danger_wash="#361D24",
    accent_wash="#162747",
    focus="#8FB4FF",
)

#: The same roles on a light ground. Contrast checked against the text colour
#: it carries rather than transposed from the dark set: `#4F84FF` on white is
#: 3.1:1, which fails for text, so the light accent is darker and the accent
#: text is white.
LIGHT = Tokens(
    canvas="#F4F6FA",
    sidebar="#EAEEF6",
    surface="#FFFFFF",
    surface_2="#F4F6FA",
    surface_3="#E8EDF6",
    border="#D6DEEB",
    border_strong="#B4C1D6",
    text="#111A28",
    muted="#4E5D74",
    accent="#1F5FE0",
    accent_hover="#1B52C4",
    accent_text="#FFFFFF",
    success="#0E7C5A",
    warning="#8A5A00",
    danger="#B4232F",
    success_wash="#E7F6F0",
    warning_wash="#FDF3DF",
    danger_wash="#FCEAEC",
    accent_wash="#E7EEFD",
    focus="#1F5FE0",
    dark=False,
)


#: Sizes the design specification states outright, kept as names so a widget
#: never spells a number the specification owns.
SIDEBAR_WIDTH = 244
SIDEBAR_COMPACT_WIDTH = 64
#: Below this *window* width the sidebar collapses to icons. It is the one
#: measurement still taken from the window rather than from a page's viewport,
#: and deliberately: the sidebar is what makes the viewport narrow, so deciding
#: it from the viewport would be a loop. Everything else asks `responsive`.
COMPACT_BELOW = 1024
#: How much slack before the sidebar changes its mind. Same reason as
#: `responsive.HYSTERESIS`: an edge dragged to exactly the threshold.
COMPACT_SLACK = 16
#: The drawer's widest. It is a maximum now, not a width: on a narrow page it
#: takes the whole viewport instead of hanging off the side of it.
DRAWER_WIDTH = 650
#: The smallest window this interface promises to be usable in. It was
#: 1100x700 — which is to say the window refused to be the size of a netbook,
#: an old laptop, or half of a 1920 screen. Everything reflows now, so the
#: floor is what Qt needs for a window with a sidebar and one card in it.
MIN_WINDOW = (800, 520)
REFERENCE_WINDOW = (1536, 960)
CONTENT_MARGIN = 28
CARD_GAP = 14
#: How thick the stylesheet makes a scroll bar — the width of a vertical one,
#: the height of a horizontal one. Named because two things need it and one of
#: them is not styling: a page that scrolls hands this much of its width to the
#: bar, and `responsive` decides a composition from what is left (F08).
SCROLL_BAR_WIDTH = 10


def _tick(colour: str) -> str:
    """A checkmark for the checkbox indicator, drawn in *colour*.

    Qt draws a ticked `QCheckBox` under a stylesheet as a plain filled square:
    "on" and "off" then differ only by colour, which is the one thing a status
    may never rest on. The old window solved this with an image and so does
    this one.
    """
    from . import icons

    return icons.path("check", colour)


def stylesheet(tokens: Tokens) -> str:
    """The whole application stylesheet for one palette.

    Two rules run through all of it. Interactive controls are at least 40 px
    of effective height, because the specification says so and because a
    person on a 150 % display is not a person with a smaller finger. And every
    focusable control draws a ring in `focus` — `:focus` alone, not
    `:focus:hover`, so keyboard traversal is visible without a mouse anywhere
    near it.
    """
    t = tokens
    tick = _tick(t.accent_text)
    return f"""
    * {{
        font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", sans-serif;
        font-size: 10pt;
        color: {t.text};
    }}
    QMainWindow, QWidget#root, QStackedWidget#router {{ background: {t.canvas}; }}
    QWidget {{ background: transparent; }}
    QWidget#sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
    QStatusBar {{ background: {t.sidebar}; color: {t.muted}; border-top: 1px solid {t.border}; }}
    QMenuBar {{ background: {t.sidebar}; color: {t.text}; }}
    QMenuBar::item:selected {{ background: {t.surface_3}; }}
    QMenu {{ background: {t.surface_2}; border: 1px solid {t.border}; }}
    QMenu::item:selected {{ background: {t.accent_wash}; }}

    QLabel#brand {{ font-size: 13pt; font-weight: 750; }}
    QLabel#version, QLabel#muted, QLabel#pageSubtitle, QLabel#cardSubtitle,
    QLabel#eyebrow, QLabel#tagline {{ color: {t.muted}; }}
    QLabel#pageTitle {{ font-size: 24pt; font-weight: 750; }}
    QLabel#eyebrow {{ font-size: 11pt; }}
    QLabel#cardTitle {{ font-size: 12pt; font-weight: 700; }}
    QLabel#metric {{ font-size: 19pt; font-weight: 750; }}
    QLabel#sectionTitle {{ font-size: 14pt; font-weight: 700; }}

    QPushButton {{
        min-height: 26px;
        padding: 8px 15px;
        border: 1px solid {t.border_strong};
        border-radius: 9px;
        background: {t.surface_2};
    }}
    QPushButton:hover {{ background: {t.surface_3}; border-color: {t.accent}; }}
    QPushButton:pressed {{ background: {t.surface}; }}
    QPushButton:disabled {{ color: {t.muted}; border-color: {t.border}; background: {t.surface}; }}
    QPushButton:focus {{ border: 2px solid {t.focus}; padding: 7px 14px; }}
    QPushButton#primary {{
        background: {t.accent}; color: {t.accent_text}; font-weight: 700; border-color: {t.accent};
    }}
    QPushButton#primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#primary:disabled {{ background: {t.surface_2}; color: {t.muted}; border-color: {t.border}; }}
    QPushButton#danger {{ border-color: {t.danger}; color: {t.danger}; }}
    QPushButton#ghost {{
        background: transparent; border-color: transparent; color: {t.muted}; text-align: left;
    }}
    QPushButton#ghost:hover {{ background: {t.surface_2}; color: {t.text}; }}
    QPushButton#nav {{
        background: transparent; border: 1px solid transparent; text-align: left;
        padding: 11px 14px; color: {t.muted}; border-radius: 10px;
    }}
    QPushButton#nav:hover {{ background: {t.surface_2}; color: {t.text}; }}
    QPushButton#nav:checked {{
        background: {t.accent_wash}; color: {t.text}; border: 1px solid {t.accent};
        font-weight: 650;
    }}
    QPushButton#nav:focus {{ border: 2px solid {t.focus}; padding: 10px 13px; }}

    QFrame#card, QFrame#dropZone, QFrame#bookRow, QFrame#preset, QFrame#settingRow,
    QFrame#tile {{
        background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
    }}
    QFrame#dropZone {{ border: 2px dashed {t.border_strong}; background: {t.surface}; }}
    QFrame#dropZone[active="true"] {{ border-color: {t.accent}; background: {t.accent_wash}; }}
    QFrame#bookRow:hover, QFrame#preset:hover, QFrame#tile:hover {{
        border-color: {t.border_strong}; background: {t.surface_2};
    }}
    QFrame#bookRow[selected="true"] {{ border: 2px solid {t.accent}; background: {t.accent_wash}; }}
    QFrame#preset[selected="true"] {{ border: 2px solid {t.accent}; background: {t.accent_wash}; }}
    QFrame#preset:focus, QFrame#bookRow:focus {{ border: 2px solid {t.focus}; }}
    QFrame#successCard {{ background: {t.success_wash}; border: 1px solid {t.success}; border-radius: 12px; }}
    QFrame#warningCard {{ background: {t.warning_wash}; border: 1px solid {t.warning}; border-radius: 12px; }}
    QFrame#dangerCard {{ background: {t.danger_wash}; border: 1px solid {t.danger}; border-radius: 12px; }}
    QFrame#metricCard {{ background: {t.surface_2}; border: 1px solid {t.border}; border-radius: 10px; }}
    QFrame#separator {{ background: {t.border}; max-height: 1px; border: none; }}

    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
        min-height: 26px; padding: 7px 11px; background: {t.surface_2};
        border: 1px solid {t.border_strong}; border-radius: 8px;
        selection-background-color: {t.accent}; selection-color: {t.accent_text};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
    QPlainTextEdit:focus, QTextEdit:focus {{ border: 2px solid {t.focus}; padding: 6px 10px; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {t.surface_2}; border: 1px solid {t.border};
        selection-background-color: {t.accent_wash}; padding: 4px;
    }}

    QCheckBox, QRadioButton {{ spacing: 10px; padding: 3px 0; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px; height: 18px; border: 1px solid {t.border_strong};
        background: {t.surface_2};
    }}
    QCheckBox::indicator {{ border-radius: 5px; }}
    QRadioButton::indicator {{ border-radius: 9px; }}
    QCheckBox::indicator:checked {{
        background: {t.accent}; border-color: {t.accent}; image: url({tick});
    }}
    QRadioButton::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
    QCheckBox:focus, QRadioButton:focus {{ color: {t.text}; }}
    QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border: 2px solid {t.focus}; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {t.muted}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: {SCROLL_BAR_WIDTH}px; background: transparent; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border_strong}; min-height: 30px; border-radius: 4px; }}
    QScrollBar:horizontal {{ height: {SCROLL_BAR_WIDTH}px; background: transparent; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t.border_strong}; min-width: 30px; border-radius: 4px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QProgressBar {{
        height: 8px; border: none; border-radius: 4px;
        background: {t.surface_3}; color: transparent;
    }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}

    QWidget#overlay {{ background: rgba(3, 8, 15, 190); }}
    QFrame#drawer {{ background: {t.sidebar}; border-left: 1px solid {t.border_strong}; }}
    QToolTip {{
        background: {t.surface_3}; color: {t.text};
        border: 1px solid {t.border_strong}; padding: 7px;
    }}
    """
