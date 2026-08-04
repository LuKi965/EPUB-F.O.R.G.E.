"""Regression against real books, without putting anybody's book in the repository.

Synthetic fixtures confirm what we already know — they were written from the
defects we had already found. Real books are what find the next one. But they
are other people's work and this repository is public under MIT, so the books
themselves never enter it.

The split:

    tests/corpus/            real .epub files, gitignored, local only
    tests/corpus/expected/   one small JSON signature per book, committed

The signature records *measurements*, never content: how many EPUBCheck errors
the rebuild has, whether the text invariant held, the shape of the report, and
the hash of the output. That last one turns this into a hard regression — if it
changes, something changed, and the diff has to be explained.

Two details are deliberate rather than incidental:

* **Signatures are named by hash, not by title.** A public repository listing
  `autor - Ostatnie życzenie.json` does not leak the book, but it leaks the
  library — which is the same class of information the whole arrangement exists
  to keep local. It also survives renaming the file on disk, which would
  otherwise orphan the signature silently.
* **Both `preserve` and `strict` are measured.** `preserve` is what users
  actually get; measuring only `strict` would leave the default path unwatched.

Refreshing after an intentional change:

    python -m tests.test_corpus --record
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Level
from epubforge.validate import find_epubcheck, validate

from .test_invariants import block_count, body_text

CORPUS = pathlib.Path(__file__).parent / "corpus"
EXPECTED = CORPUS / "expected"

#: Pinned so a signature is a function of the book alone, not of the day.
FROZEN_MODIFIED = "2020-01-01T00:00:00Z"

MODES = ("preserve", "strict")


def corpus_books() -> list[pathlib.Path]:
    if not CORPUS.is_dir():
        return []
    return sorted(p for p in CORPUS.glob("*.epub") if p.is_file())


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def expected_for(book: pathlib.Path) -> pathlib.Path:
    """Named by the book's hash — the signature already carries it, and a title
    in a public repository would say more about the shelf than we mean to."""
    return EXPECTED / f"{hashlib.sha256(book.read_bytes()).hexdigest()[:16]}.json"


def measure(book: pathlib.Path, destination: pathlib.Path, mode: str) -> dict:
    policy = Policy.preset(mode, modified_override=FROZEN_MODIFIED)
    result = rebuild(str(book), str(destination), policy)

    measurement: dict = {
        "written": result.output_path is not None,
        "report": {
            level.value: result.report.count(level)
            for level in Level
            if result.report.count(level)
        },
    }
    if result.output_path is None:
        return measurement

    measurement["output"] = digest(pathlib.Path(result.output_path).read_bytes())
    measurement["text_invariant"] = body_text(result.output_path) == body_text(str(book))
    # K1 is a character-stream invariant and cannot see a change in how the text
    # is divided. Recording the count gives that its own line in the diff.
    measurement["blocks"] = block_count(result.output_path)
    if find_epubcheck() is not None:
        check = validate(result.output_path)
        measurement["epubcheck"] = {
            "errors": check.errors,
            "warnings": check.warnings,
            "fatal": check.fatal,
        }
    return measurement


def signature(book: pathlib.Path, scratch: pathlib.Path) -> dict:
    """Everything we are willing to remember about somebody else's book."""
    record: dict = {"source": digest(book.read_bytes())}
    for mode in MODES:
        record[mode] = measure(book, scratch / f"{mode}.epub", mode)
    return record


def differences(recorded: dict, measured: dict, path: str = "") -> list[str]:
    """Field-level diff, so a change reads as a sentence and not as two hashes."""
    lines: list[str] = []
    for key in sorted(set(recorded) | set(measured)):
        here = f"{path}.{key}" if path else key
        old, new = recorded.get(key), measured.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            lines.extend(differences(old, new, here))
        elif old != new:
            lines.append(f"    {here}: {old!r} → {new!r}")
    return lines


pytestmark = pytest.mark.skipif(
    not corpus_books(),
    reason=f"no private corpus in {CORPUS}; see CONTRIBUTING.md",
)


@pytest.mark.parametrize("book", corpus_books(), ids=lambda p: p.stem)
def test_corpus_book_matches_its_signature(book, tmp_path):
    reference = expected_for(book)
    if not reference.is_file():
        pytest.skip(f"no signature recorded for {book.name}; run --record")

    recorded = json.loads(reference.read_text(encoding="utf-8"))
    measured = signature(book, tmp_path)

    # Checked first and separately: these are the two that mean the tool got
    # *worse*, as opposed to merely different.
    for mode in MODES:
        assert measured[mode].get("text_invariant") is not False, (
            f"{book.name} lost readable text in {mode} mode"
        )
        if "epubcheck" in measured[mode] and "epubcheck" in recorded.get(mode, {}):
            assert measured[mode]["epubcheck"]["errors"] <= recorded[mode]["epubcheck"]["errors"]
            assert measured[mode]["epubcheck"]["fatal"] <= recorded[mode]["epubcheck"]["fatal"]

    if measured != recorded:
        report = "\n".join(differences(recorded, measured))
        pytest.fail(
            f"{book.name} rebuilt differently than recorded:\n{report}\n"
            f"  If the change was intended: python -m tests.test_corpus --record"
        )


def record() -> int:
    """Write a fresh signature for every book, printing what actually changed.

    Without the diff this prints a wall of altered hashes, which says that
    something moved but not what. "12 books gained a css warning" is a review;
    "40 hashes changed" is not.
    """
    import tempfile

    books = corpus_books()
    if not books:
        print(f"no books in {CORPUS}", file=sys.stderr)
        return 1

    EXPECTED.mkdir(parents=True, exist_ok=True)
    changed = 0
    with tempfile.TemporaryDirectory() as scratch:
        for book in books:
            reference = expected_for(book)
            previous = (
                json.loads(reference.read_text(encoding="utf-8"))
                if reference.is_file()
                else None
            )
            current = signature(book, pathlib.Path(scratch))

            if previous is None:
                print(f"  new      {book.name}")
            elif previous != current:
                changed += 1
                print(f"  changed  {book.name}")
                for line in differences(previous, current):
                    print(line)
            reference.write_text(
                json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    print(f"\n{len(books)} book(s) recorded, {changed} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(record() if "--record" in sys.argv else 0)
