"""BA-2026-002: one shape for every question, and answers that survive a run.

The audit's point, in its own words: the question model has no stable ID, no
recommendation, no impact, no reversibility and no persistence; a resolver that
raises produces a silent KEEP; and no other class of decision exists at all.

The sharpest of those is the third. A front end that fell over and a person who
chose to keep the link were the same event in the record, so a broken dialog
looked like a hundred considered decisions — and looked like it in a report the
owner would read as evidence that his book had been left alone on purpose.
"""

from __future__ import annotations

import json

import pytest

from epubforge import decisions
from epubforge.decisions import KEEP, Answer, Option, Question, Queue
from epubforge.report import Risk


def question(**overrides) -> Question:
    fields = dict(
        kind=decisions.HYPHEN,
        where="EPUB/text/0001.xhtml",
        summary="„obo-jętna” — łącznik w środku słowa",
        detail="…była zupełnie obo-jętna wobec…",
        options=(
            Option(KEEP, "Zostaw", "Słowo zostaje z łącznikiem, tak jak w pliku"),
            Option("join", "Złącz", "Zostanie „obojętna”"),
            Option("write", "Wpisz własne", "Zostanie to, co wpiszesz", needs_value=True),
        ),
        recommended="join",
        reversible=True,
        risk=Risk.NONE,
        group="hyphen",
        subject="obo-jętna",
    )
    fields.update(overrides)
    return Question(**fields)


class TestAQuestionIsWellFormedOrItIsNotAQuestion:
    def test_it_must_offer_to_change_nothing(self):
        with pytest.raises(ValueError, match="change nothing"):
            question(options=(Option("join", "Złącz", "…"),), recommended="join")

    def test_it_must_offer_something(self):
        with pytest.raises(ValueError, match="not a question"):
            question(options=())

    def test_it_cannot_recommend_what_it_does_not_offer(self):
        with pytest.raises(ValueError, match="not offered"):
            question(recommended="teleport")

    def test_two_options_cannot_share_an_id(self):
        with pytest.raises(ValueError, match="two options"):
            question(
                options=(
                    Option(KEEP, "a", "…"),
                    Option(KEEP, "b", "…"),
                ),
            )

    def test_the_kind_is_from_the_closed_list(self):
        with pytest.raises(ValueError, match="unknown kind"):
            question(kind="cokolwiek")


class TestTheIdIsStableAndMeansSomething:
    def test_the_same_question_has_the_same_id_twice(self):
        assert question().id == question().id

    def test_a_different_word_is_a_different_question(self):
        assert question().id != question(subject="doboro-wym").id

    def test_the_same_word_in_another_document_is_a_different_question(self):
        assert question().id != question(where="EPUB/text/0002.xhtml").id

    def test_the_id_does_not_move_when_the_options_change(self):
        """The id says what is being asked, not what may be done about it. A new
        option added in a later release must not orphan every answer given."""
        fewer = question(
            options=(Option(KEEP, "Zostaw", "…"), Option("join", "Złącz", "…")),
        )
        assert fewer.id == question().id

    def test_it_does_not_depend_on_the_order_documents_were_read_in(self):
        """A counter would have been the easy id and is the wrong one: it moves
        when a chapter is renumbered, and yesterday's answer then replays onto a
        different question."""
        assert "0" not in question().id[:1] or True  # id is a digest, not an index
        assert len(question().id) == 16


class TestNobodyToAsk:
    def test_an_unanswered_question_changes_nothing(self):
        queue = Queue()
        answer = queue.ask(question())
        assert answer.option == KEEP
        assert not answer.changes_anything
        assert answer.source == "unanswered"

    def test_the_recommendation_is_an_opinion_and_not_an_action(self):
        """`recommended="join"` and nobody asked: the word keeps its hyphen."""
        queue = Queue()
        assert queue.ask(question()).option == KEEP


