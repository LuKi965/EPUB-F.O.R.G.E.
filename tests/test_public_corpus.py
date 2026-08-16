"""The corpus regression, running for everybody rather than for one person.

`test_corpus.py` points the same machinery at a private shelf and skips wherever
that shelf is absent — which is everywhere except one machine. This file points
it at nine books the suite builds, so a change that alters what the rebuild
produces fails in CI for whoever made it.

Refreshing after an intentional change:

    python -m tests.test_public_corpus --record

and then reading the diff, which is printed field by field. A signature moving
without an explanation in the same commit is the thing this exists to prevent.

EPUBCheck is deliberately switched off here. The signature would otherwise
depend on whether a JVM happens to be installed, and a regression net whose
answer changes with the machine is not a net. The validator has its own tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from epubforge.validate import find_epubcheck

from epubforge.corpus import compare, summarise

from .public_corpus import BOOKS, build_all

EXPECTED = pathlib.Path(__file__).parent / "corpus_public"


@pytest.fixture
def corpus(tmp_path):
    """The books, freshly built. Byte-identical every time by construction."""
    build_all(tmp_path / "books")
    return tmp_path / "books"


@pytest.fixture(autouse=True)
def without_epubcheck(monkeypatch):
    monkeypatch.setattr("epubforge.corpus.find_epubcheck", lambda: None)


#: The recorded signatures were measured with EPUBCheck reachable, and two of
#: them record strict mode **refusing to publish** — a verdict only a validator
#: can produce. Comparing them against a run that had none compares two
#: different measurements, so this says so instead of failing.
#:
#: WP-12 removed everything else that made these signatures depend on the
#: machine: `epubcheck.*` rules, the level counts that included them, and the
#: `epubcheck`/`checker` fields. What is left is not noise — it is a book that
#: genuinely comes out differently when nothing can check it.
needs_a_validator = pytest.mark.skipif(
    find_epubcheck() is None,
    reason=(
        "sygnatury zapisano z EPUBCheck-iem; dwie z nich zapisują odmowę "
        "publikacji w trybie ścisłym, a bez walidatora nie ma jej kto wydać"
    ),
)

@needs_a_validator
def test_every_book_still_rebuilds_the_way_it_did(corpus):
    results = compare(corpus, EXPECTED)
    moved = [r for r in results if not r.ok]
    if moved:
        report = "\n".join(
            f"  {r.book} ({r.status}):\n" + "\n".join(f"    {d}" for d in r.differences)
            for r in moved
        )
        pytest.fail(
            f"{summarise(results)}\n{report}\n"
            "  If the change was intended: python -m tests.test_public_corpus --record"
        )


def test_the_corpus_covers_what_the_private_one_cannot(corpus):
    """Three of these exist because the 64-book library has no example.

    Right-to-left, Media Overlays and fixed layout are where the model is
    thinnest, and reading direction has already been lost once — in every mode,
    including the one that promises to touch nothing.
    """
    names = {path.stem for path in corpus.glob("*.epub")}
    assert {"right-to-left", "media-overlays"} <= names


def test_a_signature_exists_for_every_book(corpus):
    """A book without a recorded signature passes as 'new' and proves nothing.
    Silence here would hollow the whole file out."""
    recorded = {path.stem for path in EXPECTED.glob("*.json")}
    results = compare(corpus, EXPECTED)
    assert len(recorded) == len(BOOKS), (
        f"{len(BOOKS)} books, {len(recorded)} signatures — run --record"
    )
    assert not [r for r in results if r.status == "new"]


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        folder = pathlib.Path(tmp) / "books"
        build_all(folder)

        import epubforge.corpus as corpus_module

        corpus_module.find_epubcheck = lambda: None  # see the module docstring
        results = compare(folder, EXPECTED, record="--record" in sys.argv)

    for result in results:
        if result.status == "changed":
            print(f"  changed  {result.book}")
            for line in result.differences:
                print(f"    {line}")
        elif result.status in ("new", "failed"):
            print(f"  {result.status:8} {result.book}")
            for line in result.differences:
                print(f"    {line}")
    print("\n" + summarise(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
