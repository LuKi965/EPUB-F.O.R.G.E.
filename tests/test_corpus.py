"""Regression against real books, without putting anybody's book in the repository.

Synthetic fixtures confirm what we already know — they were written from the
defects we had already found. Real books are what find the next one. But they
are other people's work and this repository is public under MIT, so the books
themselves never enter it.

The split:

    tests/corpus/            real .epub files, gitignored, local only
    tests/corpus/expected/   one small JSON signature per book, committed

The signature records *measurements*, never content: how many EPUBCheck errors
the source had and the rebuild has, whether the text invariant held, the shape
of the report, and the hash of the output. That last one turns this into a hard
regression: if it changes, something changed, and the diff has to be explained.

The whole module skips itself when the corpus directory is absent, so CI and
anyone cloning the repository are unaffected.

Refreshing the signatures after an intentional change:

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

from .test_invariants import body_text

CORPUS = pathlib.Path(__file__).parent / "corpus"
EXPECTED = CORPUS / "expected"

#: Pinned so a signature is a function of the book alone, not of the day.
FROZEN_MODIFIED = "2020-01-01T00:00:00Z"


def corpus_books() -> list[pathlib.Path]:
    if not CORPUS.is_dir():
        return []
    return sorted(p for p in CORPUS.glob("*.epub") if p.is_file())


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def signature(book: pathlib.Path, destination: pathlib.Path) -> dict:
    """Everything we are willing to remember about somebody else's book."""
    policy = Policy.preset("strict", modified_override=FROZEN_MODIFIED)
    result = rebuild(str(book), str(destination), policy)

    record: dict = {
        "source": digest(book.read_bytes()),
        "written": result.output_path is not None,
        "report": {
            level.value: result.report.count(level)
            for level in Level
            if result.report.count(level)
        },
    }
    if result.output_path is None:
        return record

    record["output"] = digest(pathlib.Path(result.output_path).read_bytes())
    record["text_invariant"] = body_text(result.output_path) == body_text(str(book))
    if find_epubcheck() is not None:
        check = validate(result.output_path)
        record["epubcheck"] = {"errors": check.errors, "warnings": check.warnings,
                               "fatal": check.fatal}
    return record


def expected_for(book: pathlib.Path) -> pathlib.Path:
    return EXPECTED / f"{book.stem}.json"


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
    measured = signature(book, tmp_path / "out.epub")

    # Reported first and separately: these are the two that mean the tool got
    # worse, as opposed to merely different.
    assert measured.get("text_invariant") is not False, "the book lost readable text"
    if "epubcheck" in measured and "epubcheck" in recorded:
        assert measured["epubcheck"]["errors"] <= recorded["epubcheck"]["errors"]
        assert measured["epubcheck"]["fatal"] <= recorded["epubcheck"]["fatal"]

    assert measured == recorded, (
        f"{book.name} rebuilt differently than recorded. If the change was "
        f"intended, re-record with: python -m tests.test_corpus --record"
    )


def record() -> int:
    """Write a fresh signature for every book in the corpus."""
    import tempfile

    books = corpus_books()
    if not books:
        print(f"no books in {CORPUS}", file=sys.stderr)
        return 1
    EXPECTED.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        for book in books:
            data = signature(book, pathlib.Path(scratch) / "out.epub")
            expected_for(book).write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"recorded {book.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(record() if "--record" in sys.argv else 0)
