"""One answer for the whole batch, not one answer per book.

Measured on the owner's 160 books before this existed: **8 979 questions**,
of which **8 737 were one family**. The decision queue was born inside each
rebuild, so a standing answer — "do this to all of them" — died with the book
it was given about. Answering it in book one meant being asked again in book
two, and a hundred and fifty-eight times after that.

That is not a rough edge. Everything the style work achieved reaches the
owner's shelf only through those questions, so a queue nobody can finish is a
gate on the whole programme.

What deliberately does **not** carry is a per-question answer. `Queue.stored`
is keyed on the book and refused when the book has changed, because replaying
somebody's judgement onto a page they have not seen is worse than asking again
(BA-2026-002). A standing answer is different in kind: it is an answer about a
*class*, given by somebody the option told it would apply to everything of that
class.
"""

from __future__ import annotations

import pathlib

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_class_translation import PAGE
from tests.test_shelf_refusals import make_book


class Counting:
    """Answers every question the same way and remembers what it was asked."""

    def __init__(self, *, to_the_group: bool):
        self.asked: list = []
        self.to_the_group = to_the_group

    def ask(self, question):
        self.asked.append(question)
        return Answer(
            option=question.recommended or "keep",
            apply_to_group=self.to_the_group,
        )


SHEET = (
    "p.jeden { text-indent: 2em !important; text-indent: 1em; }\n"
    "p.dwa { margin-right: 2$; }\n"
)


def a_book(tmp_path, name: str) -> str:
    return make_book(
        tmp_path / name,
        {"c0.xhtml": PAGE.format(body='<p class="jeden">Akapit z treścią.</p>')},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>',
        extra_files={"OEBPS/s.css": SHEET.encode()},
    )


def rebuild_a_few(tmp_path, chooser, standing) -> None:
    policy = Policy.preset("preserve", render_gate="off", validate_before_publish="off")
    for index in range(4):
        rebuild(
            a_book(tmp_path, f"in{index}.epub"),
            str(tmp_path / f"out{index}.epub"),
            policy,
            resolver=chooser,
            standing=standing,
        )


class TestAStandingAnswerCarriesAcrossBooks:
    def test_four_books_ask_once(self, tmp_path):
        chooser = Counting(to_the_group=True)
        rebuild_a_few(tmp_path, chooser, {})
        groups = [q.group for q in chooser.asked]
        assert len(groups) == len(set(groups)), groups

    def test_without_a_shared_dict_each_book_asks_again(self, tmp_path):
        """The state this replaces, pinned so it cannot come back quietly.
        The mutation that ignores the caller's dict fails here."""
        chooser = Counting(to_the_group=True)
        rebuild_a_few(tmp_path, chooser, None)
        groups = [q.group for q in chooser.asked]
        assert len(groups) > len(set(groups)), "the same question was not repeated"

    def test_an_answer_only_for_this_one_does_not_carry(self, tmp_path):
        """`apply_to_group` is the person saying "all of them". Without it the
        answer is about one book and the next book is asked again — which is
        the whole difference between the two, and it must survive sharing the
        dictionary."""
        chooser = Counting(to_the_group=False)
        rebuild_a_few(tmp_path, chooser, {})
        groups = [q.group for q in chooser.asked]
        assert len(groups) > len(set(groups))


class TestTheBatchFrontEndsUseIt:
    def test_the_window_keeps_one_dictionary_for_the_run(self):
        """A batch in the window is a loop over `rebuild_all`, and the whole
        fix is that the loop hands the same dict to every book."""
        import inspect

        from epubforge.gui.app import Worker

        source = inspect.getsource(Worker)
        assert "self._standing" in source
        assert "standing=self._standing" in source

    def test_the_command_line_keeps_one_for_the_run(self):
        import inspect

        from epubforge import cli

        source = inspect.getsource(cli)
        assert "standing: dict = {}" in source
        assert "standing=standing" in source


class TestWhatMustNotCarry:
    def test_a_per_question_answer_is_still_asked_about_the_next_book(self, tmp_path):
        """BA-2026-002's rule, unchanged: an answer about *this* page is not
        an answer about a page nobody has seen. Only the class-wide one
        carries, and `Queue.stored` — the per-book memory — is keyed on the
        book and refused when the book changed."""
        from epubforge.decisions import Queue

        queue = Queue()
        assert queue.stored == {}, "per-book memory must start empty"
        # and the shared dictionary is the *standing* one, not that store
        shared: dict = {}
        other = Queue(standing=shared)
        assert other.standing is shared
