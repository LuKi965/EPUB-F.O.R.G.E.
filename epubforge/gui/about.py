"""The About dialog: who made this, under what licence, with what inside."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from .. import __version__, resources
from . import theme
from .strings import tr

REPOSITORY = "https://github.com/LuKi965/EPUB-F.O.R.G.E."


class AboutDialog(QDialog):
    def __init__(self, parent=None, palette: theme.Palette | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("about.title"))
        self.setMinimumWidth(520)
        colors = palette or theme.LIGHT

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)

        layout.addLayout(self._header(colors))
        layout.addWidget(self._separator(colors))
        layout.addWidget(
            self._section(
                tr("about.authors"),
                f"{tr('about.author.human')}<br/>{tr('about.author.ai')}",
                colors,
            )
        )
        layout.addWidget(
            self._section(
                tr("about.license"),
                f"{tr('about.license.body')}<br/>"
                f'<a href="{REPOSITORY}" style="color:{colors.accent};">{REPOSITORY}</a>',
                colors,
            )
        )
        layout.addWidget(
            self._section(
                tr("about.components"),
                tr("about.components.body").replace("\n", "<br/>"),
                colors,
            )
        )
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr("about.close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _header(self, colors: theme.Palette) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        icon_path = resources.app_icon()
        if icon_path is not None:
            badge = QLabel()
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                badge.setPixmap(
                    pixmap.scaled(
                        64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
            badge.setFixedSize(64, 64)
            row.addWidget(badge, alignment=Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)

        name = QLabel("EPUB F.O.R.G.E.")
        name.setStyleSheet(f"font-size: 17pt; font-weight: 600; color: {colors.text};")
        text.addWidget(name)

        subtitle = QLabel(tr("about.subtitle"))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {colors.accent}; font-size: 9.5pt; font-style: italic;")
        text.addWidget(subtitle)

        version = QLabel(tr("about.version", version=__version__))
        version.setStyleSheet(f"color: {colors.text_muted};")
        text.addWidget(version)

        tagline = QLabel(tr("about.tagline"))
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"color: {colors.text}; padding-top: 4px;")
        text.addWidget(tagline)

        row.addLayout(text, stretch=1)
        return row

    def _separator(self, colors: theme.Palette) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {colors.border}; background: {colors.border}; max-height: 1px;")
        return line

    def _section(self, heading: str, body: str, colors: theme.Palette) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        title = QLabel(heading.upper())
        title.setStyleSheet(
            f"color: {colors.text_muted}; font-size: 8.5pt; font-weight: 600; letter-spacing: 0.5px;"
        )
        layout.addWidget(title)

        content = QLabel(body)
        content.setWordWrap(True)
        content.setOpenExternalLinks(True)
        content.setTextFormat(Qt.RichText)
        content.setStyleSheet(f"color: {colors.text};")
        layout.addWidget(content)
        return frame
