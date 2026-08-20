"""PySide6 front end: drop books in, inspect what changed, write them out."""

from __future__ import annotations

import os
import tempfile
import sys

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import resources, version_string, watermark
from ..pipeline import Status, rebuild_all
from ..policy import GATES, HYPHEN_REVIEWS, RENDER_GATES, Policy
from ..quips import quip_for
from ..report import Level, Report, batch_to_json
from ..validate import find_epubcheck, validate
from . import theme
from .about import AboutDialog
from .tabs import CorpusPanel, DiagnosticsPanel, LibraryPanel
from .strings import LANGUAGES, language, set_language, tr

LEVEL_KEYS = {
    Level.FIX: "level.fix",
    Level.PRESERVED: "level.preserved",
    Level.WARN: "level.warn",
    Level.ERROR: "level.error",
    Level.INFO: "level.info",
}

STATUS_KEYS = {
    "queued": "status.queued",
    # Its own short label: "status.working" is the status *bar*'s sentence
    # and carries a {name} placeholder — in a table cell the template leaked
    # out literally, curly braces and all (found by the WP-21 chip demo).
    "working": "status.cell.working",
    "done": "status.done",
    "issues": "status.issues",
    "failed": "status.failed",
    "blocked": "status.blocked",
}

#: Which palette colour each status paints its chip with. Module-level and
#: keyed like `STATUS_KEYS` on purpose: EF-066 was a status that existed in
#: one table and not the other, and the window found out with a KeyError on
#: the one row a person most needs to read. The seventh audit's S-2 asked for
#: the invariant to be a test, and a test needs the mapping where it can see
#: it without building a window.
STATUS_COLOR_ROLES = {
    "queued": "text_muted",
    "working": "accent",
    "done": "fix",
    "issues": "warn",
    # A gate's deliberate refusal, painted like an error: either way, this
    # book needs the person's eyes (EF-066).
    "blocked": "error",
    "failed": "error",
}


class Worker(QObject):
    """Runs the rebuild off the UI thread."""

    progress = Signal(int, str)
    #: Emitted when the rebuild is done and the validator takes over. Without
    #: it the window says "rebuilding" for the seconds a JVM needs to start,
    #: which is the longest part of the job and looked like a freeze.
    validating = Signal(int, str)
    finished_one = Signal(int, object)
    finished_all = Signal()

    def __init__(
        self,
        jobs: list[tuple[str, str]],
        policy: Policy,
        run_check: bool,
        resolver=None,
        plan_only: bool = False,
    ):
        super().__init__()
        #: BA-2026-003. A plan run does everything a real one does — every
        #: stage, K1, the balance, the validator, the appearance check — and
        #: stops one step short of the destination. Implemented by moving the
        #: destination rather than by teaching the pipeline a second mode:
        #: a rebuild that skipped its own final step would be a code path
        #: nobody exercises, which is the opposite of what a plan is for.
        self._plan_room = (
            tempfile.TemporaryDirectory(prefix="epubforge-plan-") if plan_only else None
        )
        self.plan_only = plan_only
        if self._plan_room is not None:
            jobs = [
                (source, os.path.join(self._plan_room.name, os.path.basename(target)))
                for source, target in jobs
            ]
        self._jobs = jobs
        self._policy = policy
        self._run_check = run_check
        #: Who the rebuild asks when it cannot decide — see `gui/ask.py`. It
        #: belongs to the GUI thread and is called from this one, which is the
        #: whole reason it is an object with a blocking signal rather than a
        #: function.
        self._resolver = resolver
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for index, (source, destination) in enumerate(self._jobs):
            if self._cancelled:
                break
            self.progress.emit(index, os.path.basename(source))
            try:
                # Every rendition, each into its own file. For a book with one
                # — which is every book but a handful — this is exactly what
                # `rebuild` did, and the list has one entry.
                produced = rebuild_all(
                    source, destination, self._policy, resolver=self._resolver,
                    # DELTA-2026-08-15-001: the loop above only looked between
                    # books, so Cancel on a large one meant "finish this one
                    # first". Handed down, it is asked once per document.
                    cancelled=lambda: self._cancelled,
                )
                result = produced[0]
                if self._run_check:
                    for one in produced:
                        # `report.validated` means the publication gate has
                        # already asked EPUBCheck about these exact bytes, under
                        # the staging name they carried a moment earlier. Asking
                        # again costs about four and a half seconds a book and
                        # writes the same verdict into the report a second time,
                        # which is how a strict run came back saying
                        # `epubcheck.clean` twice.
                        if one.output_path and one.report.validated is None:
                            self.validating.emit(index, os.path.basename(source))
                            validate(
                                one.output_path,
                                one.report,
                                content_untouched=not self._policy.rewrite_content,
                            )
                if len(produced) > 1:
                    # The window shows one row per source, so the siblings would
                    # otherwise be written and never mentioned.
                    result.report.add(
                        "package",
                        Level.INFO,
                        "package.renditions-written",
                        values={
                            "count": len(produced),
                            "names": ", ".join(
                                os.path.basename(one.output_path or "—") for one in produced
                            ),
                        },
                    )
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                report = Report(source=source, output=destination)
                report.add(
                    "gui",
                    Level.ERROR,
                    "gui.unexpected-failure",
                    values={"error": f'{type(exc).__name__}: {exc}'},
                )
                from ..pipeline import Result

                result = Result(report, None, None)
            self.finished_one.emit(index, result)
        self.finished_all.emit()


def settings() -> QSettings:
    return QSettings("EPUB-Forge", "EPUB-Forge")