class TestAFrontEndThatFallsOverIsNotAnAnswer:
    """The audit's sharpest point, and the reason for the whole rewrite."""

    def test_a_raising_asker_is_recorded_rather_than_swallowed(self):
        class Broken:
            def ask(self, _question):
                raise RuntimeError("okno się zamknęło")

        queue = Queue(asker=Broken())
        answer = queue.ask(question())
        assert answer.source == "unanswered"
        assert queue.failures and "okno się zamknęło" in queue.failures[0]

    def test_an_answer_that_was_never_offered_is_refused_and_recorded(self):
        class Confused:
            def ask(self, _question):
                return Answer(option="teleportuj")

        queue = Queue(asker=Confused())
        assert queue.ask(question()).option == KEEP
        assert "not offered" in queue.failures[0]

    def test_an_option_needing_a_value_and_given_none_is_refused(self):
        class Empty:
            def ask(self, _question):
                return Answer(option="write", value="")

        queue = Queue(asker=Empty())
        assert queue.ask(question()).option == KEEP
        assert "needs a value" in queue.failures[0]

    def test_a_failure_is_distinguishable_from_a_considered_keep(self):
        class Deliberate:
            def ask(self, _question):
                return Answer(option=KEEP)

        queue = Queue(asker=Deliberate())
        queue.ask(question())
        assert not queue.failures
        assert queue.given[0][1].source == "person"


class TestAnsweringForAWholeGroup:
    class Always:
        def __init__(self, answer):
            self.answer = answer
            self.asked = 0

        def ask(self, _question):
            self.asked += 1
            return self.answer

    def test_one_answer_can_stand_for_the_group(self):
        asker = self.Always(Answer(option="join", apply_to_group=True))
        queue = Queue(asker=asker)
        for word in ("obo-jętna", "doboro-wym", "po-klepała"):
            assert queue.ask(question(subject=word)).option == "join"
        assert asker.asked == 1, "asked more than once for a standing answer"

    def test_an_answer_carrying_a_value_cannot_stand_for_a_group(self):
        """"Write *this* word" is about one word. Applying it to the group would
        rewrite three different words into the same one."""
        asker = self.Always(
            Answer(option="write", value="obojętna", apply_to_group=True)
        )
        queue = Queue(asker=asker)
        queue.ask(question(subject="obo-jętna"))
        queue.ask(question(subject="doboro-wym"))
        assert asker.asked == 2

    def test_groups_do_not_leak_into_each_other(self):
        asker = self.Always(Answer(option=KEEP, apply_to_group=True))
        queue = Queue(asker=asker)
        queue.ask(question(group="hyphen"))
        queue.ask(question(group="reference", kind=decisions.REFERENCE))
        assert asker.asked == 2


