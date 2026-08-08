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
from collections import Counter
from dataclasses import dataclass, field

from .pipeline import rebuild
from .policy import Policy
from .report import Level
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


@dataclass
class Comparison:
    """What changed for one book between the recorded run and this one."""

    book: str
    identifier: str
    status: str  # "new" | "unchanged" | "changed" | "failed"
    differences: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("new", "unchanged")


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
    from .inventory import spine_text

    try:
        return _survives(" ".join(spine_text(before).split()), after)
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
    from .inventory import spine_text

    try:
        source = source_text
        result = " ".join(spine_text(after).split())
    except Exception:  # noqa: BLE001 — an unreadable book is reported elsewhere
        return False

    # Subsequence rather than substring: the rebuild may insert text between
    # documents (a generated cover page) without having lost any.
    position = 0
    for character in source:
        position = result.find(character, position)
        if position < 0:
            return False
        position += 1
    return True


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
    from .inventory import measure as inventory_measure, spine_text

    try:
        characters = inventory_measure(book).fields.get("spine_text_characters", 0)
        text = " ".join(spine_text(book).split())
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
    policy = Policy.preset(mode, modified_override=FROZEN_MODIFIED)
    result = rebuild(str(book), str(destination), policy)

    # Counters by level say a book gained three fixes. Counters by rule say
    # *which* three, so a signature that moves reads as "this book stopped
    # losing its contents page" rather than as "a number went up" — which is
    # the difference between a regression net and a tripwire (EF-018).
    rules: Counter = Counter(f.rule for f in result.report.findings if f.rule)

    measurement: dict = {
        "written": result.output_path is not None,
        "report": {
            level.value: result.report.count(level)
            for level in Level
            if result.report.count(level)
        },
        "rules": dict(sorted(rules.items())),
    }
    if result.output_path is None:
        return measurement

    output = pathlib.Path(result.output_path)
    measurement["output"] = digest(output.read_bytes())

    after = inventory_measure(output).fields
    # Spine text only. The rebuild generates a navigation document when the
    # source had none, and its chapter titles are text — counting them made
    # every EPUB 2 book in a corpus report that its text had changed, which is
    # the one thing this field exists to be believed about.
    #
    # K1 is "no character is lost", not "no character is added", and the two
    # are not the same rule. Comparing the counts for equality made this field
    # false for every book that arrives without a cover page in its spine,
    # because generating one adds two characters — a deliberate, documented
    # improvement reported as a broken invariant. The six Project Gutenberg
    # books added to the corpus were false on all six for that reason alone.
    #
    # Counting is not enough to say K1 holds: two books can carry the same
    # number of characters and not the same characters. So the source's spine
    # text has to still be *in* the output's, in order, and the count is kept
    # beside it as a number a human can read.
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
            check = validate(result.output_path)
            measurement["epubcheck"] = {
                "errors": check.errors,
                "warnings": check.warnings,
                "fatal": check.fatal,
            }
    return measurement


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

    # A directory of this book's own. Books are measured side by side now, and
    # two threads writing `scratch/preserve.epub` would each be checking a file
    # the other had just overwritten — a race that produces a plausible wrong
    # answer rather than a crash, which is the worst kind to introduce.
    room = scratch / identifier_for(book)
    room.mkdir(parents=True, exist_ok=True)

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
        if recorded is None:
            check = validate(str(book))
            recorded = {
                "errors": check.errors,
                "warnings": check.warnings,
                "fatal": check.fatal,
            }
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