class _NavTabs:
    """The old QTabWidget surface of the new side navigation — WP-21 phase B.

    The window used to be a QTabWidget and half the test suite (rightly)
    reaches features through `window.tabs`. The navigation is a list and a
    stack now, but the promise those tests hold — every feature has a page,
    every page is reachable — has not changed, so the surface they hold it
    through does not change either.
    """

    def __init__(self, nav: QListWidget, pages: QStackedWidget):
        self._nav = nav
        self._pages = pages

    def count(self) -> int:
        return self._pages.count()

    def widget(self, index: int):
        return self._pages.widget(index)

    def tabText(self, index: int) -> str:  # noqa: N802 - Qt casing, kept on purpose
        item = self._nav.item(index)
        return item.text() if item is not None else ""

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self._nav.setCurrentRow(index)

    def currentIndex(self) -> int:  # noqa: N802
        return self._nav.currentRow()


class _StatusChip:
    """Paints the queue's status cell as a Fluent pill — WP-21 phase B2.

    A delegate rather than rich text, because a QTableWidgetItem cannot round
    its own corners and a real chip is the difference the owner pointed at:
    the sidebar spoke the new language and the middle of the window did not.
    The colour comes from the item's foreground, which `_set_status` already
    chooses per status — so a new status never needs a second table here.
    """

    @staticmethod
    def install(table: QTableWidget, border: str) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtWidgets import QStyledItemDelegate

        class Chip(QStyledItemDelegate):
            def sizeHint(self, option, index):  # noqa: N802 - Qt casing
                hint = super().sizeHint(option, index)
                hint.setWidth(hint.width() + 18)
                return hint

            def paint(self, painter, option, index):
                text = index.data() or ""
                if not text:
                    return super().paint(painter, option, index)
                color = index.data(Qt.ForegroundRole)
                color = color.color() if color is not None else option.palette.text().color()
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing, True)
                metrics = option.fontMetrics
                width = metrics.horizontalAdvance(text) + 20
                height = metrics.height() + 6
                rect = QRectF(
                    option.rect.x() + 6,
                    option.rect.center().y() - height / 2,
                    width,
                    height,
                )
                fill = QColor(color)
                fill.setAlpha(28)
                painter.setPen(Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRoundedRect(rect, height / 2, height / 2)
                painter.setPen(color)
                painter.drawText(rect, Qt.AlignCenter, text)
                # The column separator the stylesheet draws for every other
                # cell — a custom paint bypasses QSS, so it is drawn by hand
                # or this one column loses its boundary.
                painter.setPen(QPen(QColor(border)))
                painter.drawLine(option.rect.topRight(), option.rect.bottomRight())
                painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
                painter.restore()

        table.setItemDelegateForColumn(1, Chip(table))


class MainWindow(QMainWindow):
    def __init__(self, palette: theme.Palette | None = None, initial_files: list[str] | None = None):
        super().__init__()
        #: Set when the language changes; run() rebuilds the window so every
        #: label is retranslated, carrying the queue across.
        self.restart_requested = False
        self.palette_colors = palette or theme.LIGHT
        self.setWindowTitle(tr("window.title", version=version_string()))
        # A fixed 1180×760 is a comfortable size on the machine it was written
        # on and an unusable one on a 1366×768 laptop, where it opens taller
        # than the screen. Ask for four fifths of the available desktop instead,
        # capped so it does not sprawl on a large monitor, and set a floor low
        # enough that the layout still works at the bottom of that range.
        self.setMinimumSize(880, 560)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1280, int(available.width() * 0.8)),
                min(860, int(available.height() * 0.85)),
            )
        else:  # pragma: no cover - only when Qt reports no screen at all
            self.resize(1100, 720)
        self.setAcceptDrops(True)

        self._sources: list[str] = []
        self._results: dict[int, object] = {}
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self._epubcheck = find_epubcheck() is not None

        self._build_ui()
        self._build_menu()
        if initial_files:
            self._add(initial_files)

    # ---------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        # WP-21 phase B: a side navigation instead of a top tab bar. The four
        # pages are the same four panels; what changed is where their names
        # live and how much of the window says "application" before it says
        # "content". The owner's rule for this package: take the design
        # language, keep our flows — nothing here is reachable one click
        # later than it was.
        from . import theme as theme_module

        nav_pane = QWidget()
        nav_pane.setObjectName("navPane")
        nav_pane.setFixedWidth(212)
        nav_layout = QVBoxLayout(nav_pane)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(10)

        brand = QWidget()
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(2, 0, 0, 4)
        brand_row.setSpacing(8)
        glyph = QLabel("EF")
        glyph.setObjectName("brandGlyph")
        glyph.setFixedSize(30, 30)
        glyph.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(glyph)
        names = QVBoxLayout()
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        title = QLabel("EPUB F.O.R.G.E.")
        title.setObjectName("brandTitle")
        names.addWidget(title)
        version = QLabel(version_string())
        version.setObjectName("brandVersion")
        names.addWidget(version)
        brand_row.addLayout(names)
        brand_row.addStretch(1)
        nav_layout.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("sideNav")
        self.nav.setIconSize(QSize(17, 17))
        self.nav.setUniformItemSizes(True)
        self.pages = QStackedWidget()

        for glyph_name, label, page in (
            ("rebuild", tr("tab.rebuild"), self._build_rebuild_tab()),
            ("library", tr("tab.library"), LibraryPanel(self.palette_colors)),
            ("corpus", tr("tab.corpus"), CorpusPanel(self.palette_colors)),
            ("diagnostics", tr("tab.diagnostics"), DiagnosticsPanel(self.palette_colors)),
        ):
            item = QListWidgetItem(
                QIcon(theme_module.nav_icon(glyph_name, self.palette_colors.text_muted)),
                label,
            )
            self.nav.addItem(item)
            self.pages.addWidget(page)

        nav_layout.addWidget(self.nav, stretch=1)

        central = QWidget()
        columns = QHBoxLayout(central)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns.addWidget(nav_pane)
        columns.addWidget(self.pages, stretch=1)
        self.setCentralWidget(central)

        self.tabs = _NavTabs(self.nav, self.pages)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._tab_changed)
        self.nav.setCurrentRow(0)
        self._tab_changed(0)

    def _tab_changed(self, index: int) -> None:
        """The status line belongs to the tab, not to the window.

        "Drop EPUB files anywhere in this window" is good advice on the rebuild
        tab and simply untrue on the other two, which take a folder.
        """
        if index == 0:
            hint = tr("status.hint")
            if not self._epubcheck:
                hint = f"{hint}   ·   {tr('status.hint.nocheck')}"
        else:
            hint = tr("library.intro") if index == 1 else tr("corpus.intro")
        self.statusBar().showMessage(hint)

    def _build_rebuild_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_source_row())

        # Vertical first: the queue and its report belong together, and giving
        # the options their own column at every width is what left a third of
        # the window empty on the screenshot that started this.
        work = QSplitter(Qt.Vertical)
        work.addWidget(self._build_table())
        work.addWidget(self._build_report_view())
        work.setStretchFactor(0, 3)
        work.setStretchFactor(1, 2)
        work.setChildrenCollapsible(False)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(work)
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([640, 420])
        layout.addWidget(splitter, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        return page

    def _build_report_view(self) -> QWidget:
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Cascadia Mono, Consolas, monospace", 9))
        self.report_view.setPlaceholderText(tr("report.placeholder"))
        self.report_view.setMinimumHeight(120)
        return self.report_view

    def _build_source_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        add = QPushButton(tr("toolbar.add"))
        add.setObjectName("tonal")
        add.setToolTip(tr("toolbar.add.tip"))
        add.clicked.connect(self._choose_files)
        layout.addWidget(add)

        clear = QPushButton(tr("toolbar.clear"))
        clear.setToolTip(tr("toolbar.clear.tip"))
        clear.clicked.connect(self._clear)
        layout.addWidget(clear)

        layout.addSpacing(16)
        output_label = QLabel(tr("toolbar.output"))
        output_label.setObjectName("sectionLabel")
        layout.addWidget(output_label)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(tr("toolbar.output.placeholder"))
        self.output_edit.setToolTip(tr("toolbar.output.tip"))
        layout.addWidget(self.output_edit, stretch=1)

        browse = QPushButton(tr("toolbar.browse"))
        browse.setToolTip(tr("toolbar.browse.tip"))
        browse.clicked.connect(self._choose_output)
        layout.addWidget(browse)
        return row

    def _build_table(self) -> QWidget:
        self.table = QTableWidget(0, 5)
        headers = [
            (tr("table.book"), None),
            (tr("table.status"), None),
            (tr("table.fixed"), tr("table.fixed.tip")),
            (tr("table.kept"), tr("table.kept.tip")),
            (tr("table.issues"), tr("table.issues.tip")),
        ]
        # Uppercase by hand: Qt stylesheets have no text-transform, and the
        # quiet small-caps header is half of what makes a table read as a card.
        self.table.setHorizontalHeaderLabels([label.upper() for label, _ in headers])
        for column, (_, tip) in enumerate(headers):
            if tip:
                self.table.horizontalHeaderItem(column).setToolTip(tip)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        # No zebra: the row separator below replaces it, which is how a
        # Fluent list reads — lines, hover, selection, not stripes.
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected_report)
        _StatusChip.install(self.table, self.palette_colors.border)

        # The empty queue invites instead of sitting blank — WP-21 phase B2.
        # A child of the viewport, so it scrolls with nothing and never
        # swallows a click or a drop: events pass through it.
        from . import theme as theme_module

        hint = QLabel(
            f'<div align="center">'
            f'<img src="{theme_module.nav_icon("drop", self.palette_colors.text_muted)}" '
            f'width="40" height="40"/><br/><br/>{tr("table.empty")}</div>',
            self.table.viewport(),
        )
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._empty_hint = hint
        self.table.viewport().installEventFilter(self)
        self._update_empty_hint()
        return self.table

    def eventFilter(self, watched, event) -> bool:
        if watched is self.table.viewport() and event.type() in (
            event.Type.Resize,
            event.Type.Paint,
        ):
            self._empty_hint.resize(self.table.viewport().size())
        return super().eventFilter(watched, event)

    def _update_empty_hint(self) -> None:
        self._empty_hint.setVisible(self.table.rowCount() == 0)
        self._empty_hint.resize(self.table.viewport().size())

    def _build_side_panel(self) -> QWidget:
        """The options, in a column that scrolls rather than being cut off.

        Three stacked cards plus a button need more height than a 768-pixel
        laptop has once the title bar, the tab strip and the status bar are
        taken out. Without the scroll area the bottom card simply vanishes, and
        the run button with it.
        """
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_policy_box())
        layout.addWidget(self._build_compat_box())
        layout.addWidget(self._build_metadata_box())
        layout.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidget(inner)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(scroller, stretch=1)

        self.run_button = QPushButton(tr("action.run"))
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip(tr("action.run.tip"))
        self.run_button.setMinimumHeight(42)
        self.run_button.clicked.connect(self._run)
        column.addWidget(self.run_button)

        # Wide enough for the longest option label, narrow enough to leave the
        # queue the majority of any window. Tightened in WP-21 phase B3: with
        # the side navigation in place, every pixel this column keeps is a
        # pixel the book titles in the queue lose — the first column was down
        # to eight characters before eliding.
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(430)
        return panel

    def _build_policy_box(self) -> QWidget:
        # WP-21 phase B4: the sections became *cards*, one per concern — the
        # owner's line was that the right column still did not speak the
        # sidebar's language, and eight small cards is that language. Same
        # switches, same attribute names, one scrolling column; only the
        # walls moved.
        column = QWidget()
        stack = QVBoxLayout(column)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(10)

        def card(key: str) -> QVBoxLayout:
            box = QGroupBox(tr(key))
            inner = QVBoxLayout(box)
            inner.setSpacing(7)
            stack.addWidget(box)
            return inner

        layout = card("policy.section.mode")
        label = QLabel(tr("policy.mode.label"))
        label.setObjectName("sectionLabel")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.mode_combo = QComboBox()
        self.mode_combo.setToolTip(tr("policy.mode.tip"))
        modes = (
            ("preserve", "policy.mode.preserve"),
            ("strict", "policy.mode.strict"),
            ("minimal", "policy.mode.minimal"),
        )
        for index, (value, key) in enumerate(modes):
            self.mode_combo.addItem(tr(key), value)
            # Per-item tooltips let the consequences of each mode be read before
            # committing to one, which is the whole point of the choice.
            self.mode_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        layout.addWidget(self.mode_combo)

        layout = card("policy.section.container")
        self.ncx_check = self._checkbox(layout, "policy.ncx", checked=True)
        self.orphans_check = self._checkbox(layout, "policy.orphans", checked=False)
        # The last thing in the program that deleted a file by name. It now
        # proves the book does not use it first — and it is a tick all the
        # same, because the standing rule has no exception for obvious cases.
        self.junk_check = self._checkbox(layout, "policy.junk", checked=True)
        self.layout_check = self._checkbox(layout, "policy.layout", checked=True)
        self.scripts_check = self._checkbox(layout, "policy.scripts", checked=False)

        layout = card("policy.section.styles")
        # Ticked by "force the standard" and untickable there all the same.
        # The owner asked for this as a standing rule rather than about this
        # feature: whatever the application ever deletes must be optional to
        # untick, or asked about first.
        self.dead_check = self._checkbox(layout, "policy.dead", checked=False)
        # Not folded into the tick above: the fifth audit measured this sweep
        # an order of magnitude larger than the sheets', so it enters through
        # its own door (D-028).
        self.style_sweep_check = self._checkbox(layout, "policy.style-sweep", checked=True)
        # Pillar 1 of the 0.3 plan (D-031); on by default since D-032, the
        # same road the sweep travelled.
        self.class_names_check = self._checkbox(layout, "policy.class-names", checked=True)
        # EF-029. Off by default and in the window rather than only behind a
        # flag, because it is a change to the publisher's stylesheet and S-04
        # says the person deciding gets to see the switch.
        self.relative_units_check = self._checkbox(
            layout, "policy.relative.units", checked=False
        )
        self.typography_check = self._checkbox(layout, "policy.typography", checked=False)

        layout = card("policy.section.store")
        watermark_label = QLabel(tr("policy.watermark.label"))
        watermark_label.setObjectName("sectionLabel")
        watermark_label.setWordWrap(True)
        watermark_label.setToolTip(tr("policy.watermark.tip"))
        layout.addWidget(watermark_label)
        self.watermark_label = watermark_label

        self.watermark_combo = QComboBox()
        self.watermark_combo.setToolTip(tr("policy.watermark.tip"))
        for index, value in enumerate(watermark.MODES):
            key = f"policy.watermark.{value}"
            self.watermark_combo.addItem(tr(key), value)
            # Each option removes a different amount, and one of them removes
            # the token altogether — nobody should have to guess which.
            self.watermark_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.watermark_combo.setCurrentIndex(watermark.MODES.index(Policy().watermarks))
        layout.addWidget(self.watermark_combo)
        # WP-17 / D-019. Off, and next to the watermark setting rather than
        # inside it: that one asks how visible a token may be, this one asks
        # whether a sentence may be deleted.
        self.shop_notices_check = self._checkbox(
            layout, "policy.shop.notices", checked=False
        )

        layout = card("policy.section.assets")
        # Two more things this program changes about a book, and the owner's
        # standing rule says a person gets the last word on each: fonts whose
        # obfuscation is undone, and images converted out of a format EPUB 3
        # does not require. Both were on and neither was reachable from here,
        # which for somebody who runs the Windows build means they were not
        # switches at all.
        self.fonts_check = self._checkbox(layout, "policy.fonts", checked=True)
        self.images_check = self._checkbox(layout, "policy.images", checked=True)

        layout = card("policy.section.questions")
        # There used to be a checkbox here — "rebuild even if part of the source
        # cannot be read". It is gone with the setting behind it: a source this
        # program could not read in full now stops the rebuild, with no way
        # past, because a book quietly missing a chapter or an ornament is the
        # outcome this whole program exists against. What replaces it is the
        # damage report and, next to it, the two things worth doing about a
        # damaged file: check a shelf for damage before it matters, and rebuild
        # one good copy out of two broken ones.

        # F-010's other half. A reference whose anchor does not exist cannot be
        # repaired from the file, and the program refuses to invent an answer —
        # so the only way one of these is ever *resolved* rather than reported
        # is a person looking at it. On by default: this is a window, somebody
        # is here, and asking is the point rather than the fallback.
        self.ask_check = self._checkbox(layout, "policy.ask", checked=True)
        # Pillar 3 of the 0.3 plan. Detection changes nothing and the question's
        # safe answer is "leave it"; this tick declines the question in advance.
        self.footnotes_check = self._checkbox(layout, "policy.footnotes", checked=True)
        self.hyphens_check = self._checkbox(layout, "policy.hyphens", checked=True)
        # BA-2026-001's remaining half. 67 evidenced candidates against 189
        # that the book itself does not settle — so the weaker classes are one
        # question carrying the words rather than 189 questions.
        hyphen_label = QLabel(tr("policy.hyphen.review"))
        hyphen_label.setToolTip(tr("policy.hyphen.review.tip"))
        layout.addWidget(hyphen_label)
        self.hyphen_review_combo = QComboBox()
        self.hyphen_review_combo.setToolTip(tr("policy.hyphen.review.tip"))
        for index, value in enumerate(HYPHEN_REVIEWS):
            key = f"policy.hyphen.review.{value}"
            self.hyphen_review_combo.addItem(tr(key), value)
            self.hyphen_review_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.hyphen_review_combo.setCurrentIndex(
            HYPHEN_REVIEWS.index(Policy().hyphen_review)
        )
        layout.addWidget(self.hyphen_review_combo)
        # EF-050. Beside the hyphens because it is the other setting that
        # touches characters a reader sees — and unlike them it puts the text
        # back rather than taking it away.
        self.encoding_check = self._checkbox(
            layout, "policy.repair.encoding", checked=False
        )
        # F-004's half of the same rule. A package that only parsed after
        # recovery gives fields nobody wrote; with the window open the rebuild
        # asks about each one, and this is the same consent in advance.
        self.reconstructed_check = self._checkbox(
            layout, "policy.metadata.reconstructed", checked=False
        )
        # BA-2026-001 and BA-2026-002. Detection is on because detection changes
        # nothing; the answers are remembered because being asked the same
        # forty-six questions on every rebuild is how a feature becomes
        # something people switch off.
        self.remember_check = self._checkbox(layout, "policy.remember", checked=True)

        layout = card("policy.section.gates")
        self.validate_check = self._checkbox(
            layout, "policy.validate", checked=self._epubcheck, enabled=self._epubcheck
        )
        if not self._epubcheck:
            self.validate_check.setToolTip(tr("policy.validate.missing"))
        # The audit's K.2 invariant 12, as a choice rather than a policy this
        # program makes on somebody's behalf. It follows the mode by default —
        # strict refuses an invalid file, the other two publish and report — and
        # the mode combo resets it, so changing the mode never leaves a stricter
        # setting behind than the mode implies.
        gate_label = QLabel(tr("policy.gate"))
        gate_label.setToolTip(tr("policy.gate.tip"))
        layout.addWidget(gate_label)
        self.gate_label = gate_label

        self.gate_combo = QComboBox()
        self.gate_combo.setToolTip(tr("policy.gate.tip"))
        for index, value in enumerate(GATES):
            key = f"policy.gate.{value}"
            self.gate_combo.addItem(tr(key), value)
            # Each one refuses a different set of books, and one of them refuses
            # books this program did nothing wrong to. That has to be readable
            # before it is chosen, not after a batch stops.
            self.gate_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        layout.addWidget(self.gate_combo)
        # F-028, and the owner's own choice of default: "stop". He was shown the
        # cost — about thirty-six seconds a book — and the measurement behind it,
        # zero refusals across his thirty-two books, and chose the strong one.
        render_label = QLabel(tr("policy.render.gate"))
        render_label.setObjectName("sectionLabel")
        render_label.setToolTip(tr("policy.render.tip"))
        layout.addWidget(render_label)
        self.render_combo = QComboBox()
        self.render_combo.setToolTip(tr("policy.render.tip"))
        for index, value in enumerate(RENDER_GATES):
            key = f"policy.render.gate.{value}"
            self.render_combo.addItem(tr(key), value)
            self.render_combo.setItemData(index, tr(f"{key}.tip"), Qt.ToolTipRole)
        self.render_combo.setCurrentIndex(RENDER_GATES.index(Policy().render_gate))
        layout.addWidget(self.render_combo)
        # WP-11. K1 in the publication gate: every character of the source in
        # the output, in the same order. On by default and here rather than
        # hidden, because the owner's rule is that a choice belongs to him — and
        # because somebody rebuilding a book with a deliberately altered text
        # has a reason this program cannot know.
        self.text_check = self._checkbox(
            layout, "policy.text.invariant", checked=Policy().verify_text_survives
        )
        # He asked for this one in those words: there has to be an option to
        # check the whole book. A sample is somebody else's choice about which
        # pages of *his* book are worth looking at.
        self.render_all_check = self._checkbox(layout, "policy.render.all", checked=False)
        # DELTA-2026-08-15-001. Separate from the gate above and separate on
        # purpose: that one says what to do when the check *runs* and finds a
        # loss, this one says what to do when it cannot run at all. With the
        # window open the rebuild asks; this is the same consent given in
        # advance, for a batch nobody is sitting in front of.
        self.unverified_check = self._checkbox(
            layout, "policy.render.unverified", checked=False
        )

        layout = card("policy.section.run")
        # BA-2026-003. Beside the settings rather than beside the button,
        # because it is a question about this run and not about this book.
        self.plan_check = self._checkbox(layout, "policy.plan.only", checked=False)
        # Two builds of one book, byte for byte the same. Off by default,
        # because the honest modification date of a file produced now is now.
        self.reproducible_check = self._checkbox(layout, "policy.reproducible", checked=False)
        # EF-020, after the measurement. On by default, because the alternative
        # default is the process being killed halfway with nothing written and
        # nothing said — and this is the build most likely to meet that: a
        # batch of books in one window, on a laptop, on Windows.
        self.memory_check = self._checkbox(layout, "policy.memory", checked=True)
        # And the budget itself, because "everything is reachable from the
        # window" does not stop at the switch. Empty means "ask the machine
        # what is free", which is the right default and not the only answer a
        # person might want: somebody working while a batch runs may prefer a
        # fixed ceiling that does not move with whatever else they open.
        self.memory_limit_edit = QLineEdit()
        self.memory_limit_edit.setPlaceholderText(tr("policy.memory.limit.placeholder"))
        self.memory_limit_edit.setToolTip(tr("policy.memory.limit.tip"))
        layout.addWidget(self.memory_limit_edit)
        self.memory_check.toggled.connect(self.memory_limit_edit.setEnabled)

        self._mode_changed()
        return column

    def _checkbox(self, layout, key: str, *, checked: bool, enabled: bool = True) -> QCheckBox:
        box = QCheckBox(tr(key))
        box.setToolTip(tr(f"{key}.tip"))
        box.setChecked(checked)
        box.setEnabled(enabled)
        layout.addWidget(box)
        return box

    def _build_compat_box(self) -> QGroupBox:
        """Opt-in concessions to particular devices — none of them on by default."""
        box = QGroupBox(tr("compat.group"))
        layout = QVBoxLayout(box)
        layout.setSpacing(7)

        hint = QLabel(tr("compat.hint"))
        hint.setObjectName("sectionLabel")
        hint.setWordWrap(True)
        hint.setToolTip(tr("compat.hint.tip"))
        layout.addWidget(hint)

        self.compat_checks: dict[str, QCheckBox] = {}
        for profile in ("kindle", "kobo", "apple", "legacy"):
            self.compat_checks[profile] = self._checkbox(
                layout, f"compat.{profile}", checked=False
            )

        # Stated in the panel rather than only in a tooltip: it is the one
        # consequence of ticking these boxes that outlives the run.
        note = QLabel(tr("compat.note"))
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {self.palette_colors.text_muted}; font-size: 8.5pt; font-style: italic;"
        )
        layout.addWidget(note)
        return box

    def _build_metadata_box(self) -> QGroupBox:
        box = QGroupBox(tr("meta.group"))
        layout = QVBoxLayout(box)
        layout.setSpacing(4)
        self.title_edit = self._field(layout, "meta.title")
        self.author_edit = self._field(layout, "meta.author")
        self.language_edit = self._field(layout, "meta.language")
        return box

    def _field(self, layout, key: str) -> QLineEdit:
        label = QLabel(tr(key))
        label.setObjectName("fieldLabel")
        label.setToolTip(tr(f"{key}.tip"))
        layout.addWidget(label)
        edit = QLineEdit()
        edit.setPlaceholderText(tr("meta.placeholder"))
        edit.setToolTip(tr(f"{key}.tip"))
        layout.addWidget(edit)
        return edit

    def _mode_changed(self) -> None:
        """Minimal mode regenerates only the container, so content knobs do nothing."""
        content_mode = self.mode_combo.currentData() != "minimal"
        for widget in (self.orphans_check, self.layout_check, self.scripts_check,
                       self.dead_check, self.typography_check,
                       self.watermark_combo, self.watermark_label):
            widget.setEnabled(content_mode)
        # Follows the mode rather than overriding it: "force the standard"
        # means tidiness wins, so it arrives ticked — and stays untickable.
        self.dead_check.setChecked(
            content_mode and self.mode_combo.currentData() == "strict"
        )
        # The gate follows the mode for the same reason: the mode is the answer
        # to "how much may this program change", and refusing to publish an
        # invalid file is part of that answer rather than a separate opinion.
        # Set rather than merely defaulted, so switching strict → preserve does
        # not leave a batch quietly refusing books preserve exists to publish.
        preset = Policy.preset(self.mode_combo.currentData())
        self.gate_combo.setCurrentIndex(GATES.index(preset.validate_before_publish))

    def _merge_copies(self) -> None:
        """One good book out of two damaged in different places.

        In the File menu rather than beside the rebuild, because it is not a
        rebuild: it produces a source, and a source is what this program then
        refuses or accepts on its own terms.
        """
        from .merge import MergeDialog

        MergeDialog(self, self.palette_colors).exec()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("menu.file"))
        for label, slot, shortcut in (
            (tr("toolbar.add"), self._choose_files, "Ctrl+O"),
            (tr("action.save"), self._save_report, "Ctrl+S"),
            (tr("action.save.batch"), self._save_batch_report, "Ctrl+Shift+S"),
            (tr("menu.merge"), self._merge_copies, "Ctrl+M"),
            (tr("menu.quit"), self.close, "Ctrl+Q"),
        ):
            action = QAction(label, self)
            action.triggered.connect(slot)
            action.setShortcut(shortcut)
            file_menu.addAction(action)

        settings_menu = self.menuBar().addMenu(tr("menu.settings"))
        language_menu = settings_menu.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = settings().value("language", "pl")
        for code in LANGUAGES:
            action = QAction(tr(f"language.{code}"), self, checkable=True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _checked=False, c=code: self._change_language(c))
            group.addAction(action)
            language_menu.addAction(action)

        help_menu = self.menuBar().addMenu(tr("menu.help"))
        about = QAction(tr("menu.about"), self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _change_language(self, code: str) -> None:
        if code == settings().value("language", "pl"):
            return
        settings().setValue("language", code)
        set_language(code)
        self.restart_requested = True
        self.close()

    def _show_about(self) -> None:
        AboutDialog(self, self.palette_colors).exec()

    # ------------------------------------------------------------ file input
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._add(
            [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.toLocalFile().lower().endswith(".epub")
            ]
        )

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("dialog.selectfiles"), "", tr("dialog.filter")
        )
        self._add(files)

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("dialog.selectfolder"))
        if directory:
            self.output_edit.setText(directory)

    def _add(self, files: list[str]) -> None:
        for path in files:
            if path and path not in self._sources:
                self._sources.append(path)
                row = self.table.rowCount()
                self.table.insertRow(row)
                item = QTableWidgetItem(os.path.basename(path))
                item.setToolTip(path)
                self.table.setItem(row, 0, item)
                self._set_status(row, "queued")
                for column in (2, 3, 4):
                    self.table.setItem(row, column, QTableWidgetItem("—"))
        self._update_empty_hint()
        self.statusBar().showMessage(tr("status.queued.count", count=len(self._sources)))

    def _clear(self) -> None:
        self._sources.clear()
        self._results.clear()
        self.table.setRowCount(0)
        self.report_view.clear()
        self._update_empty_hint()

    def _set_status(self, row: int, status: str) -> None:
        item = QTableWidgetItem(tr(STATUS_KEYS[status]))
        role = STATUS_COLOR_ROLES.get(status, "text")
        item.setForeground(QColor(getattr(self.palette_colors, role)))
        self.table.setItem(row, 1, item)

    # ------------------------------------------------------------- execution
    def _policy(self) -> Policy:
        policy = Policy.preset(self.mode_combo.currentData())
        policy.write_ncx = self.ncx_check.isChecked()
        policy.compat_profiles = tuple(
            name for name, box in self.compat_checks.items() if box.isChecked()
        )
        if self.mode_combo.currentData() != "minimal":
            policy.drop_orphans = self.orphans_check.isChecked()
            policy.remove_junk = self.junk_check.isChecked()
            policy.reorganize_files = self.layout_check.isChecked()
            policy.strip_scripts = self.scripts_check.isChecked()
            policy.remove_dead = self.dead_check.isChecked()
            policy.sweep_style_blocks = self.style_sweep_check.isChecked()
            policy.translate_class_names = self.class_names_check.isChecked()
            policy.link_footnotes = self.footnotes_check.isChecked()
            policy.watermarks = self.watermark_combo.currentData()
            policy.typography = self.typography_check.isChecked()
            policy.transcode_images = self.images_check.isChecked()
        policy.deobfuscate_fonts = self.fonts_check.isChecked()
        policy.reproducible = self.reproducible_check.isChecked()
        policy.render_gate = self.render_combo.currentData()
        policy.verify_text_survives = self.text_check.isChecked()
        policy.render_sample = 0 if self.render_all_check.isChecked() else 12
        policy.accept_unverified_render = self.unverified_check.isChecked()
        policy.accept_reconstructed_metadata = self.reconstructed_check.isChecked()
        policy.hyphen_review = self.hyphen_review_combo.currentData()
        policy.detect_hyphens = self.hyphens_check.isChecked()
        policy.relative_units = self.relative_units_check.isChecked()
        policy.remove_shop_notices = self.shop_notices_check.isChecked()
        policy.repair_encoding = self.encoding_check.isChecked()
        policy.remember_decisions = self.remember_check.isChecked()
        policy.check_memory = self.memory_check.isChecked()
        typed = self.memory_limit_edit.text().strip()
        if typed:
            from ..cli import _bytes_from

            try:
                policy.memory_limit = _bytes_from(typed)
            except ValueError:
                # Something that is not a size. Ignored rather than refused:
                # the field is a narrowing of a limit that already has a sane
                # default, so falling back to the machine's own answer is the
                # behaviour somebody who mistyped would have wanted anyway.
                policy.memory_limit = None
        policy.validate_before_publish = self.gate_combo.currentData()
        for key, edit in (
            ("title", self.title_edit),
            ("author", self.author_edit),
            ("language", self.language_edit),
        ):
            value = edit.text().strip()
            if value:
                policy.metadata_overrides[key] = value
                if key == "language":
                    policy.default_language = value
        return policy

    def _ask_resolver(self):
        """Somebody for the rebuild to ask, or nobody, as the box says.

        Built fresh for each run and parented to the window, so it lives in the
        GUI thread — which is the requirement the whole arrangement exists to
        satisfy. `None` means the rebuild behaves exactly as it does in a batch:
        it changes nothing it cannot justify, and reports what it left.
        """
        if not self.ask_check.isChecked():
            return None
        from .ask import Ask

        self._resolver = Ask(self)
        return self._resolver

    def _run(self) -> None:
        if not self._sources:
            QMessageBox.information(self, tr("dialog.nothing.title"), tr("dialog.nothing.body"))
            return
        if self._thread is not None:
            return

        output_dir = self.output_edit.text().strip()
        jobs: list[tuple[str, str]] = []
        for source in self._sources:
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                destination = os.path.join(output_dir, os.path.basename(source))
            else:
                destination = f"{os.path.splitext(source)[0]}.forged.epub"
            if os.path.abspath(destination) == os.path.abspath(source):
                QMessageBox.warning(
                    self,
                    tr("dialog.overwrite.title"),
                    tr("dialog.overwrite.body", name=os.path.basename(source)),
                )
                return
            jobs.append((source, destination))

        self.progress.setVisible(True)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.run_button.setEnabled(False)

        self._thread = QThread()
        self._worker = Worker(
            jobs,
            self._policy(),
            self.validate_check.isChecked(),
            self._ask_resolver(),
            plan_only=self.plan_check.isChecked(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.validating.connect(self._on_validating)
        self._worker.finished_one.connect(self._on_one_finished)
        self._worker.finished_all.connect(self._on_all_finished)
        self._thread.start()

    def _on_progress(self, index: int, name: str) -> None:
        self._set_status(index, "working")
        self.statusBar().showMessage(tr("status.working", name=name))

    def _on_validating(self, index: int, name: str) -> None:
        self.statusBar().showMessage(tr("status.validating", name=name))

    def _on_one_finished(self, index: int, result) -> None:
        self._results[index] = result
        report = result.report

        # From the status the pipeline reports, not from whether a file appeared.
        # Those two used to be the same question and were not the same answer:
        # a stage could crash and the file appeared anyway.
        status = getattr(result, "status", None)
        if status is not None and not status.wrote_a_file:
            self._set_status(index, "blocked" if status is Status.BLOCKED else "failed")
        elif report.count(Level.ERROR):
            self._set_status(index, "issues")
        else:
            self._set_status(index, "done")

        counts = (
            report.count(Level.FIX),
            report.count(Level.PRESERVED),
            report.count(Level.ERROR) + report.count(Level.WARN),
        )
        for column, value in enumerate(counts, start=2):
            self.table.setItem(index, column, QTableWidgetItem(str(value)))
        self.progress.setValue(index + 1)
        if self.table.currentRow() in (-1, index):
            self.table.selectRow(index)
            # Drawing the report was left to `itemSelectionChanged`, and that
            # signal does not fire when the row is *already* selected — which is
            # exactly the case with one book in the queue. The result was a
            # blank report panel until a second book was added and the user
            # clicked between the two.
            self._show_selected_report()

    def _on_all_finished(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)
        self.progress.setVisible(False)
        failures = sum(1 for r in self._results.values() if r.output_path is None)
        total = len(self._results)
        self.statusBar().showMessage(
            tr("status.finished.failures", count=total, failures=failures)
            if failures
            else tr("status.finished", count=total)
        )

    # ---------------------------------------------------------------- output
    def _show_selected_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            self.report_view.clear()
            return

        colors = {
            Level.FIX: self.palette_colors.fix,
            Level.PRESERVED: self.palette_colors.preserved,
            Level.WARN: self.palette_colors.warn,
            Level.ERROR: self.palette_colors.error,
            Level.INFO: self.palette_colors.info,
        }
        default = QColor(self.palette_colors.text)

        self.report_view.clear()
        self.report_view.setTextColor(default)
        self.report_view.append(f"{tr('report.source')}: {result.report.source}")
        self.report_view.append(
            f"{tr('report.output')}: {result.output_path or tr('report.notwritten')}"
        )
        remark = quip_for(result.report, language())
        if remark:
            self.report_view.setTextColor(QColor(self.palette_colors.text_muted))
            self.report_view.append(f"— {remark}")
        self.report_view.append("")

        width = max(len(tr(key)) for key in LEVEL_KEYS.values())
        for finding in result.report.sorted_findings():
            self.report_view.setTextColor(QColor(colors[finding.level]))
            label = tr(LEVEL_KEYS[finding.level]).rjust(width)
            where = f"  [{finding.location}]" if finding.location else ""
            # The window has been bilingual and the report has not, because the
            # English sentence *was* the identity of a finding. With the
            # catalogue it is not, so the headline follows the interface. The
            # original line stays beneath it only where the translation cannot
            # state the specifics itself, which is what the templates remove.
            headline, _, original = result.report.headline(finding, language()).partition("\n")
            self.report_view.append(f"{label}  {finding.stage}: {headline}{where}")
            if original:
                self.report_view.setTextColor(QColor(self.palette_colors.text_muted))
                self.report_view.append(f"{'':>{width + 2}}{finding.message}")
                self.report_view.setTextColor(QColor(colors[finding.level]))
            detail = result.report.detail_for(finding, language())
            if detail:
                self.report_view.append(f"{'':>{width + 2}}{detail}")
        # BA-2026-003: the balance sheet, after the findings and before the
        # cursor goes back to the top. Only what cannot be undone is listed —
        # the rest is in the saved JSON, and a window that reprints every move
        # is a window nobody scrolls to the end of.
        undoable = result.report.irreversible()
        if result.report.changes:
            self.report_view.setTextColor(QColor(self.palette_colors.text_muted))
            self.report_view.append("")
            self.report_view.append(
                tr(
                    "report.changes",
                    total=len(result.report.changes),
                    irreversible=len(undoable),
                )
            )
            for change in undoable:
                self.report_view.append(
                    f"    {change.action.value}  {change.subject}"
                    + (f"  ({change.before})" if change.before else "")
                )
        self.report_view.setTextColor(default)
        self.report_view.moveCursor(QTextCursor.MoveOperation.Start)

    def _save_report(self) -> None:
        row = self.table.currentRow()
        result = self._results.get(row)
        if result is None:
            QMessageBox.information(self, tr("dialog.noreport.title"), tr("dialog.noreport.body"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport"), "raport.json", "JSON (*.json)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(result.report.to_json(language()))

    def _save_batch_report(self) -> None:
        """Every book in the queue, in one file.

        Saving one report at a time is fine for one book and unusable for
        thirty: the question a batch raises is which of them needs attention,
        and opening thirty files to answer it is slower than not asking.
        """
        if not self._results:
            QMessageBox.information(self, tr("dialog.noreport.title"), tr("dialog.noreport.body"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog.savereport.batch"), "raport-zbiorczy.json", "JSON (*.json)"
        )
        if path:
            reports = [self._results[row].report for row in sorted(self._results)]
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(batch_to_json(reports, language()))
            self.statusBar().showMessage(
                tr("status.batch.saved", count=len(reports))
            )


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Must happen before the first window exists, or the taskbar has already
    # decided which icon to group this process under.
    resources.set_windows_app_id()

    app = QApplication(argv)
    app.setApplicationName("EPUB F.O.R.G.E.")
    # Not setApplicationDisplayName: Qt appends it to every window title, and
    # the result read "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E.".
    app.setStyle("Fusion")

    icon_path = resources.app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    set_language(settings().value("language", "pl"))

    palette = theme.active_palette(app)
    app.setStyleSheet(theme.stylesheet(palette))

    # Paths arrive this way from the installer's "Rebuild with EPUB-Forge"
    # shell verb and from dragging files onto the executable.
    queued = [
        path for path in argv[1:]
        if path.lower().endswith(".epub") and os.path.isfile(path)
    ]

    # Retranslating an imperatively built UI in place means tracking every
    # widget; rebuilding the window is simpler and keeps the queue.
    while True:
        window = MainWindow(palette, initial_files=queued)
        window.show()
        app.exec()
        if not window.restart_requested:
            return 0
        queued = list(window._sources)
