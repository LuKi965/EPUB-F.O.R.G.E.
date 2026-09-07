"""The corpus: a library keeping the tool honest, without anybody handing it over.

Expert work, and the page says so. What it does is compare every book against
what this program did to it last time, so a release that changes an answer has
to say which answer and why — and it can build the two families of books that
cannot be bought.
"""

from __future__ import annotations

import os
import pathlib

from PySide6.QtWidgets import QFileDialog, QInputDialog

from ....strings import tr
from ....toolwork import (
    assign_fixture,
    build_edge_cases,
    corpus_check,
    fixture_roles,
    fixtures_survey,
    streak,
)
from ...tokens import Tokens
from ...widgets import label
from .base import ToolPage


class CorpusToolPage(ToolPage):
    def __init__(self, tokens: Tokens) -> None:
        super().__init__(
            tokens, key="shell.tools.corpus", glyph="tools",
            card_key="corpus.card", intro_key="corpus.intro", empty_key="corpus.empty",
        )
        self._signatures_used: pathlib.Path | None = None
        self.books = self.add_source("corpus.books")
        self.signatures = self.add_source(
            "corpus.signatures", placeholder=tr("corpus.signatures.placeholder")
        )
        note = label(tr("corpus.what"), "cardSubtitle")
        self.body.addWidget(note)

        self.add_action("corpus.check", self.check, primary=True, glyph="check",
                        tip_key="corpus.check.tip")
        self.add_action("corpus.record", self.record, glyph="save", tip_key="corpus.record.tip")
        # The one family nobody can go and buy. It used to be a command-line
        # script importing from the test suite, which put it out of reach of
        # the only person able to fill it.
        self.add_action("corpus.edges", self.build_edges, glyph="plus", tip_key="corpus.edges.tip")
        # The other family nobody can buy, and the one the audit stalled on: it
        # named two purchased books "mandatory" and never said which.
        self.add_action("corpus.fixtures", self.show_fixtures, glyph="book",
                        tip_key="corpus.fixtures.tip")
        self.add_action("corpus.fixtures.assign", self.assign, glyph="folder",
                        tip_key="corpus.fixtures.assign.tip")
        self.end_actions()
        self.finish_building()

    # -- the five things it can do ------------------------------------------
    def check(self) -> None:
        self._compare(record=False)

    def record(self) -> None:
        self._compare(record=True)

    def _compare(self, *, record: bool) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            self.needs_a_source()
            return
        signatures = self.signatures.text().strip()
        self.run_work(
            lambda tick: corpus_check(books, signatures, record=record, tick=tick)
        )

    def build_edges(self) -> None:
        books = self.books.text().strip()
        if not books or not os.path.isdir(books):
            self.needs_a_source()
            return
        self.run_work(lambda tick: build_edge_cases(books, tick=tick))

    def show_fixtures(self) -> None:
        books = self.books.text().strip()
        self.run_work(lambda tick: fixtures_survey(books, tick=tick))

    def assign(self) -> None:
        chosen, picked = QFileDialog.getOpenFileName(
            self, tr("corpus.fixtures.assign"), self.books.text().strip(), "EPUB (*.epub)"
        )
        if not picked or not chosen:
            return
        role, confirmed = QInputDialog.getItem(
            self, tr("corpus.fixtures.assign"), tr("corpus.fixtures.role"),
            fixture_roles(), 0, False,
        )
        if not confirmed:
            return
        self.show_answer(assign_fixture(role, chosen))

    def show_answer(self, answer) -> None:
        if answer.used:
            self._signatures_used = pathlib.Path(answer.used)
        super().show_answer(answer)

    def streak(self) -> str:
        """How many releases in a row came out clean, for the last comparison."""
        return streak(self._signatures_used)
