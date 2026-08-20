"""One shape for every question this program cannot answer by itself.

BA-2026-002: the only thing a person could ever be asked about was a broken
fragment, and even that question had no stable identity, no recommendation, no
statement of what it would cost, and no way to be answered once and remembered.
A resolver that raised was caught by a bare `except` and read as "leave it
alone", so a front end that crashed and a person who chose to keep the link were
the same event in the record. Nothing else in the program could ask anything.

That mattered more once there was a second thing worth asking about. A hard
hyphen left inside a word by a bad conversion — `obo-jętna` — cannot be repaired
by rule: some of them are the conversion's damage and some of them are the
author's, and no amount of cleverness separates those two from inside the file.
The project's answer to "cannot decide" is settled and is not "guess": it is to
ask. But asking needs somewhere for the answer to live, or the same two hundred
questions arrive on every rebuild and the feature becomes something people
switch off.

So a question here is a `Question`:

* a **stable id**, derived from the book and the thing being asked about, so the
  same question about the same book is the same question next month;
* a **group**, so "do this to all of them" is a promise about a set rather than
  a hope;
* the **options**, each saying what it will do to the book — not "keep/repoint"
  but the sentence a person needs to choose between them;
* a **recommendation**, which is this program's opinion and is not applied
  without an answer;
* **reversibility and risk**, in the same vocabulary the change ledger uses,
  because a person deciding needs to know which of these they can take back.

And an `Answer` can be written to disk and read back, so a rebuild run twice
asks the second time only what it has not been told.

What this deliberately does not do is answer anything on a timer, a default or a
majority. An unanswered question keeps the book as the publisher wrote it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field, replace
from typing import Protocol

from .report import Risk

#: The kinds of question that exist. A closed vocabulary for the same reason
#: `Action` is closed: "how many decisions of each sort did this book need" is a
#: question about the program, and it cannot be answered against free text.
REFERENCE = "reference"
HYPHEN = "hyphen"
METADATA = "metadata"
#: The appearance check is required and could not be performed here. Unlike the
#: other three this question is not about a place in the book — it is about
#: whether a book nobody was able to check may be written at all, and it exists
#: because the alternative was the program answering it silently.
VERIFICATION = "verification"
#: Punctuation that a conversion turned into an unprintable code — EF-050. Its
#: own kind rather than a `HYPHEN`, because the two are answered by different
#: judgements: a hyphen candidate asks *is this one word or two*, which needs
#: the sentence; this asks *were these quotation marks*, which needs nothing but
#: the count. Keeping them apart also keeps the ledger's per-kind tally
#: meaningful.
ENCODING = "encoding"
#: A declaration written the way an HTML attribute is written — `text-align=
#: "center"` — in a rule no generator signed. No reader has ever applied it,
#: so enabling it (the `=` becomes a `:`) changes how the book looks, and
#: whether the publisher wanted that is not a fact the file can answer.
#: Pillar 4 of the 0.3 plan, the owner's own call: "Ja bym to chyba zrobił
#: na zasadzie zapytania czy włączyć czy eliminować całkowicie."
#: (The kind existed once before, for the typo question D-030 removed;
#: the name returns because the judgement is again about one CSS rule.)
STYLE = "style"
KINDS = (REFERENCE, HYPHEN, METADATA, VERIFICATION, ENCODING, STYLE)

#: Every question has this option and it is always the safe one: change nothing.
#: Named rather than spelled out at each call site, because "the option that
#: does nothing" has to be identifiable by the machinery — it is what an
#: unanswered, failed or declined question falls back to.
KEEP = "keep"


@dataclass(frozen=True)
class Option:
    """One thing that may be done, and what it does to the book."""

    id: str
    label: str
    #: What the reader would see afterwards. Not a restatement of the label:
    #: somebody choosing between two options needs the consequence of each.
    consequence: str
    #: `True` when this option carries a value the person supplies — an anchor
    #: to point at, a word to write.
    needs_value: bool = False


@dataclass(frozen=True)
class Question:
    """Something this program will not decide on somebody's behalf."""

    kind: str
    #: Container path of whatever the question is about.
    where: str
    #: One line, the thing being asked.
    summary: str
    #: What a person needs in order to answer — the surrounding text, the
    #: anchors that do exist, the two spellings in conflict.
    detail: str
    options: tuple[Option, ...]
    #: The option this program would choose. An opinion, never an action.
    recommended: str = KEEP
    #: Whether the recommended option can be undone from the output alone.
    reversible: bool = True
    risk: Risk = Risk.NONE
    #: Questions sharing this answer the same way. "All of them" means this set.
    group: str = ""
    #: Whatever makes this question this question — the word, the reference,
    #: the field. Feeds the stable id and nothing else.
    subject: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind of question: {self.kind!r}")
        if not self.options:
            raise ValueError("a question with no options is not a question")
        ids = [option.id for option in self.options]
        if KEEP not in ids:
            raise ValueError("every question must offer to change nothing")
        if len(set(ids)) != len(ids):
            raise ValueError(f"two options with one id: {ids}")
        if self.recommended not in ids:
            raise ValueError(f"recommending {self.recommended!r}, which is not offered")

    @property
    def id(self) -> str:
        """Stable across runs, and across everything that is not the question.

        Built from what the question *is* — its kind, where it is, what it is
        about — and not from a counter, a position in a list or the order the
        documents happened to be read in. That is the whole requirement for
        answers being worth writing down: an id that moves when a chapter is
        renumbered would replay yesterday's answer onto today's different
        question, which is worse than not remembering at all.
        """
        material = "\x00".join((self.kind, self.where, self.subject, self.summary))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def option(self, option_id: str) -> "Option | None":
        return next((o for o in self.options if o.id == option_id), None)

    def __str__(self) -> str:
        return f"{self.where}: {self.summary}"