def green_streak(history: "list[dict]", *, minimum: int = 1) -> "list[str]":
    """The run of consecutive releases that came out clean, most recent last.

    Read from the run ledger rather than from the signatures: a signature keeps
    a book's latest measurement only, so re-measuring a book erases the release
    it was green on before. History is the question being asked here.

    *minimum* is how many books a run must cover to count at all. A run over
    three books says nothing about a corpus of eighty-six, and letting it extend
    a streak would be the same mistake as counting books instead of families.
    """
    streak: list[str] = []
    for entry in history:
        if entry.get("books", 0) < minimum:
            continue
        if entry.get("clean"):
            if not streak or streak[-1] != entry.get("version"):
                streak.append(entry.get("version", "?"))
        else:
            streak = []
    return streak


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
        # A mode the recorded signature never held. Adding `minimal` made every
        # book in the corpus report the whole block as a difference — ninety
        # lines each, ninety-three times, for a change in what is measured
        # rather than in how a book rebuilds. There is nothing to compare
        # against, so say that and say it once.
        if not path and (key in MODES or key == "source_epubcheck") and old is None and new is not None:
            lines.append(f"{here}: not measured before")
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
    """
    import concurrent.futures
    import tempfile
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

    def measure_one(book: pathlib.Path, scratch: str) -> Comparison:
        nonlocal done
        label = label_for(book)
        identifier = identifier_for(book)
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
                status = "unchanged" if not changes else "changed"
            if record:
                reference.write_text(
                    json.dumps(current, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            outcome = Comparison(label, identifier, status, changes)

        # Reported on completion rather than on start: with several books in
        # flight, "starting number 40" while 33 to 39 are still running is a
        # progress bar that lies about how much is left.
        if on_book is not None:
            with progress_lock:
                done += 1
                on_book(done - 1, label)
        return outcome

    with tempfile.TemporaryDirectory(prefix="epubforge-corpus-") as scratch:
        count = workers_for(len(shelf), workers)
        if count == 1:
            results = [measure_one(book, scratch) for book in shelf]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                results = list(pool.map(lambda b: measure_one(b, scratch), shelf))

    if record:
        _log_run(signatures, results)
    return results


#: One entry per corpus run, in the folder *containing* the signatures.
#:
#: Not among them. That folder means "one file per book", and anything else
#: living there is a trap for every loop that reads it — the owner's inventory
#: landed there once by accident and broke the analysis on the spot.
RUNS = "runs.json"


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
        "failed": sum(1 for r in results if r.status == "failed"),
    }
    errors = introduced = carried = fatal = lost = unwritten = 0
    for result in results:
        record_path = signatures / f"{result.identifier}.json"
        if not record_path.is_file():
            continue
        measured = json.loads(record_path.read_text(encoding="utf-8"))
        source = (measured.get("source_epubcheck") or {}).get("errors", 0)
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
                introduced += max(0, count - source)
                carried += min(count, source)
            else:
                errors += count
            if not found.get("text_invariant", True):
                lost += 1
    entry.update(
        errors=errors,
        introduced=introduced,
        carried=carried,
        fatal=fatal,
        text_lost=lost,
        unwritten=unwritten,
    )
    entry["clean"] = not (
        errors or introduced or fatal or lost or unwritten or entry["failed"]
    )

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
    counts = {status: 0 for status in ("new", "unchanged", "changed", "failed")}
    for result in results:
        counts[result.status] += 1
    line = (
        f"{len(results)} book(s): {counts['unchanged']} unchanged, "
        f"{counts['changed']} changed, {counts['new']} new, {counts['failed']} failed"
    )
    if signatures is None:
        return line

    errors = introduced = carried = 0
    for result in results:
        path = signatures / f"{result.identifier}.json"
        if not path.is_file():
            continue
        measured = json.loads(path.read_text(encoding="utf-8"))
        source = (measured.get("source_epubcheck") or {}).get("errors", 0)
        for mode in MODES:
            count = ((measured.get(mode) or {}).get("epubcheck") or {}).get("errors", 0)
            if mode in CARRIES_SOURCE_DEFECTS:
                introduced += max(0, count - source)
                carried += min(count, source)
            else:
                errors += count
    if not (errors or introduced or carried):
        return line
    parts = [f"{errors} EPUBCheck error(s) in modes that rewrite content"]
    if carried:
        parts.append(f"{carried} source error(s) carried through by container-only mode")
    if introduced:
        parts.append(f"{introduced} introduced by it")
    return line + "\n" + "; ".join(parts) + "."


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
]
