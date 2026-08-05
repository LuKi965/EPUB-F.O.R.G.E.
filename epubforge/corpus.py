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
from collections import Counter
from dataclasses import dataclass, field

from .pipeline import rebuild
from .policy import Policy
from .report import Level
from .validate import find_epubcheck, validate

#: Pinned, so a signature is a function of the book and not of the day it ran.
FROZEN_MODIFIED = "2020-01-01T00:00:00Z"

#: Both modes are measured. `preserve` is what people actually get, and
#: measuring only `strict` would leave the default path unwatched.
MODES = ("preserve", "strict")


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

    def normalise(text: str) -> str:
        return " ".join(text.split())

    try:
        source = normalise(spine_text(before))
        result = normalise(spine_text(after))
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


def _measure(book: pathlib.Path, destination: pathlib.Path, mode: str) -> dict:
    from .inventory import measure as inventory_measure  # local: avoids a cycle

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

    before = inventory_measure(book).fields
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
    measurement["text_added"] = after.get("spine_text_characters", 0) - before.get(
        "spine_text_characters", 0
    )
    measurement["text_invariant"] = _text_survived(book, output)
    # K1 compares a stream of characters and cannot see two paragraphs merged
    # into one. Recording the count gives that change its own line in the diff.
    measurement["blocks"] = after.get("blocks", 0)

    if find_epubcheck() is not None:
        check = validate(result.output_path)
        measurement["epubcheck"] = {
            "errors": check.errors,
            "warnings": check.warnings,
            "fatal": check.fatal,
        }
    return measurement


def signature(book: pathlib.Path, scratch: pathlib.Path) -> dict:
    record: dict = {"source": digest(book.read_bytes())}
    for mode in MODES:
        record[mode] = _measure(book, scratch / f"{mode}.epub", mode)
    return record


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


def differences(recorded: dict, measured: dict, path: str = "") -> list[str]:
    """Field-level diff, so a change reads as a sentence and not as two hashes."""
    lines: list[str] = []
    for key in sorted(set(recorded) | set(measured)):
        here = f"{path}.{key}" if path else key
        old, new = recorded.get(key), measured.get(key)
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


def compare(
    books: pathlib.Path,
    signatures: pathlib.Path,
    *,
    record: bool = False,
    on_book=None,
) -> list[Comparison]:
    """Check every book against its signature, optionally rewriting them.

    With ``record`` off this is a regression test. With it on, it is how a
    deliberate change gets accepted — and it still reports what moved, because
    "40 hashes changed" is not something anybody can review.
    """
    import tempfile

    signatures.mkdir(parents=True, exist_ok=True)
    results: list[Comparison] = []

    with tempfile.TemporaryDirectory(prefix="epubforge-corpus-") as scratch:
        for index, book in enumerate(books_in(books)):
            # Relative to the corpus root: two shelves may hold a file of the
            # same name, and "changed: ksiazka.epub" would then be ambiguous.
            label = str(book.relative_to(books)) if book.is_relative_to(books) else book.name
            if on_book is not None:
                on_book(index, label)

            identifier = identifier_for(book)
            reference = signatures / f"{identifier}.json"
            previous = (
                json.loads(reference.read_text(encoding="utf-8"))
                if reference.is_file()
                else None
            )

            try:
                current = signature(book, pathlib.Path(scratch))
            except Exception as exc:  # noqa: BLE001 — one bad book is a finding
                results.append(
                    Comparison(label, identifier, "failed", [f"{type(exc).__name__}: {exc}"])
                )
                continue

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
            results.append(Comparison(label, identifier, status, changes))
    return results


def summarise(results: list[Comparison]) -> str:
    counts = {status: 0 for status in ("new", "unchanged", "changed", "failed")}
    for result in results:
        counts[result.status] += 1
    return (
        f"{len(results)} book(s): {counts['unchanged']} unchanged, "
        f"{counts['changed']} changed, {counts['new']} new, {counts['failed']} failed"
    )


__all__ = [
    "Comparison",
    "FROZEN_MODIFIED",
    "MODES",
    "books_in",
    "compare",
    "differences",
    "identifier_for",
    "signature",
    "summarise",
]
