"""The question dialog shows the picture a question is about.

Record 039 left it open: a person asked to describe a picture was shown its
file name, pixel size and weight, and not the picture. The owner's answer
(2026-09-02) was to build the preview. The question carries the book's own
bytes; the dialog draws them scaled to fit, and shows the question without
them when they cannot be drawn.
"""

from __future__ import annotations

import os

import pytest

# The widgets module, not the package: a host with PySide6 installed and no
# EGL library imports the package fine and fails on the widgets, which is a
# collection error rather than a skip. Seen on a fresh container 2026-09-02.
pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from epubforge.decisions import IMAGE, KEEP, Option, Preview, Question  # noqa: E402
from epubforge.gui.ask import PREVIEW_BOX, DecideDialog  # noqa: E402

from tests.factory import png_bytes  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def question(preview=None) -> Question:
    return Question(
        kind=IMAGE,
        where="c0.xhtml",
        summary="Obraz bez opisu",
        detail="Dowody.",
        options=(
            Option(KEEP, "Zostaw", "Nic się nie zmienia"),
            Option("describe", "Wpisz opis", "Trafia do alt", needs_value=True),
        ),
        preview=preview,
    )


class TestThePictureIsShown:
    def test_a_small_picture_is_drawn_at_its_own_size(self, app):
        dialog = DecideDialog(question(Preview("image/png", png_bytes((40, 12)))))
        assert dialog.preview is not None
        pixmap = dialog.preview.pixmap()
        assert not pixmap.isNull()
        assert (pixmap.width(), pixmap.height()) == (40, 12)

    def test_a_big_picture_is_scaled_to_fit_and_keeps_its_shape(self, app):
        dialog = DecideDialog(question(Preview("image/png", png_bytes((1200, 600)))))
        pixmap = dialog.preview.pixmap()
        assert pixmap.width() == PREVIEW_BOX
        assert pixmap.height() == PREVIEW_BOX // 2

    def test_a_question_without_a_picture_has_no_preview(self, app):
        dialog = DecideDialog(question())
        assert dialog.preview is None

    def test_bytes_that_cannot_be_drawn_leave_the_question_standing(self, app):
        """A format Qt has no plugin for, or a broken file: the question is
        shown without the picture rather than not shown."""
        dialog = DecideDialog(question(Preview("image/x-unknown", b"not a picture at all")))
        assert dialog.preview is None
        assert dialog.answer().option == KEEP

    def test_the_answer_is_unaffected_by_the_preview(self, app):
        dialog = DecideDialog(question(Preview("image/png", png_bytes((40, 12)))))
        dialog.buttons_for["describe"].setChecked(True)
        dialog.value_edit.setText("Róża nad tytułem")
        answer = dialog.answer()
        assert answer.option == "describe"
        assert answer.value == "Róża nad tytułem"


class TestThePreviewNeverReachesTheRecord:
    def test_the_queue_writes_option_and_value_only(self, tmp_path):
        """The answers file beside a book is a record of decisions, not a
        copy of the book's pictures."""
        from epubforge.decisions import Answer, Queue

        class Chooser:
            def ask(self, q):
                return Answer(option="describe", value="Mapa")

        queue = Queue(asker=Chooser())
        queue.ask(question(Preview("image/png", png_bytes((40, 12)))))
        payload = queue.to_dict(book="x")
        text = str(payload)
        assert "Mapa" in text
        assert "PNG" not in text and "preview" not in text
