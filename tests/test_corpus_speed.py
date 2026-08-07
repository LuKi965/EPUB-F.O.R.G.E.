"""What the corpus run may skip, and what it may never skip.

Ninety-three books across three modes is two hundred and seventy-nine JVM
starts, and four fifths of the wall time is EPUBCheck. Measured on an
eight-core desktop the run sat at **6% CPU**: one validation at a time, the
other fifteen threads idle, an hour to learn that nothing had changed.

Two things were done about it, and only one of them is dangerous. Measuring
books side by side cannot change an answer. Reusing a recorded verdict can, so
the conditions under which it is reused are pinned here rather than trusted.

EPUBCheck is a pure function of the jar and the bytes it reads. Both are
compared; either one moving means it runs again. The second is the one worth
testing, because an EPUBCheck upgrade is exactly when the answer is expected to
change and exactly when nobody would think to look.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge import corpus
from epubforge.corpus import (
    MODES,
    _reusable_verdict,
    checker_identity,
    compare,
    workers_for,
)
from tests.public_corpus import (
    declared_entities,
    epub2_ncx_only,
    legacy_markup,
    nav_in_spine,
    right_to_left,
    watermarked,
)

#: Five books that differ from each other. Copying one file five times would
#: give five names and one identifier — a signature is keyed by the book's
#: bytes — and a test of parallelism that measures the same book five times is
#: measuring one book.
BUILDERS = (epub2_ncx_only, nav_in_spine, right_to_left, legacy_markup, watermarked)

VERDICT = {"errors": 0, "warnings": 0, "fatal": 0}


@pytest.fixture
def shelf(tmp_path):
    """Two small books and an empty signature folder."""
    books = tmp_path / "books"
    books.mkdir()
    epub2_ncx_only(books / "a.epub")
    nav_in_spine(books / "b.epub")
    return books, tmp_path / "expected"


@pytest.fixture
def quick(monkeypatch):
    """The same run with no EPUBCheck.

    Everything about the pool — ordering, scratch isolation, worker counts — is
    independent of the validator, and each validation is five and a half seconds
    of JVM. Testing them through it would put four minutes on every suite run to
    re-measure something the tests below already pin.
    """
    monkeypatch.setattr(corpus, "find_epubcheck", lambda: None)


class TestEveryModeIsMeasured:
    def test_minimal_is_among_them(self):
        """The roadmap justifies a whole corpus family — fixed layout and
        comics — as "a test of whether minimal mode engages", and the corpus
        ran that mode on nothing at all. The family was filled for a purpose
        nothing measured."""
        assert "minimal" in MODES
        assert set(MODES) == {"minimal", "preserve", "strict"}

    def test_a_signature_carries_a_block_for_each(self, shelf, quick):
        books, expected = shelf
        compare(books, expected, record=True)
        import json

        for path in expected.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for mode in MODES:
                assert mode in record, f"{path.name} has no {mode}"


class TestAVerdictIsReusedOnlyWhenItCannotHaveChanged:
    def test_same_bytes_same_checker_is_reused(self):
        previous = {"output": "sha256:abc", "checker": checker_identity(), "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:abc") == VERDICT

    def test_different_output_is_not_reused(self):
        """The whole point of the signature: different bytes, different book,
        and nothing recorded about the old ones applies."""
        previous = {"output": "sha256:abc", "checker": checker_identity(), "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:zzz") is None

    def test_a_different_checker_is_not_reused(self):
        """An EPUBCheck upgrade is when the answer is expected to change."""
        previous = {"output": "sha256:abc", "checker": "0000000000000000", "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:abc") is None

    def test_a_signature_with_no_verdict_is_not_reused(self):
        previous = {"output": "sha256:abc", "checker": checker_identity()}
        assert _reusable_verdict(previous, "sha256:abc") is None

    def test_nothing_recorded_is_not_reused(self):
        assert _reusable_verdict(None, "sha256:abc") is None
        assert _reusable_verdict({}, "sha256:abc") is None

    def test_the_checker_identity_is_stable_within_a_process(self):
        assert checker_identity() == checker_identity()


@pytest.mark.skipif(
    corpus.find_epubcheck() is None, reason="no EPUBCheck to reuse a verdict from"
)
class TestTheReuseSurvivesARealRun:
    def test_a_second_run_agrees_with_the_first(self, shelf):
        """The speed-up is worth nothing if it changes an answer."""
        books, expected = shelf
        first = {r.identifier: r.status for r in compare(books, expected, record=True)}
        assert set(first.values()) == {"new"}
        second = compare(books, expected)
        assert {r.status for r in second} == {"unchanged"}

    def test_a_changed_book_is_still_validated(self, shelf, monkeypatch):
        """The reuse must not hide a book that started failing. Replacing one
        book's bytes changes the output digest, and the verdict is taken
        again."""
        books, expected = shelf
        compare(books, expected, record=True)

        calls = []
        real = corpus.validate

        def counted(path, *args, **kwargs):
            calls.append(path)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(corpus, "validate", counted)
        # Nothing moved: no JVM starts at all.
        compare(books, expected)
        assert calls == []

        # One book replaced by a genuinely different one — not a copy of the
        # other, which would carry the same bytes, the same identifier and the
        # same signature, and would be reused exactly as it should be.
        (books / "a.epub").unlink()
        declared_entities(books / "a.epub")
        compare(books, expected)
        assert len(calls) == len(MODES)


class TestHowManyBooksAtOnce:
    def test_a_single_book_needs_no_pool(self):
        assert workers_for(1) == 1

    def test_it_never_exceeds_the_shelf(self):
        assert workers_for(2) <= 2

    def test_it_is_capped_so_the_machine_does_not_swap(self):
        """Each JVM wants a few hundred megabytes. A machine that starts
        thirty-two at once spends the difference in swap."""
        assert workers_for(1000) <= 8

    def test_an_explicit_request_wins(self):
        assert workers_for(1000, 3) == 3

    def test_it_is_never_zero(self):
        assert workers_for(0) >= 1
        assert workers_for(1000, 0) >= 1


class TestResultsComeBackInShelfOrder:
    def test_order_does_not_depend_on_which_book_finished_first(self, shelf, quick):
        """A corpus report that shuffles itself between runs is one nobody can
        diff, and with several books in flight the finishing order is whatever
        the machine felt like."""
        books, expected = shelf
        for index, build in enumerate(BUILDERS[2:], start=3):
            build(books / f"{chr(ord('a') + index)}.epub")
        serial = [r.book for r in compare(books, expected, workers=1)]
        parallel = [r.book for r in compare(books, expected, workers=4)]
        assert serial == parallel == sorted(serial)


class TestTheScratchIsNotShared:
    def test_two_books_do_not_write_the_same_file(self, shelf, quick):
        """Every book used to build into `scratch/preserve.epub`. Measured side
        by side, two threads would each be checking a file the other had just
        overwritten — a race that produces a plausible wrong answer rather than
        a crash, which is the worst kind."""
        books, expected = shelf
        for index, build in enumerate(BUILDERS[2:], start=3):
            build(books / f"{chr(ord('a') + index)}.epub")
        one = compare(books, expected, record=True, workers=1)
        assert len({r.identifier for r in one}) == 5, "the five books are not distinct"
        many = compare(books, expected, workers=4)
        # Measured side by side, every one still matches what it recorded alone.
        assert {r.status for r in many} == {"unchanged"}, [
            (r.book, r.status, r.differences) for r in many if r.status != "unchanged"
        ]