@dataclass(frozen=True)
class Answer:
    """What was decided, by whom, and whether it stands for the group."""

    option: str = KEEP
    #: For an option that carries one — the anchor, the spelling.
    value: str = ""
    #: Apply to every remaining question in the same group.
    apply_to_group: bool = False
    #: `person`, `stored` (read back from a previous run) or `unanswered`.
    source: str = "person"

    @property
    def changes_anything(self) -> bool:
        return self.option != KEEP


UNANSWERED = Answer(source="unanswered")


class Asker(Protocol):
    """Something that can put a question to a person.

    May return `None`, meaning the same as leaving it alone. May raise, and
    that is the point of the change here: a front end that fell over is not a
    person who chose to keep the link, and the queue records the difference.
    """

    def ask(self, question: Question) -> "Answer | None":  # pragma: no cover
        ...


def _book_key(source: "str | pathlib.Path") -> str:
    """Which book a stored answer belongs to.

    The digest of the file. A book that has been edited since the answers were
    given is a different book, and replaying onto it would be applying somebody's
    judgement about a page they have not seen.
    """
    sha = hashlib.sha256()
    with open(source, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


@dataclass
class Queue:
    """The questions asked during one rebuild and the answers they got."""

    asker: "Asker | None" = None
    #: Answers read from a previous run, by question id.
    stored: dict = field(default_factory=dict)
    #: Standing answers, by group.
    standing: dict = field(default_factory=dict)
    #: Everything asked, in order, with what came back.
    given: list = field(default_factory=list)
    #: Front ends that failed. Recorded rather than swallowed: BA-2026-002's
    #: sharpest point was that a resolver raising and a person answering "keep"
    #: were indistinguishable in the record, so a broken dialog looked like a
    #: hundred considered decisions.
    failures: list = field(default_factory=list)

    def ask(self, question: Question) -> Answer:
        """Put one question, or don't, and return what stands."""
        remembered = self.stored.get(question.id)
        if remembered is not None:
            answer = replace(remembered, source="stored")
            self.given.append((question, answer))
            return answer

        if question.group and question.group in self.standing:
            answer = self.standing[question.group]
            self.given.append((question, answer))
            return answer

        if self.asker is None:
            self.given.append((question, UNANSWERED))
            return UNANSWERED

        try:
            answer = self.asker.ask(question)
        except Exception as exc:  # noqa: BLE001 — a front end that fell over
            self.failures.append(f"{question}: {type(exc).__name__}: {exc}")
            self.given.append((question, UNANSWERED))
            return UNANSWERED

        if answer is None:
            answer = UNANSWERED
        if answer.option not in {option.id for option in question.options}:
            self.failures.append(
                f"{question}: answered {answer.option!r}, which was not offered"
            )
            answer = UNANSWERED
        elif (option := question.option(answer.option)) and option.needs_value and not answer.value:
            self.failures.append(f"{question}: {answer.option!r} needs a value and got none")
            answer = UNANSWERED

        if answer.apply_to_group and question.group:
            # A standing answer only carries where it means the same thing
            # everywhere. "Point this one at `fn-3`" does not; "leave them all
            # alone" does.
            if not (option := question.option(answer.option)) or not option.needs_value:
                self.standing[question.group] = answer
        self.given.append((question, answer))
        return answer

    # ------------------------------------------------------------- persistence
    def to_dict(self, *, book: str = "") -> dict:
        return {
            "book": book,
            "answers": {
                question.id: {
                    "option": answer.option,
                    "value": answer.value,
                    "kind": question.kind,
                    "where": question.where,
                    "summary": question.summary,
                }
                for question, answer in self.given
                if answer.source == "person" and answer.changes_anything
            },
        }

    def save(self, path: "str | pathlib.Path", *, source: "str | pathlib.Path") -> pathlib.Path:
        """Write the answers a person gave, beside the book they are about.

        Only what a person decided *and* that changes something. An unanswered
        question is not a decision to record — writing it down would turn "I did
        not get round to it" into "leave this alone forever".
        """
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict(book=_book_key(source))
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    @classmethod
    def load(
        cls,
        path: "str | pathlib.Path",
        *,
        source: "str | pathlib.Path",
        asker: "Asker | None" = None,
    ) -> "Queue":
        """Read answers back, if they are about this exact book.

        A digest mismatch loads nothing and says so through `failures`. Silently
        replaying answers onto an edited book is the failure this guards: the
        person answered about a page that is no longer there.
        """
        queue = cls(asker=asker)
        target = pathlib.Path(path)
        if not target.is_file():
            return queue
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            queue.failures.append(f"{target}: {type(exc).__name__}: {exc}")
            return queue
        if payload.get("book") and payload["book"] != _book_key(source):
            queue.failures.append(
                f"{target}: answers are about a different version of this book, "
                f"so none of them were used"
            )
            return queue
        for question_id, entry in (payload.get("answers") or {}).items():
            queue.stored[question_id] = Answer(
                option=entry.get("option", KEEP),
                value=entry.get("value", ""),
                source="stored",
            )
        return queue

    def forget(self, question_id: str) -> bool:
        """Undo one stored answer. `True` when there was one to undo."""
        return self.stored.pop(question_id, None) is not None

    def forget_all(self) -> int:
        count = len(self.stored)
        self.stored.clear()
        self.standing.clear()
        return count

    # ------------------------------------------------------------- reporting
    @property
    def answered(self) -> int:
        return sum(1 for _, answer in self.given if answer.source != "unanswered")

    @property
    def changed(self) -> int:
        return sum(1 for _, answer in self.given if answer.changes_anything)

    def summary(self) -> str:
        if not self.given:
            return "nie było o co pytać"
        parts = [
            f"{len(self.given)} do decyzji",
            f"{self.answered} z odpowiedzią",
            f"{self.changed} zmieniło książkę",
        ]
        if self.failures:
            parts.append(f"{len(self.failures)} pytań przepadło")
        return ", ".join(parts)


def answers_path(source: "str | pathlib.Path") -> pathlib.Path:
    """Where this book's answers live: beside it, named after it.

    Beside the book rather than in a central store, because the answers are
    about *that* book and a person moving their library should not leave their
    judgements behind on a machine.
    """
    book = pathlib.Path(source)
    return book.with_suffix(book.suffix + ".decyzje.json")


__all__ = [
    "Answer",
    "Asker",
    "ENCODING",
    "HYPHEN",
    "KEEP",
    "KINDS",
    "METADATA",
    "Option",
    "Queue",
    "Question",
    "REFERENCE",
    "STYLE",
    "UNANSWERED",
    "answers_path",
]
