"""What crosses the boundary: plain data, copyable, with no Qt and no engine.

Two rules hold this file together.

*Widgets never see a domain object.* `Report`, `Policy` and `Result` stay on
the other side of `backend.ForgeUiBackend`; what a page renders is one of the
dataclasses below. That is what lets the flow be tested without a pipeline and
the pipeline be changed without touching a page.

*Everything here is safe to hand to another thread.* Work runs in a `QThread`
and these objects come back across that line, so they hold strings, numbers
and paths — never a live report, never a lambda, never a widget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Stage(Enum):
    """Where the rebuild flow stands. The order is the stepper's order."""

    FILES = 0
    ANALYSIS = 1
    PLAN = 2
    RUNNING = 3
    RESULTS = 4

    @property
    def step(self) -> int:
        """Which of the four steps the stepper shows — running is still the plan
        being carried out, so it lights the last one."""
        return 3 if self is Stage.RESULTS else min(self.value, 2)


class Preset(str, Enum):
    """The three understandable choices. The values are the engine's mode names,
    so nothing has to translate them twice."""

    PRESERVE = "preserve"
    STRICT = "strict"
    CONTAINER = "minimal"


class BookStatus(str, Enum):
    QUEUED = "queued"
    ANALYSING = "analysing"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    #: Written, and something in it is worth a person's eye.
    ATTENTION = "attention"
    #: A gate refused to publish. Not a crash — a decision.
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def wrote_a_file(self) -> bool:
        return self in (BookStatus.DONE, BookStatus.ATTENTION)


#: Status → (icon glyph, token role). Colour is never alone: the badge carries
#: the glyph and the word as well, which is the accessibility rule this table
#: exists to make impossible to forget.
STATUS_LOOK = {
    BookStatus.QUEUED: ("queued", "muted"),
    BookStatus.ANALYSING: ("running", "accent"),
    BookStatus.READY: ("check", "success"),
    BookStatus.RUNNING: ("running", "accent"),
    BookStatus.DONE: ("check", "success"),
    BookStatus.ATTENTION: ("warning", "warning"),
    BookStatus.BLOCKED: ("error", "danger"),
    BookStatus.FAILED: ("error", "danger"),
    BookStatus.CANCELLED: ("close", "muted"),
}


@dataclass
class ChangeCategory:
    """One plain-language group of what a rebuild did to a book."""

    icon: str
    title: str
    lines: tuple[str, ...] = ()


@dataclass
class BookItem:
    """One book, from the moment it is dropped to the moment it is written."""

    source: Path
    title: str
    author: str = ""
    kind: str = "EPUB"
    size: int = 0
    status: BookStatus = BookStatus.QUEUED
    #: One sentence about what analysis found, in the person's language.
    summary: str = ""
    #: Counts from the report: repaired, deliberately kept, worth a look.
    fixed: int = 0
    kept: int = 0
    issues: int = 0
    output: Path | None = None
    #: The technical report, rendered once by the adapter and shown on demand.
    report_text: str = ""
    #: What the rebuild changed, grouped for a person rather than by stage.
    categories: tuple[ChangeCategory, ...] = ()
    #: Why a book failed or was refused, when it was.
    error: str = ""
    #: True while the person keeps it in the batch. Unticking a row removes it
    #: from the run without removing it from the list.
    chosen: bool = True

    @property
    def rebuildable(self) -> bool:
        """Whether this book can be part of a run at all.

        A file the analysis could not read will not become readable by being
        ticked, and a book a gate refused is a decision rather than a mishap.
        Both used to sit in the plan with a tick beside them, be sent to the
        engine, and come back failed a second time.
        """
        return self.status not in (BookStatus.FAILED, BookStatus.BLOCKED)

    @property
    def size_text(self) -> str:
        if not self.size:
            return "—"
        units = ("B", "KB", "MB", "GB")
        value = float(self.size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}".replace(".0 ", " ")
            value /= 1024
        return "—"