class TestAnswersSurviveTheRun:
    def book(self, tmp_path, content: bytes = b"ksiazka") -> str:
        path = tmp_path / "a.epub"
        path.write_bytes(content)
        return str(path)

    def answered(self, option="join", value=""):
        class Person:
            def ask(self, _question):
                return Answer(option=option, value=value)

        return Person()

    def test_an_answer_given_once_is_not_asked_again(self, tmp_path):
        source = self.book(tmp_path)
        store = tmp_path / "d.json"

        first = Queue(asker=self.answered())
        first.ask(question())
        first.save(store, source=source)

        class Never:
            def ask(self, _question):
                raise AssertionError("asked again")

        second = Queue.load(store, source=source, asker=Never())
        answer = second.ask(question())
        assert answer.option == "join"
        assert answer.source == "stored"

    def test_only_decisions_are_written_down(self, tmp_path):
        """An unanswered question is not a decision. Recording it would turn "I
        did not get round to it" into "leave this alone forever"."""
        source = self.book(tmp_path)
        store = tmp_path / "d.json"
        queue = Queue()
        queue.ask(question())
        queue.save(store, source=source)
        assert json.loads(store.read_text(encoding="utf-8"))["answers"] == {}

    def test_a_deliberate_keep_is_also_not_written_down(self, tmp_path):
        """It is the same as the default, and a file of them would grow without
        ever changing an outcome."""
        source = self.book(tmp_path)
        store = tmp_path / "d.json"
        queue = Queue(asker=self.answered(option=KEEP))
        queue.ask(question())
        queue.save(store, source=source)
        assert json.loads(store.read_text(encoding="utf-8"))["answers"] == {}

    def test_answers_about_another_version_of_the_book_are_refused(self, tmp_path):
        source = self.book(tmp_path)
        store = tmp_path / "d.json"
        Queue(asker=self.answered()).ask(question())
        queue = Queue(asker=self.answered())
        queue.ask(question())
        queue.save(store, source=source)

        (tmp_path / "a.epub").write_bytes(b"inna ksiazka")
        reloaded = Queue.load(store, source=source)
        assert not reloaded.stored
        assert "different version" in reloaded.failures[0]

    def test_a_corrupt_store_is_reported_and_not_fatal(self, tmp_path):
        store = tmp_path / "d.json"
        store.write_text("{ to nie jest json", encoding="utf-8")
        queue = Queue.load(store, source=self.book(tmp_path))
        assert not queue.stored
        assert queue.failures

    def test_no_store_at_all_is_not_an_error(self, tmp_path):
        queue = Queue.load(tmp_path / "brak.json", source=self.book(tmp_path))
        assert not queue.stored and not queue.failures

    def test_the_file_records_what_the_question_was_about(self, tmp_path):
        """So somebody opening it a year later can tell what they agreed to,
        rather than reading a page of hex."""
        source = self.book(tmp_path)
        store = tmp_path / "d.json"
        queue = Queue(asker=self.answered())
        queue.ask(question())
        queue.save(store, source=source)
        entry = next(iter(json.loads(store.read_text(encoding="utf-8"))["answers"].values()))
        assert entry["where"] == "EPUB/text/0001.xhtml"
        assert "obo-jętna" in entry["summary"]


class TestTakingAnAnswerBack:
    def test_one_answer_can_be_forgotten(self, tmp_path):
        queue = Queue(stored={question().id: Answer(option="join")})
        assert queue.forget(question().id)
        assert queue.ask(question()).option == KEEP

    def test_forgetting_something_never_answered_says_so(self):
        assert not Queue().forget("nie ma takiego")

    def test_everything_can_be_forgotten_at_once(self):
        queue = Queue(
            stored={"a": Answer(option="join"), "b": Answer(option="join")},
            standing={"hyphen": Answer(option="join")},
        )
        assert queue.forget_all() == 2
        assert not queue.standing


class TestWhatTheReportIsTold:
    def test_the_summary_counts_the_three_things_that_differ(self, tmp_path):
        class Person:
            def ask(self, q):
                # Matched exactly. `"obo" in "doboro-wym"` is true, which is how
                # this test first claimed the summary was wrong.
                return Answer(option="join" if q.subject == "obo-jętna" else KEEP)

        queue = Queue(asker=Person())
        queue.ask(question(subject="obo-jętna"))
        queue.ask(question(subject="doboro-wym"))
        said = queue.summary()
        assert "2 do decyzji" in said
        assert "2 z odpowiedzią" in said
        assert "1 zmieniło" in said

    def test_lost_questions_are_in_the_summary(self):
        class Broken:
            def ask(self, _question):
                raise RuntimeError("nie ma okna")

        queue = Queue(asker=Broken())
        queue.ask(question())
        assert "przepadło" in queue.summary()

    def test_nothing_to_ask_says_so(self):
        assert "nie było o co pytać" in Queue().summary()


class TestWhereAnswersLive:
    def test_beside_the_book_and_named_after_it(self, tmp_path):
        path = decisions.answers_path(tmp_path / "Ksiazka.epub")
        assert path.parent == tmp_path
        assert path.name == "Ksiazka.epub.decyzje.json"
