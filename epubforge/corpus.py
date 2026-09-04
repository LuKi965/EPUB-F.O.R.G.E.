"""Regression against real books, without holding anybody's book.

A corpus is a folder of EPUBs and a folder of *signatures*. A signature is what
we are willing to remember about somebody else's book: how many findings the
rebuild produced, whether the text survived, how many blocks it has, what
EPUBCheck said, and the hash of the result. No title, no author, not a word of
the text. Files are named by the hash of the book, because a listing of titles
in a public place says more about a shelf than about a tool.

The point is the last field. If a change to this tool alters the output for a
book, the hash moves and the comparison says so — a hard regression across a
library nobody had to hand over.

This lives in the package rather than in the test suite because it is a feature,
not a fixture: the person with the books is not necessarily the person with a
checkout, and asking them to install Python to help is asking too much. The
tests are a thin wrapper over what is here.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field

from .pipeline import rebuild
from .policy import Policy
from .report import Level
from . import dictionaries
from .validate import find_epubcheck, validate

#: Pinned, so a signature is a function of the book and not of the day it ran.
FROZEN_MODIFIED = "2020-01-01T00:00:00Z"

#: Every mode is measured. `preserve` is what people actually get, and
#: measuring only `strict` would leave the default path unwatched.
#:
#: `minimal` was missing until the corpus was complete enough to notice. The
#: roadmap justifies a whole family — fixed layout and comics — with the words
#: "a test of whether minimal mode engages", and the corpus never ran that mode
#: on anything. The family was filled for a purpose nothing measured, which is
#: the same shape of mistake as counting books instead of counting families.
#:
#: It costs a third more wall time per book, which is why it arrives together
#: with the run being parallel.
MODES = ("minimal", "preserve", "strict")

#: What the container-only mode reports when a document carries markup that was
#: legal in EPUB 2 and is not in EPUB 3. Named here because the ledger reads it:
#: an error that mode cannot reach is only excused when the tool **said so**.
#:
#: That condition is the whole safeguard. "Container-only failed and the full
#: rebuild did not, so it must be the mode's contract" would have quietly
#: excused a real defect — 0.2.11's missing `properties="svg"` was exactly that
#: shape, a package this mode generated and got wrong while `preserve` got it
#: right. Requiring the tool to name the construct first means an error it does
#: not understand is still counted against it.
STRANDED_BY_MODE = "xhtml.epub2-only-markup"

#: Sentences the container-only mode is contractually unable to answer,
#: described as **classes** rather than as a list of attribute names.
#:
#: EF-054, i to jest jego druga połowa. Pierwsza wersja wymieniała `valign`,
#: `value`, `clear`, `link`, `vlink`, `target` — sześć nazw wziętych z tego, co
#: akurat wyszło na dwóch półkach. Przebieg kontrolny natychmiast pokazał, ile
#: to jest warte: `introduced` skoczyło z zera na **42**, a czterdzieści jeden
#: z tych błędów to `align`, `bordercolor`, `cellpadding`, `cellspacing` —
#: dokładnie ta sama klasa, tylko inne słowa.
#:
#: Lista nazw jest tu z założenia przegrana. Ten tryb **kopiuje dokumenty bajt
#: w bajt** i zmienia w nich dwie rzeczy w głowie; nie usuwa atrybutów, nie
#: tyka arkuszy i nie przepisuje treści. Więc każdy błąd tej klasy jest
#: nieosiągalny niezależnie od tego, jak nazywa się atrybut — i tak to jest
#: teraz zapisane.
STRANDED_PATTERNS = (
    # Atrybut, którego element nie ma prawa nieść. Tryb kontenerowy nie usuwa
    # atrybutów, więc żaden taki błąd nie może być jego.
    re.compile(r'attribute "[^"]+" not allowed'),
    # Wartość atrybutu z czasów, gdy była legalna — `<img width="50%">`.
    re.compile(r'value of attribute "[^"]+" is invalid'),
    # Element w miejscu, w którym HTML5 go nie przewiduje.
    re.compile(r'element "[^"]+" not allowed'),
    # Arkusze stylów są w tym trybie przepisywane bajt w bajt.
    re.compile(r"^CSS-\d+"),
)

#: Zdania spoza klas wyżej, wymienione z nazwy, bo są pojedynczymi kształtami,
#: a nie rodzinami. Każde ma za sobą pomiar na prawdziwej książce.
STRANDED_SHAPES = (
    # EF-045: deklaracja kodowania z czasów EPUB 2.
    "meta element in encoding declaration state",
    # EF-053: breadcrumb DRM-u Adobe, `value` zamiast `content`.
    'element "meta" missing required attribute "content"',
    # EF-054: sześć powtórzonych `id` **już w źródle**, w tych samych sześciu
    # dokumentach, o które przyczepia się walidator. Stara ścieżka walidacji
    # tego nie sprawdzała, nowa sprawdza.
    "Duplicate ID",
)


def _the_mode_cannot_reach(shape: str) -> bool:
    """Whether this EPUBCheck sentence is one the container-only mode may not fix.

    **Nie odwrotność „co ten tryb psuje", tylko odpowiedź na „czego ten tryb
    dotyka".** Dotyka dokumentu pakietu, nawigacji, NCX-a i kontenera, a wewnątrz
    dokumentów treści — deklaracji typu i pustego `<title>`. Wszystko inne
    przepisuje bajt w bajt, więc błąd w treści nie jest jego sprawą.
    """
    if any(fragment in shape for fragment in STRANDED_SHAPES):
        return True
    return any(pattern.search(shape) for pattern in STRANDED_PATTERNS)


def _split_by_reach(origin: dict, check: dict, rules: dict, added: int) -> "tuple[int, int, Counter]":
    """Added errors, split into what the mode could not reach and what is ours.

    By **shape** where the measurement has shapes, which is every signature this
    program has recorded since it learned to keep them. Older ones — and any
    caller handing in counts alone — fall back to the previous question: is the
    stranded rule present. The fallback is deliberately the *old* behaviour and
    not a refusal to answer: a signature that predates a field is not a book
    that changed, and treating it as one is the host-dependence mistake in
    another costume.
    """
    gained = _new_shapes(origin, check)
    if not (check.get("shapes") or {}):
        # Three levels, poorest measurement last. By code where there are codes
        # — never by the net total, which is EF-052 and would have come straight
        # back in the one path nothing on the shelves exercises. By the total
        # only where the measurement holds neither, which is a signature older
        # than both fields.
        by_code = _new_codes(origin, check)
        if by_code or (check.get("codes") or {}):
            if STRANDED_BY_MODE in (rules or {}):
                return sum(by_code.values()), 0, Counter()
            return 0, sum(by_code.values()), by_code
        if STRANDED_BY_MODE in (rules or {}):
            return added, 0, Counter()
        return 0, added, Counter()

    unreachable = sum(
        number for shape, number in gained.items() if _the_mode_cannot_reach(shape)
    )
    mine = Counter(
        {
            shape: number
            for shape, number in gained.items()
            if not _the_mode_cannot_reach(shape)
        }
    )
    return unreachable, sum(mine.values()), mine

#: The mode that promises *not* to fix things. A container-only rebuild leaves
#: every content document byte for byte, so a source whose XHTML is invalid
#: stays invalid — deliberately, because the alternative is touching content in
#: the one mode that exists to promise it will not.
#:
#: This has to be written down somewhere the run summary can read, and until it
#: was, the summary called those errors ours. The first run that measured
#: `minimal` reported **44 errors across 31 books** and marked itself unclean,
#: while `preserve` and `strict` came out at zero on the same shelf — 44 defects
#: the source already had, counted against the release that carried them
#: faithfully. Left alone, that made the alpha condition unreachable: the corpus
#: could never be green again, for doing exactly what it said it would.
CARRIES_SOURCE_DEFECTS = frozenset({"minimal"})

#: Rules that describe **the machine running the rebuild** rather than the
#: rebuild. They are true, they belong in a report, and they must never reach a
#: signature: a regression net whose answer changes with the host is not a net.
#:
#: `epubcheck.*` is the case WP-12 was written for. `epubcheck.clean` appeared
#: in every strict signature here, so a recorded corpus could only be reproduced
#: on a machine with Java, and a run without one reported thirteen books as
#: "changed" when nothing about any book had changed. The verdict itself is kept
#: separately and honestly in the `epubcheck` field, which is already omitted
#: when there is nothing to record.
#:
#: `hyphens.no-dictionary` (WP-10) is the same shape and arrived the same way:
#: it says the hyphen detector had no dictionary to ask, which is true of a
#: checkout and of CI and false of an installed release. Recording it would pin
#: the corpus to machines without dictionaries — the WP-12 mistake, inverted.
_MACHINE_RATHER_THAN_BOOK = frozenset({"hyphens.no-dictionary"})
_MACHINE_PREFIXES = ("epubcheck.",)


def describes_the_machine(rule: "str | None") -> bool:
    """Whether *rule* reports on the host rather than on the book."""
    if not rule:
        return False
    return rule in _MACHINE_RATHER_THAN_BOOK or rule.startswith(_MACHINE_PREFIXES)


@dataclass
class Comparison:
    """What changed for one book between the recorded run and this one."""

    book: str
    identifier: str
    status: str  # "new" | "unchanged" | "changed" | "duplicate" | "failed"
    differences: list[str] = field(default_factory=list)
    #: What *this* run measured, as opposed to what the signature file holds.
    #:
    #: EF-051. Without it the ledger and the summary read the recorded files,
    #: which without `--record` are the previous run — so one line answered two
    #: questions from two different moments: "14 changed" about now and
    #: "3 introduced" about last time. Caught by disbelieving a fix: the run
    #: after EF-045 still printed the old three, and for a minute that looked
    #: like the repair had not worked.
    measured: "dict | None" = None

    @property
    def ok(self) -> bool:
        return self.status in ("new", "unchanged", "duplicate")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


#: A signature file is named after the book's digest: sixteen hex characters.
#: Matching on the name rather than on the extension is what keeps a stray
#: document in the folder from being read as a book that never existed.
_SIGNATURE_NAME = re.compile(r"^[0-9a-f]{16}\.json$")


def signature_files(folder: pathlib.Path) -> "list[pathlib.Path]":
    """Every signature in *folder*, and nothing else that happens to be there."""
    return sorted(p for p in folder.glob("*.json") if _SIGNATURE_NAME.match(p.name))


def identifier_for(book: pathlib.Path) -> str:
    return hashlib.sha256(book.read_bytes()).hexdigest()[:16]


def books_in(folder: pathlib.Path) -> list[pathlib.Path]:
    """Every book under *folder*, subfolders included.

    Libraries are filed — by author, by series, by shop — and a corpus that
    only read the top level silently measured one book out of a shelf of
    hundreds while reporting success. The survey has always walked the tree;
    this now agrees with it.
    """
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".epub"
    )


def _text_survived(before: pathlib.Path, after: pathlib.Path) -> bool:
    """Whether every character of *before*'s reading order is still in *after*.

    The reading half of `_survives`, kept because "did this book's text survive
    into that one" is the question, and two paths are how it is naturally asked.
    A corpus run has already read the source — once, for all three modes — and
    calls the inner form directly rather than parsing it again per mode.
    """
    from .fidelity import spine_text_of

    try:
        return _survives(spine_text_of(before), after)
    except Exception:  # noqa: BLE001 — an unreadable book is reported elsewhere
        return False


def _survives(source_text: str, after: pathlib.Path) -> bool:
    """Whether every character of the source's reading order is still there.

    K1 as it is actually written: *no character is lost*. Not "the counts
    match" — that forbids the rebuild from generating a cover page, which it is
    supposed to do — and not "the output is no shorter", which a book could
    satisfy while losing a chapter and gaining a longer one.

    Whitespace is compared loosely because the rebuild reflows markup, and
    collapsing runs of spaces is not losing text. Everything else has to appear,
    in order.
    """
    from .fidelity import first_character_lost, spine_text_of

    try:
        result = spine_text_of(after)
    except Exception:  # noqa: BLE001 — an unreadable book is reported elsewhere
        return False

    # Subsequence rather than substring: the rebuild may insert text between
    # documents (a generated cover page) without having lost any. The comparison
    # itself moved to `fidelity` in WP-11, so the gate in front of the writer and
    # this corpus mean the same thing by K1 — two definitions of the invariant
    # this program is built around would be one too many.
    return first_character_lost(source_text, result) < 0


_checker_identity: "str | None" = None


def checker_identity() -> str:
    """Which EPUBCheck this is, as a hash of the jar that will run.

    Recorded beside a verdict so the verdict can be reused. A version string
    would be cheaper to read and worse to trust: two builds can carry the same
    version, and reading it costs a JVM start of its own. The jar's bytes are
    the thing that decides the answer, so the jar's bytes are what is compared.

    Hashed once per process. Thirty megabytes takes a tenth of a second, against
    the five and a half seconds one validation costs.
    """
    global _checker_identity
    if _checker_identity is not None:
        return _checker_identity
    command = find_epubcheck()
    if command is None:
        _checker_identity = "none"
        return _checker_identity
    jars = [part for part in command if part.lower().endswith(".jar")]
    try:
        payload = b"".join(pathlib.Path(jar).read_bytes() for jar in jars) or b"".join(
            part.encode() for part in command
        )
        _checker_identity = hashlib.sha256(payload).hexdigest()[:16]
    except OSError:
        _checker_identity = "unreadable"
    return _checker_identity


def _reusable_verdict(previous: "dict | None", output_digest: str) -> "dict | None":
    """The recorded EPUBCheck verdict, when it cannot have changed.

    EPUBCheck is a pure function of two things: the jar and the bytes it reads.
    When both match what produced the recorded verdict, running it again is four
    fifths of the corpus's wall time spent to learn something already written
    down — and on a check where nothing has moved, that is every book.

    Both halves are required. Matching bytes alone would keep serving an old
    answer across an EPUBCheck upgrade, which is precisely when the answer is
    expected to change and precisely when nobody would think to look.
    """
    if not previous:
        return None
    verdict = previous.get("epubcheck")
    if not verdict or previous.get("output") != output_digest:
        return None
    if previous.get("checker") != checker_identity():
        return None
    # A verdict recorded before the identifiers existed is a count with no
    # explanation, and reuse would keep it that way for as long as the book and
    # the jar hold still — which for a private corpus is forever. `{}` counts as
    # recorded: it is what a clean book has.
    if verdict.get("codes") is None:
        return None
    # `shapes` arrived one release after `codes`, for the same reason and with
    # the same consequence: a verdict taken before it existed explains nothing,
    # and on a corpus whose books never change it would be reused for ever.
    # Absent is only allowed when there was nothing to explain.
    if verdict.get("errors") or verdict.get("fatal"):
        if verdict.get("shapes") is None:
            return None
    return verdict


@dataclass
class _Source:
    """What a book is before the rebuild touches it, measured once.

    Only the two things a mode's measurement compares against: how many
    characters the reading order held, and that text itself for the K1
    subsequence check. Not the whole inventory — nothing else was ever read.
    """

    characters: int
    text: str


def _read_source(book: pathlib.Path) -> _Source:
    from .inventory import measure as inventory_measure

    try:
        characters = inventory_measure(book).fields.get("spine_text_characters", 0)
        # Folded exactly as the output side is folded. WP-11: the two sides went
        # through different normalisations for one commit and every book in the
        # corpus reported its text as lost — which is what happens when "the
        # same text" has two definitions.
        from .fidelity import spine_text_of

        text = spine_text_of(book)
    except Exception:  # noqa: BLE001 — an unreadable book is reported elsewhere
        return _Source(0, "")
    return _Source(characters, text)


def _measure(
    book: pathlib.Path,
    destination: pathlib.Path,
    mode: str,
    source: "_Source | None" = None,
    previous: "dict | None" = None,
) -> dict:
    from .inventory import measure as inventory_measure  # local: avoids a cycle

    # Everything about the *source* is the same for every mode, and it used to
    # be recomputed for each: two full inventory passes and a spine-text parse
    # per mode, over a file that had not changed since the last one. With three
    # modes that is two thirds of the source work thrown away.
    source = source or _read_source(book)
    # `render_gate="off"` for the same reason the signatures do not ask
    # EPUBCheck by default: a signature has to be a function of the *book and
    # this program*, and nothing else. With the render gate on, the answer would
    # depend on whether the machine taking the measurement happens to have a
    # browser — a shelf recorded on one laptop would come back "changed" on
    # another, having changed in no way at all. It also costs about thirty-six
    # seconds per book per mode, on a run that already measures three modes.
    policy = Policy.preset(
        mode, modified_override=FROZEN_MODIFIED, render_gate="off"
    )
    # Without a dictionary, deliberately. The third application of one rule
    # (WP-12): a regression net whose answer changes with the host is not a net.
    # A dictionary settles hyphens the detector would otherwise leave alone, so
    # a corpus recorded on a machine that had one could only be reproduced on
    # such a machine — and the Windows build, which downloads dictionaries
    # *after* running the tests, duly reported a book as changed that nobody had
    # touched. Filtering a rule name cannot fix this one, because the two runs
    # genuinely did different work. See `dictionaries.suppressed`.
    with dictionaries.suppressed():
        result = rebuild(str(book), str(destination), policy)

    # Counters by level say a book gained three fixes. Counters by rule say
    # *which* three, so a signature that moves reads as "this book stopped
    # losing its contents page" rather than as "a number went up" — which is
    # the difference between a regression net and a tripwire (EF-018).
    # What `describes_the_machine` filters out is deliberately not among them,
    # and that is WP-12.
    #
    # Counted over the same findings, and filtered the same way, because
    # `report.info` counting one finding that `rules` does not is a
    # disagreement waiting to be recorded as a regression.
    counted = [
        finding
        for finding in result.report.findings
        if not describes_the_machine(finding.rule)
    ]
    rules: Counter = Counter(f.rule for f in counted if f.rule)
    levels: Counter = Counter(finding.level.value for finding in counted)

    measurement: dict = {
        "written": result.output_path is not None,
        "report": {
            level.value: levels[level.value] for level in Level if levels[level.value]
        },
        "rules": dict(sorted(rules.items())),
    }
    if result.output_path is None:
        return measurement

    output = pathlib.Path(result.output_path)
    measurement["output"] = digest(output.read_bytes())

    after = inventory_measure(output).fields
    # Spine text only: the generated navigation document's chapter titles are
    # text too, and counting them made every EPUB 2 book report that its text
    # had changed.
    #
    # **K1 is "no character is lost", not "no character is added."** Comparing
    # counts for equality was false for every book arriving without a cover page
    # in its spine, because generating one adds two characters — all six
    # Gutenberg books failed on that alone.
    #
    # Counting cannot say K1 holds anyway: two books can carry the same number
    # of characters and not the same characters. So the source's spine text has
    # to still be *in* the output's, in order, and the count is kept beside it
    # as a number a human can read.
    measurement["text_characters"] = after.get("spine_text_characters", 0)
    measurement["text_added"] = (
        after.get("spine_text_characters", 0) - source.characters
    )
    measurement["text_invariant"] = _survives(source.text, output)
    # K1 compares a stream of characters and cannot see two paragraphs merged
    # into one. Recording the count gives that change its own line in the diff.
    measurement["blocks"] = after.get("blocks", 0)

    if find_epubcheck() is not None:
        measurement["checker"] = checker_identity()
        recorded = _reusable_verdict(previous, measurement["output"])
        if recorded is not None:
            measurement["epubcheck"] = recorded
        else:
            measurement["epubcheck"] = _verdict(validate(result.output_path))
    return measurement


def _verdict(check) -> dict:
    """What EPUBCheck said, in the form a signature is allowed to keep.

    Three counts and the identifiers behind them. The identifiers are the point:
    a run that says "14 errors introduced" and cannot say which rules they broke
    is a smoke alarm with no address, and the books are on somebody else's disk.
    `RSC-005` names a rule in EPUBCheck's own vocabulary and nothing about the
    book, so it stays inside the promise this file opens with.
    """
    verdict = {
        "errors": check.errors,
        "warnings": check.warnings,
        "fatal": check.fatal,
        "codes": check.codes,
    }
    # Only when there is something to explain. A clean book recording an empty
    # dictionary of shapes would put the field in ninety-three signatures to say
    # nothing ninety-three times.
    if check.shapes:
        verdict["shapes"] = check.shapes
    return verdict


def signature(
    book: pathlib.Path, scratch: pathlib.Path, previous: "dict | None" = None
) -> dict:
    """One book's measurements, stamped with the release that took them.

    The stamp is not decoration. Entry into alpha asks for the corpus to be
    green "across three consecutive releases", and until now a signature said
    nothing about which release produced it — so the condition could only be
    answered from memory, which is how the family count came to be wrong. A
    partial run stamps only the books it touched, and the rest keep the release
    they were last measured on: mixed is the truth, and it is now visible.
    """
    from . import __version__

    # Unique per **measurement**, not per book. Books are measured side by side,
    # and two threads sharing a directory check files the other has overwritten
    # — a race that answers wrongly rather than crashing.
    #
    # Keying by the book's content hash reopened it for the case that bites
    # hardest: a shelf holding the same file twice hands two threads one room.
    # Measured on the owner's second shelf, where four books are exact
    # duplicates: four `PermissionError`s on Windows. Windows was the lucky
    # part — the same race on Linux is silent.
    scratch.mkdir(parents=True, exist_ok=True)
    room = pathlib.Path(tempfile.mkdtemp(prefix=identifier_for(book) + "-", dir=scratch))

    source = _read_source(book)
    source_digest = digest(book.read_bytes())
    record: dict = {"source": source_digest, "version": __version__}
    if find_epubcheck() is not None:
        record["checker"] = checker_identity()
        # What the book was already wrong about, before anything touched it.
        # Container-only mode leaves content documents byte for byte, so an
        # error inside one of them is the source's and always will be; without
        # this number there is no way to tell that apart from an error the
        # rebuild introduced, and the run summary was calling both the same.
        #
        # A book's identifier *is* the hash of its bytes, so this can never go
        # stale for a book that still exists: read once, then reused for as long
        # as EPUBCheck itself does not change.
        stale = (previous or {}).get("source") != source_digest or (
            previous or {}
        ).get("checker") != record["checker"]
        recorded = None if stale else (previous or {}).get("source_epubcheck")
        if recorded is not None and (
            recorded.get("codes") is None
            or ((recorded.get("errors") or recorded.get("fatal"))
                and recorded.get("shapes") is None)
        ):
            recorded = None  # counted before we could explain it; ask again
        if recorded is None:
            recorded = _verdict(validate(str(book)))
        record["source_epubcheck"] = recorded
    for mode in MODES:
        record[mode] = _measure(
            book, room / f"{mode}.epub", mode, source, (previous or {}).get(mode)
        )
    return record


def releases(records: "list[dict]") -> "dict[str, int]":
    """How many books were last measured on each release."""
    counted: Counter = Counter(record.get("version", "?") for record in records)
    return dict(sorted(counted.items()))


def _scope(entry: dict) -> "tuple[int, tuple[str, ...]]":
    """What a run measured: how many books, in how many modes.

    Not *what it found* — that is the verdict. This is the size of the question
    that was asked, and it is what has to hold still for two verdicts to be
    comparable.
    """
    return (entry.get("books", 0), tuple(entry.get("modes") or ()))


def _widened(previous: "dict | None", entry: dict) -> bool:
    """Whether *entry* asked a larger question than the run before it.

    Strictly larger, in both directions at once or in either alone: more books,
    or the same books in more modes. A run over *fewer* books is not a widening
    however it comes out — a shrinking corpus that reports clean is exactly the
    shape of evidence this ledger exists to refuse.
    """
    if previous is None:
        return False
    books_before, modes_before = _scope(previous)
    books_now, modes_now = _scope(entry)
    if books_now < books_before or not set(modes_before) <= set(modes_now):
        return False
    return books_now > books_before or len(modes_now) > len(modes_before)


def green_streak(history: "list[dict]", *, minimum: int = 1) -> "list[str]":
    """The run of consecutive releases that came out clean, most recent last.

    Read from the run ledger rather than from the signatures: a signature keeps
    a book's latest measurement only, so re-measuring a book erases the release
    it was green on before. History is the question being asked here.

    *minimum* is how many books a run must cover to count at all. A run over
    three books says nothing about a corpus of eighty-six, and letting it extend
    a streak would be the same mistake as counting books instead of families.

    **A release that widened the measurement is passed over rather than counted
    against.** Every corpus run so far but one asked a larger question than the
    run before it — 38 books, then 70, then 87, 91, 93, then the same 93 in a
    third mode — and under the old rule each of those resets the count to zero.
    That made "green across three consecutive releases" not a bar this project
    could clear but a bar it was forbidden to approach, because the way to clear
    it was to stop looking at more books. The corpus is here to find defects; a
    rule that punishes it for succeeding is the rule that is wrong.

    Passed over, not counted as green: a widening release neither extends the
    streak nor ends it, and `widenings()` lists them so the gap is on the record
    rather than papered over. What stops a real regression hiding in that gap is
    that it does not go away — the next run at unchanged scope finds it, and
    that one resets the count. The exemption is for the release that grew, not
    for the defect it found.
    """
    streak: list[str] = []
    previous: "dict | None" = None
    for entry in history:
        if entry.get("books", 0) < minimum:
            continue
        if _widened(previous, entry):
            previous = entry
            continue
        previous = entry
        if entry.get("clean"):
            if not streak or streak[-1] != entry.get("version"):
                streak.append(entry.get("version", "?"))
        else:
            streak = []
    return streak


def widenings(history: "list[dict]", *, minimum: int = 1) -> "list[str]":
    """The releases that asked a larger question than the run before them.

    The other half of the rule above. A streak that skips releases without
    saying which, or why, is a number to be taken on trust; this is the
    accompanying list that makes it checkable.
    """
    grown: list[str] = []
    previous: "dict | None" = None
    for entry in history:
        if entry.get("books", 0) < minimum:
            continue
        if _widened(previous, entry):
            grown.append(entry.get("version", "?"))
        previous = entry
    return grown


def _rule_changes(recorded: dict, measured: dict) -> str:
    """What started happening and what stopped, in one line."""
    parts: list[str] = []
    for rule in sorted(set(recorded) | set(measured)):
        before, after = recorded.get(rule, 0), measured.get(rule, 0)
        if before == after:
            continue
        if not before:
            parts.append(f"+{rule}" + (f" ×{after}" if after > 1 else ""))
        elif not after:
            parts.append(f"−{rule}")
        else:
            parts.append(f"{rule} {before}→{after}")
    return ", ".join(parts)


#: Fields that say *when* a measurement was taken rather than *what* it found.
#: A diff over them is noise: bumping the version would report every book in the
#: corpus as changed and bury the one book that really did.
#: Fields that describe the *measurement* rather than the book. A release stamp
#: and the identity of the validator both move without anything about the book
#: having changed, and reporting them as differences would drown the ones that
#: matter — which is what happened the first time the version was recorded.
_METADATA = frozenset({"version", "checker"})
_MODE_METADATA = frozenset({"checker"})

#: Blocks whose *absence* from a recorded signature means the field did not
#: exist yet, rather than that its value was nothing. Every one of them arrived
#: after books were already recorded: the modes when `minimal` joined, the
#: source's own verdict when carried defects had to be told from introduced
#: ones, the identifiers when a count stopped being enough to act on.
_NEWLY_MEASURED = frozenset({*MODES, "source_epubcheck", "epubcheck", "codes"})

#: How `differences` says a field could not be measured on this machine. Matched
#: rather than re-derived, so the sentence and the rule that reads it cannot
#: drift apart.
NOT_MEASURED_HERE = "nie zmierzone tutaj"

#: Fields that only exist when EPUBCheck was reachable. Their absence is a fact
#: about the machine, not about the book — see `differences`.
_NEEDS_A_VALIDATOR = frozenset({"source_epubcheck", "epubcheck", "checker"})


def differences(recorded: dict, measured: dict, path: str = "") -> list[str]:
    """Field-level diff, so a change reads as a sentence and not as two hashes."""
    lines: list[str] = []
    for key in sorted(set(recorded) | set(measured)):
        here = f"{path}.{key}" if path else key
        old, new = recorded.get(key), measured.get(key)
        if not path and key in _METADATA:
            continue
        if path in MODES and key in _MODE_METADATA:
            continue
        # A field the recorded signature never held. Adding `minimal` made every
        # book in the corpus report the whole block as a difference — ninety
        # lines each, ninety-three times, for a change in what is measured
        # rather than in how a book rebuilds. Adding the EPUBCheck identifiers
        # did the same on a smaller scale. There is nothing to compare against,
        # so say that, and say it once.
        #
        # Named rather than inferred, because absence means two different
        # things in this file. In a counter — `report`, `rules`, `codes`'
        # contents — a missing key means the count was zero, and calling that
        # "not measured" would be a lie about a measurement that ran. In these
        # four it means the field did not exist when the signature was written.
        if key in _NEWLY_MEASURED and key not in recorded and new is not None:
            lines.append(f"{here}: not measured before")
            continue
        # And the mirror image: a field the recorded signature holds that this
        # run could not measure, because this machine has no validator.
        #
        # WP-12. Without it, running the corpus on a machine without Java
        # reported every book as changed — thirteen of thirteen — for the
        # single reason that `epubcheck` and `checker` are missing from the
        # measurement. That is a fact about the machine and it is worth saying,
        # once per field, but it is not a book that rebuilds differently. Said
        # rather than skipped, because a signature quietly compared over fewer
        # fields is a weaker net wearing the same name.
        if key in _NEEDS_A_VALIDATOR and new is None and old is not None:
            lines.append(f"{here}: nie zmierzone tutaj (brak walidatora)")
            continue
        if key == "rules" and isinstance(old, dict) and isinstance(new, dict):
            # Rendered as one line naming what appeared and what stopped,
            # because "rules.nav.repointed: None → 1" spread over eight lines is
            # a diff nobody reads. This is the line that says *which* behaviour
            # moved rather than that a number did.
            change = _rule_changes(old, new)
            if change:
                lines.append(f"{here}: {change}")
        elif isinstance(old, dict) and isinstance(new, dict):
            lines.extend(differences(old, new, here))
        elif old != new:
            lines.append(f"{here}: {old!r} → {new!r}")
    return lines


def workers_for(books: int, requested: int | None = None) -> int:
    """How many books to measure at once.

    Four fifths of a book's cost is EPUBCheck, and EPUBCheck is a JVM this
    program starts, waits for, and reads the output of. Waiting is not work:
    during it the interpreter holds nothing and the machine does nothing. On an
    eight-core desktop the corpus ran at 6% CPU for exactly that reason —
    ninety-three books, three modes, two hundred and seventy-nine JVMs, one
    after another.

    Threads rather than processes, deliberately. The expensive part is a
    subprocess wait, which releases the GIL, so threads buy nearly all of the
    available speedup; and this runs inside a frozen Windows GUI, where a
    process pool without `freeze_support` relaunches the whole application once
    per worker. That failure is a fork bomb on a user's desktop, and the
    remaining fraction of a speedup is not worth standing next to it.

    Capped at eight: each JVM wants a few hundred megabytes, and a machine that
    starts sixteen of them at once spends the difference in swap.
    """
    import os

    if requested is not None:
        return max(1, requested)
    return max(1, min(8, os.cpu_count() or 1, books))


def compare(
    books: pathlib.Path,
    signatures: pathlib.Path,
    *,
    record: bool = False,
    on_book=None,
    workers: int | None = None,
) -> list[Comparison]:
    """Check every book against its signature, optionally rewriting them.

    With ``record`` off this is a regression test. With it on, it is how a
    deliberate change gets accepted — and it still reports what moved, because
    "40 hashes changed" is not something anybody can review.

    Books are measured side by side; the results come back in shelf order
    regardless, because a corpus report that shuffles itself between runs is one
    nobody can diff.

    A shelf may hold the same file twice — the owner's second one does, four
    times over, being a folder downloaded whole. A signature is named after the
    book's bytes, so both copies are one signature and measuring the second is
    three JVM runs spent to learn what the first already said. Worse than
    wasteful: both copies wrote to one working directory and both were counted
    into the ledger, so a shelf of 67 files reported the totals of 71. Duplicates
    are now named as such and measured once.
    """
    import concurrent.futures
    import threading

    signatures.mkdir(parents=True, exist_ok=True)
    shelf = books_in(books)
    if not shelf:
        return []

    done = 0
    progress_lock = threading.Lock()

    def label_for(book: pathlib.Path) -> str:
        # Relative to the corpus root: two shelves may hold a file of the same
        # name, and "changed: ksiazka.epub" would then be ambiguous.
        return str(book.relative_to(books)) if book.is_relative_to(books) else book.name

    # Read once, here, rather than inside every worker: the identifier is the
    # hash of the whole file, and the grouping below needs it before any thread
    # starts anyway.
    identity = {book: identifier_for(book) for book in shelf}
    original: dict[str, pathlib.Path] = {}
    copies: dict[pathlib.Path, pathlib.Path] = {}
    for book in shelf:
        first = original.setdefault(identity[book], book)
        if first is not book:
            copies[book] = first

    def measure_one(book: pathlib.Path, scratch: str) -> Comparison:
        nonlocal done
        label = label_for(book)
        identifier = identity[book]
        reference = signatures / f"{identifier}.json"
        previous = (
            json.loads(reference.read_text(encoding="utf-8"))
            if reference.is_file()
            else None
        )

        try:
            current = signature(book, pathlib.Path(scratch), previous)
        except Exception as exc:  # noqa: BLE001 — one bad book is a finding
            outcome = Comparison(
                label, identifier, "failed", [f"{type(exc).__name__}: {exc}"]
            )
        else:
            if previous is None:
                status, changes = "new", []
            else:
                changes = differences(previous, current)
                # A note about the machine is not a book that rebuilt
                # differently. WP-12: on a machine without Java every book said
                # "changed" because two fields were missing from the
                # measurement, which turns a regression net into a tripwire for
                # the environment. The lines stay in the output — the run is
                # weaker and says so — but they do not fail the comparison.
                moved = [line for line in changes if NOT_MEASURED_HERE not in line]
                status = "unchanged" if not moved else "changed"
            if record:
                reference.write_text(
                    json.dumps(current, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            outcome = Comparison(label, identifier, status, changes, current)

        # Reported on completion rather than on start: with several books in
        # flight, "starting number 40" while 33 to 39 are still running is a
        # progress bar that lies about how much is left.
        if on_book is not None:
            with progress_lock:
                done += 1
                on_book(done - 1, label)
        return outcome

    def note_copy(book: pathlib.Path) -> Comparison:
        nonlocal done
        label = label_for(book)
        if on_book is not None:
            with progress_lock:
                done += 1
                on_book(done - 1, label)
        return Comparison(
            label,
            identity[book],
            "duplicate",
            [f"byte for byte the same file as {label_for(copies[book])}"],
        )

    fresh = [book for book in shelf if book not in copies]
    with tempfile.TemporaryDirectory(prefix="epubforge-corpus-") as scratch:
        count = workers_for(len(fresh), workers)
        if count == 1:
            taken = [measure_one(book, scratch) for book in fresh]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                taken = list(pool.map(lambda b: measure_one(b, scratch), fresh))

    # Back into shelf order, duplicates in the place their file occupies. The
    # shelf has 67 files and the report says 67, because that is what is on the
    # disk; what it no longer does is count four of them twice.
    measured = dict(zip(fresh, taken))
    results = [measured[book] if book in measured else note_copy(book) for book in shelf]

    if record:
        _log_run(signatures, results)
    return results


#: One entry per corpus run, in the folder *containing* the signatures.
#:
#: Not among them. That folder means "one file per book", and anything else
#: living there is a trap for every loop that reads it — the owner's inventory
#: landed there once by accident and broke the analysis on the spot.
RUNS = "runs.json"


def _once_each(results: "list[Comparison]") -> "list[Comparison]":
    """The results, with a book that appears twice on the shelf counted once.

    Every total below is read out of `signatures/{identifier}.json`, and the
    identifier is the book's content hash — so two results for one file read the
    same signature and add its errors twice. The owner's second shelf holds four
    exact duplicates, and its ledger for 0.2.17 and 0.2.18 says 129 carried where
    the books say 122, and one error more than there is. The count of *files* is
    honest and stays; the count of *defects* has to be per book.
    """
    seen: set[str] = set()
    unique = []
    for result in results:
        if result.identifier in seen:
            continue
        seen.add(result.identifier)
        unique.append(result)
    return unique


def _new_shapes(source: dict, produced: dict) -> "Counter":
    """The sentences EPUBCheck says about the output and not about the source."""
    return Counter(produced.get("shapes") or {}) - Counter(source.get("shapes") or {})


def _new_codes(source: dict, produced: dict) -> "Counter":
    """The EPUBCheck rules broken by the rebuild and not by the book.

    Counted rather than set-differenced: a source with one `RSC-005` and an
    output with three has gained two, and calling that "nothing new" is how a
    real regression hides behind a defect the source already had.
    """
    return Counter(produced.get("codes") or {}) - Counter(source.get("codes") or {})


def _log_run(signatures: pathlib.Path, results: "list[Comparison]") -> None:
    """Append what this run measured, because a signature cannot remember.

    A signature holds a book's *latest* measurement, so the moment a book is
    re-measured its previous release is gone from the record. Entry into alpha
    asks for the corpus to be green "across three consecutive releases", and
    that is a question about history — which the signatures, by design, do not
    keep. Recording the release into them made a partial run visible and still
    could not answer it.

    So the runs are logged. One entry per `--record`, appended, never rewritten:
    what was measured, on which release, and whether it came out clean.
    """
    import datetime

    from . import __version__

    entry = {
        "version": __version__,
        "date": datetime.date.today().isoformat(),
        "books": len(results),
        # Half of what makes two runs comparable. Adding `minimal` widened the
        # measurement without moving the book count by one, and nothing in the
        # ledger recorded it — so the run that first measured a third mode read
        # as the same question asked again, and its answer as a regression.
        "modes": list(MODES),
        "failed": sum(1 for r in results if r.status == "failed"),
    }
    errors = introduced = carried = fatal = lost = unwritten = inherent = 0
    blamed: Counter = Counter()
    #: EF-052. Nazwy reguł **dołożonych przez tryb kontenerowy**, liczone po
    #: kodach, a nie po sumie. `introduced` jest różnicą liczb i potrafi wyjść
    #: zerem, gdy przebudowa naprawi jeden błąd źródła i dołoży inny — na
    #: kolekcji 67 zdarzyło się to trzy razy: znikało `NCX-001`, pojawiało się
    #: `RSC-005`, suma stała w miejscu i dziennik pisał `introduced: 0`.
    #: Wymiana błędu na inny błąd nie jest brakiem błędu.
    ours: Counter = Counter()
    for result in _once_each(results):
        measured = result.measured
        if measured is None:
            record_path = signatures / f"{result.identifier}.json"
            if not record_path.is_file():
                continue
            measured = json.loads(record_path.read_text(encoding="utf-8"))
        origin = measured.get("source_epubcheck") or {}
        source = origin.get("errors", 0)
        for mode in MODES:
            found = measured.get(mode) or {}
            if not found.get("written"):
                unwritten += 1
                continue
            check = found.get("epubcheck") or {}
            count = check.get("errors", 0)
            fatal += check.get("fatal", 0)
            if mode in CARRIES_SOURCE_DEFECTS:
                # Judged on what it added, not on what it declined to fix.
                added = max(0, count - source)
                carried += min(count, source)
                # EF-054. Split by **shape**, not by whether the report
                # happens to carry the stranded rule: an error the mode cannot
                # reach is one whose sentence it cannot answer, and the presence
                # of one such sentence says nothing about the next.
                unreachable, mine, shapes = _split_by_reach(
                    origin, check, found.get("rules") or {}, added
                )
                inherent += unreachable
                if mine:
                    introduced += mine
                    ours.update(
                        Counter(
                            {shape.split(":")[0]: number for shape, number in shapes.items()}
                        )
                    )
                    blamed.update(_new_codes(origin, check))
            else:
                errors += count
                # Only what the source did **not** already have — the same
                # subtraction the report does, and for the same reason. 0.2.18
                # fixed a summary line that added every code it saw under a
                # heading reading "Ours" and left this one adding every code it
                # saw into a field named `codes`. The mixed shelf's ledger
                # therefore blames 34 `RSC-005`, 8 `RSC-011` and 5 `RSC-007` on
                # a release whose honest figure was two rules and ten errors.
                # A report and a ledger disagreeing about whose fault something
                # is means one of them is lying, and it was this one.
                blamed.update(_new_codes(origin, check))
            if not found.get("text_invariant", True):
                lost += 1
    entry.update(
        errors=errors,
        introduced=introduced,
        inherent=inherent,
        carried=carried,
        fatal=fatal,
        text_lost=lost,
        unwritten=unwritten,
    )
    if blamed:
        # Which EPUBCheck rules they were. Without this the ledger records that
        # something broke and leaves the reader with no next question to ask.
        entry["codes"] = dict(sorted(blamed.items()))
    if ours:
        # EF-052. Kept apart from `codes`, and apart from `introduced`, because
        # the three answer different questions: what was seen, how much the
        # total moved, and what this program put there. A run is not clean while
        # this field has anything in it, whatever the total did.
        entry["added_codes"] = dict(sorted(ours.items()))
    # `inherent` is deliberately absent from this line. It counts errors the
    # container-only mode is contractually unable to reach, on markup the report
    # names out loud — and a run cannot be held to a promise it kept.
    entry["clean"] = not (
        errors or introduced or fatal or lost or unwritten or entry["failed"] or ours
    )
    copies = len(results) - len(_once_each(results))
    if copies:
        # Stated rather than quietly subtracted: `books` counts the files on the
        # shelf, every total counts the books, and a reader comparing the two
        # needs to be told why they differ.
        entry["duplicates"] = copies

    ledger = signatures.parent / RUNS
    history = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    history.append(entry)
    ledger.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarise(results: list[Comparison], signatures: "pathlib.Path | None" = None) -> str:
    """The run in one or two lines.

    The second line only appears when the signatures are at hand, and it exists
    because a bare "44 errors" is a number that reads as failure and was not
    one: those were the source's, carried through by the mode that promises not
    to touch content. What a reader needs is the two figures apart.
    """
    counts = Counter(result.status for result in results)
    line = (
        f"{len(results)} book(s): {counts['unchanged']} unchanged, "
        f"{counts['changed']} changed, {counts['new']} new, {counts['failed']} failed"
    )
    if counts["duplicate"]:
        line += f", {counts['duplicate']} the same file twice"
    if signatures is None:
        return line

    tally = _tally_epubcheck(results, signatures)
    if not (tally.errors or tally.introduced or tally.carried or tally.inherent):
        return line
    parts = [f"{tally.errors} EPUBCheck error(s) in modes that rewrite content"]
    if tally.carried:
        parts.append(f"{tally.carried} source error(s) carried through by container-only mode")
    if tally.inherent:
        parts.append(
            f"{tally.inherent} it cannot reach without opening a document, and says so"
        )
    if tally.introduced:
        parts.append(f"{tally.introduced} introduced by it")
    line += "\n" + "; ".join(parts) + "."
    return line + _blame_lines(tally)


class _EpubcheckTally:
    """What the signatures say about EPUBCheck errors across a run, apart:
    the document-opening modes' errors, and the container-only mode's
    introduced, carried and inherent ones, with the rules behind each."""

    def __init__(self) -> None:
        self.errors = self.introduced = self.carried = self.inherent = 0
        self.blamed: Counter = Counter()
        self.said: Counter = Counter()
        #: EF-048. `blamed` is fed by **both** branches — the container-only one
        #: whose additions count as `introduced`, and the document-opening one whose
        #: errors count as `errors`. Printing it beside `introduced` therefore read
        #: as "these are the three", and on the mixed shelf it read as eight.
        self.ours: Counter = Counter()


def _tally_epubcheck(results: list, signatures: "pathlib.Path") -> _EpubcheckTally:
    tally = _EpubcheckTally()
    for result in _once_each(results):
        measured = result.measured
        if measured is None:
            path = signatures / f"{result.identifier}.json"
            if not path.is_file():
                continue
            measured = json.loads(path.read_text(encoding="utf-8"))
        origin = measured.get("source_epubcheck") or {}
        source = origin.get("errors", 0)
        for mode in MODES:
            check = (measured.get(mode) or {}).get("epubcheck") or {}
            count = check.get("errors", 0)
            if mode in CARRIES_SOURCE_DEFECTS:
                added = max(0, count - source)
                tally.carried += min(count, source)
                unreachable, mine, shapes = _split_by_reach(
                    origin, check, (measured.get(mode) or {}).get("rules") or {}, added
                )
                tally.inherent += unreachable
                if mine:
                    tally.introduced += mine
                    tally.blamed.update(_new_codes(origin, check))
                    for shape, number in shapes.items():
                        tally.said[shape] += number
                        tally.ours[shape.split(":")[0]] += number
            else:
                tally.errors += count
                # Only what the source did **not** already have. This branch
                # used to blame every code it saw, and the line beneath was
                # headed "Ours" — so a shelf of 67 books whose ledger said
                # `introduced: 3` printed six rule names under a heading
                # claiming all of them. It sent me looking for defects in this
                # tool that belonged to the books, and a report that misstates
                # whose fault something is, is worse than one that stays quiet.
                tally.blamed.update(_new_codes(origin, check))
                tally.said.update(_new_shapes(origin, check))
    return tally


def _blame_lines(tally: _EpubcheckTally) -> str:
    """The rule names behind the figures, under two headings (EF-048)."""
    def named(counter: "Counter") -> str:
        return ", ".join(
            f"{code} ×{count}" if count > 1 else code
            for code, count in sorted(counter.items())
        )

    text = ""
    # EF-048. Two headings rather than one, because the counters answer two
    # questions and one of them was standing under the other's title. `ours`
    # holds only what the container-only mode added — the same figure as
    # `introduced` — while `blamed` holds every rule not present in the source,
    # including the ones the document-opening modes count under `errors`. On
    # the mixed shelf that read as `introduced: 3` beside eight rule names, and
    # a reader had every right to take the eight for the three.
    if tally.ours:
        # Named by rule rather than counted, and printed even when the total
        # did not move: `introduced` is a difference of two numbers, and a book
        # that loses one error and gains another leaves it at zero.
        text += f"\nRules the container-only mode added: {named(tally.ours)}."
    if tally.blamed:
        rest = Counter(tally.blamed)
        rest.subtract(tally.ours)
        rest = Counter({code: count for code, count in rest.items() if count > 0})
        if rest:
            text += f"\nNot in the source, seen in any mode: {named(rest)}."
    if tally.said:
        text += "\n" + "\n".join(
            f"  {shape}" + (f" ×{count}" if count > 1 else "")
            for shape, count in sorted(tally.said.items())[:6]
        )
    return text


__all__ = [
    "Comparison",
    "FROZEN_MODIFIED",
    "MODES",
    "books_in",
    "compare",
    "differences",
    "identifier_for",
    "signature_files",
    "RUNS",
    "signature",
    "summarise",
    "workers_for",
    "CARRIES_SOURCE_DEFECTS",
    "STRANDED_SHAPES",
]