@dataclass
class RebuildPlan:
    """What the person asked for, as one object the adapter turns into policy."""

    sources: tuple[Path, ...]
    destination: Path | None = None
    preset: Preset = Preset.PRESERVE
    #: Setting key → value, exactly the deviations from the preset.
    overrides: dict = field(default_factory=dict)
    #: Whether questions may interrupt. A batch nobody is sitting in front of
    #: answers nothing and changes nothing it cannot justify.
    ask: bool = True

    @property
    def changed_count(self) -> int:
        return len(self.overrides)


@dataclass
class Progress:
    """One step of a long job, as the worker reports it."""

    done: int
    total: int
    name: str = ""
    #: "analysis", "rebuild", "validate" — what the number is counting.
    phase: str = ""

    @property
    def determinate(self) -> bool:
        return self.total > 0


@dataclass
class BatchOutcome:
    """The end of a run: the books as they finished, and how it ended."""

    books: tuple[BookItem, ...] = ()
    cancelled: bool = False
    destination: Path | None = None

    @property
    def written(self) -> int:
        return sum(1 for book in self.books if book.status.wrote_a_file)

    @property
    def attention(self) -> int:
        return sum(1 for book in self.books if book.status is BookStatus.ATTENTION)

    @property
    def failed(self) -> int:
        return sum(
            1 for book in self.books
            if book.status in (BookStatus.FAILED, BookStatus.BLOCKED)
        )

    @property
    def fixed(self) -> int:
        return sum(book.fixed for book in self.books)

    @property
    def all_well(self) -> bool:
        return bool(self.books) and not self.failed and not self.cancelled

    @property
    def folders(self) -> "tuple[str, ...]":
        """Every folder a file of this run actually landed in.

        `destination` is what the person *chose*, and it is `None` for the
        common case — books written beside their sources. Asking the books
        where they went is the only answer that is true in both cases, and it
        is the one the history needs: a run over three shelves lands in three
        folders and none of them is "the destination".
        """
        seen: list[str] = []
        for book in self.books:
            if book.output is None:
                continue
            place = str(Path(book.output).parent)
            if place not in seen:
                seen.append(place)
        return tuple(seen)


@dataclass
class JobRecord:
    """One line of history. Deliberately small: counts, statuses and paths.

    No book contents, no report bodies — the report stays where it was saved
    and this remembers where that is.
    """

    when: str
    count: int
    written: int
    attention: int
    failed: int
    preset: str
    destination: str = ""
    #: Every folder the run actually wrote into. A batch left to write beside
    #: its sources lands in as many folders as the books came from, and the old
    #: single `destination` was empty in exactly that case — the common one.
    #: `destination` is kept as the first of these so a history file written by
    #: an older version still reads, and one written by this version still
    #: opens in an older one.
    destinations: tuple[str, ...] = ()
    #: The first few titles, for a line a person recognises.
    titles: tuple[str, ...] = ()
    cancelled: bool = False

    @property
    def folders(self) -> "tuple[str, ...]":
        """The places to offer, from either field, without repeats."""
        seen = []
        for place in (*self.destinations, self.destination):
            if place and place not in seen:
                seen.append(place)
        return tuple(seen)

    @property
    def status(self) -> BookStatus:
        if self.cancelled:
            return BookStatus.CANCELLED
        if self.failed:
            return BookStatus.FAILED
        if self.attention:
            return BookStatus.ATTENTION
        return BookStatus.DONE

    def as_dict(self) -> dict:
        return {
            "when": self.when,
            "count": self.count,
            "written": self.written,
            "attention": self.attention,
            "failed": self.failed,
            "preset": self.preset,
            "destination": self.destination,
            "destinations": list(self.destinations),
            "titles": list(self.titles),
            "cancelled": self.cancelled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JobRecord":
        return cls(
            when=str(data.get("when", "")),
            count=int(data.get("count", 0)),
            written=int(data.get("written", 0)),
            attention=int(data.get("attention", 0)),
            failed=int(data.get("failed", 0)),
            preset=str(data.get("preset", "")),
            destination=str(data.get("destination", "")),
            destinations=tuple(str(place) for place in data.get("destinations", ())),
            titles=tuple(str(title) for title in data.get("titles", ())),
            cancelled=bool(data.get("cancelled", False)),
        )
