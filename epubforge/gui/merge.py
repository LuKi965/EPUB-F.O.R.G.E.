"""One good book out of two damaged in different places, with a person deciding.

The rebuild refuses a source it could not read in full and there is no setting
that makes it stop refusing. That is right and it is not help, so this is the
half that helps: two copies of one book, each damaged somewhere the other is
not, merged entry by entry into one that is whole.

**Everything is shown before anything is written.** The plan is computed first
and displayed in full — which entry comes from which copy, what neither copy
has, where two intact copies disagree — and the button that writes is disabled
until there is a plan worth writing. That is the owner's standing rule in the
place it matters most: this operation exists because a file was damaged, and a
repair that surprises somebody is not a repair.

Nothing here reconstructs anything. Every entry is copied whole, byte for byte,
from an archive that gave it up cleanly with its own CRC checked. Where two
copies both read an entry cleanly and disagree about its contents, the merge
refuses rather than picking one, because two different intact answers means
these are two different books — or one that somebody edited — and averaging them
produces a book neither copy was.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .. import repair
from . import theme
from .strings import tr


class MergeDialog(QDialog):
    def __init__(self, parent=None, palette: theme.Palette | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("merge.title"))
        self.setMinimumSize(680, 520)
        self.colors = palette or theme.LIGHT
        self._plan: repair.MergePlan | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        intro = QLabel(tr("merge.intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {self.colors.text_muted};")
        layout.addWidget(intro)

        self.copies = QListWidget()
        layout.addWidget(self.copies, stretch=1)

        buttons = QHBoxLayout()
        add = QPushButton(tr("merge.add"))
        add.clicked.connect(self._add_copies)
        buttons.addWidget(add)
        remove = QPushButton(tr("merge.remove"))
        remove.clicked.connect(self._remove_selected)
        buttons.addWidget(remove)
        self.examine = QPushButton(tr("merge.examine"))
        self.examine.setObjectName("primary")
        self.examine.clicked.connect(self._examine)
        buttons.addWidget(self.examine)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        destination = QHBoxLayout()
        destination.addWidget(QLabel(tr("merge.output")))
        self.output_path = QLineEdit()
        destination.addWidget(self.output_path, stretch=1)
        pick = QPushButton(tr("common.browse"))
        pick.clicked.connect(self._pick_output)
        destination.addWidget(pick)
        layout.addLayout(destination)

        self.plan_view = QTextEdit()
        self.plan_view.setReadOnly(True)
        self.plan_view.setPlainText(tr("merge.empty"))
        layout.addWidget(self.plan_view, stretch=2)

        self.box = QDialogButtonBox(QDialogButtonBox.Close)
        self.write_button = self.box.addButton(
            tr("merge.write"), QDialogButtonBox.AcceptRole
        )
        # Nothing is writable until a plan has been computed *and* shown. The
        # dialog cannot be used to merge blind, which is the entire point of it
        # being a dialog rather than a menu item that does the thing.
        self.write_button.setEnabled(False)
        self.write_button.clicked.connect(self._write)
        self.box.rejected.connect(self.reject)
        layout.addWidget(self.box)

    # ----------------------------------------------------------------- input
    def _add_copies(self) -> None:
        chosen, _ = QFileDialog.getOpenFileNames(
            self, tr("merge.add"), "", "EPUB (*.epub)"
        )
        existing = self._paths()
        for path in chosen:
            if path not in existing:
                self.copies.addItem(path)
        self._invalidate()

    def _remove_selected(self) -> None:
        for item in self.copies.selectedItems():
            self.copies.takeItem(self.copies.row(item))
        self._invalidate()

    def _pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("merge.output"), self.output_path.text(), "EPUB (*.epub)"
        )
        if path:
            self.output_path.setText(path)

    def _paths(self) -> list[str]:
        return [self.copies.item(row).text() for row in range(self.copies.count())]

    def _invalidate(self) -> None:
        """A plan describes the files it was computed from and nothing else."""
        self._plan = None
        self.write_button.setEnabled(False)
        self.plan_view.setPlainText(tr("merge.empty"))

    # ------------------------------------------------------------------ work
    def _examine(self) -> None:
        paths = self._paths()
        if len(paths) < 2:
            self.plan_view.setPlainText(tr("merge.needs.two"))
            return

        lines: list[str] = []
        for path in paths:
            lines.append(f"  {repair.inspect(path).summary()}")
        lines.append("")

        plan = repair.plan_merge(paths)
        if plan.refused:
            lines.append(tr("merge.refused", reason=plan.refused))
            self.plan_view.setPlainText("\n".join(lines))
            return

        first = os.path.basename(plan.first)
        taken = {
            name: source for name, source in plan.take.items() if source != plan.first
        }
        lines.append(tr("merge.plan.header", count=len(plan.take), first=first))
        for name, source in sorted(taken.items()):
            lines.append(f"    {name}  ←  {os.path.basename(source)}")
        if not taken:
            lines.append(f"    {tr('merge.plan.nothing')}")
        for name in plan.still_missing:
            lines.append(f"    {name}  —  {tr('merge.plan.missing')}")
        for name in plan.conflicts:
            lines.append(f"    {name}  —  {tr('merge.plan.conflict')}")

        lines.append("")
        lines.append(
            tr("merge.plan.ready", count=plan.repairs)
            if plan.usable
            else tr("merge.plan.unusable")
        )
        self.plan_view.setPlainText("\n".join(lines))
        self._plan = plan
        self.write_button.setEnabled(plan.usable and bool(self.output_path.text().strip()))
        if plan.usable and not self.output_path.text().strip():
            self.plan_view.append("\n" + tr("merge.plan.needs.output"))

    def _write(self) -> None:
        if self._plan is None or not self._plan.usable:
            return
        destination = self.output_path.text().strip()
        if not destination:
            self.plan_view.append("\n" + tr("merge.plan.needs.output"))
            return
        result = repair.merge(self._paths(), destination, self._plan)
        if not result.output_path:
            self.plan_view.append(
                "\n" + tr("merge.refused", reason=self._plan.refused or "—")
            )
            return
        # Checked, not assumed. The whole operation is about a file somebody
        # cannot trust, so the last thing it does is read the result back.
        health = repair.inspect(result.output_path)
        self.plan_view.append(
            "\n"
            + tr("merge.written", path=result.output_path, count=result.written)
            + "\n"
            + f"  {health.summary()}"
        )
        self.write_button.setEnabled(False)


__all__ = ["MergeDialog"]
