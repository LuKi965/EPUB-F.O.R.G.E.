"""Regression against a private corpus, when one is present.

The machinery lives in `epubforge/corpus.py` — it is a feature rather than a
fixture, because the person holding the books is not necessarily the person
holding a checkout. This file is the pytest end of it: it points the same code
at `tests/corpus/` and fails when a book rebuilds differently than recorded.

The books themselves are gitignored and never leave the machine they are on.
Only the signatures under `tests/corpus/expected/` are committed, and those are
counts and hashes.

Refreshing after an intentional change:

    python -m tests.test_corpus --record
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from epubforge.corpus import books_in, compare, summarise

CORPUS = pathlib.Path(__file__).parent / "corpus"
EXPECTED = CORPUS / "expected"


pytestmark = pytest.mark.skipif(
    not books_in(CORPUS),
    reason=f"no private corpus in {CORPUS}; see docs/KORPUS.md",
)


def test_every_corpus_book_matches_its_signature():
    results = compare(CORPUS, EXPECTED)
    changed = [r for r in results if not r.ok]
    if changed:
        report = "\n".join(
            f"  {r.book} ({r.status}):\n" + "\n".join(f"    {d}" for d in r.differences)
            for r in changed
        )
        pytest.fail(
            f"{summarise(results)}\n{report}\n"
            "  If the change was intended: python -m tests.test_corpus --record"
        )


def main() -> int:
    if not books_in(CORPUS):
        print(f"no books in {CORPUS}", file=sys.stderr)
        return 1

    def announce(index: int, name: str) -> None:
        print(f"  [{index + 1}] {name}", file=sys.stderr)

    results = compare(CORPUS, EXPECTED, record="--record" in sys.argv, on_book=announce)
    for result in results:
        if result.status == "changed":
            print(f"  changed  {result.book}")
            for line in result.differences:
                print(f"    {line}")
        elif result.status in ("new", "failed"):
            print(f"  {result.status:8} {result.book}")
    print("\n" + summarise(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
