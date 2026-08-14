"""The corpus machinery itself, on books the suite can make.

`test_corpus.py` runs the same code against somebody's real library and skips
when there is none — which is everywhere except one machine. That left the
machinery it depends on with no test at all, and both defects pinned here were
found by a person running it on a real shelf rather than by this suite.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge.corpus import books_in, compare, signature, summarise

from .factory import make_legacy_epub, make_modern_epub


@pytest.fixture(autouse=True)
def without_epubcheck(monkeypatch):
    """Signatures record what EPUBCheck said, and asking it costs a JVM start
    per book per mode. Nothing here is about the validator — `test_epubcheck.py`
    is — and a suite nobody waits for is a suite nobody runs."""
    monkeypatch.setattr("epubforge.corpus.find_epubcheck", lambda: None)


def shelf(root: pathlib.Path) -> pathlib.Path:
    """A library filed the way people file libraries: in folders."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "Autor").mkdir()
    (root / "Autor" / "Cykl").mkdir()
    make_modern_epub(str(root / "na wierzchu.epub"), title="Pierwsza")
    make_modern_epub(str(root / "Autor" / "druga.epub"), title="Druga")
    make_legacy_epub(str(root / "Autor" / "Cykl" / "trzecia.epub"))
    return root


class TestFindingTheBooks:
    def test_subfolders_are_searched(self, tmp_path):
        """It read the top level only, and reported success on 1 of 3 books."""
        assert len(books_in(shelf(tmp_path / "lib"))) == 3

    def test_a_folder_with_no_books_is_not_an_error(self, tmp_path):
        empty = tmp_path / "pusto"
        empty.mkdir()
        assert books_in(empty) == []

    def test_a_missing_folder_is_not_an_error(self, tmp_path):
        assert books_in(tmp_path / "nie ma") == []

    def test_books_are_labelled_by_where_they_sit(self, tmp_path):
        """Two shelves may hold the same filename; the bare name would lie."""
        results = compare(shelf(tmp_path / "lib"), tmp_path / "sig", record=True)
        labels = {result.book for result in results}
        assert str(pathlib.Path("Autor/druga.epub")) in labels


class TestTheTextInvariantMeansWhatItSays:
    """A real signature came back `text_invariant: false` on a book whose text
    was untouched.

    The rebuild generates the navigation document EPUB 3 requires, and that
    document is a list of chapter titles — text, by any measure that counts
    characters in content documents. Comparing the totals therefore reported
    the table of contents as text that had appeared from nowhere, on every
    EPUB 2 book anybody owns. A field that cries wolf on the majority of a
    corpus is worse than no field.
    """

    def test_generating_a_table_of_contents_is_not_a_change_to_the_text(self, tmp_path):
        book = pathlib.Path(make_legacy_epub(str(tmp_path / "stara.epub")))
        record = signature(book, tmp_path)
        assert record["preserve"]["written"]
        assert record["preserve"]["text_invariant"], record["preserve"]
        # This assertion was suspended for one release. The publication gate
        # arrived in 0.2.23 and strict stopped publishing this fixture: the
        # stylesheet points at `Fonts/moja.ttf`, the source has no such file,
        # and EPUB 3 calls that an error where EPUB 2 did not. Strict could
        # neutralise a dead reference in a document and not in a stylesheet, so
        # it could not make the book conformant. F-017 closed that, strict
        # publishes it again, and the question this test was written to ask is
        # answerable again.
        assert record["strict"]["written"]
        assert record["strict"]["text_invariant"]
        assert record["minimal"]["text_invariant"], record["minimal"]

    def test_the_recorded_count_is_the_reader_s_text(self, tmp_path):
        from epubforge.inventory import measure

        book = pathlib.Path(make_legacy_epub(str(tmp_path / "stara.epub")))
        record = signature(book, tmp_path)
        assert record["preserve"]["text_characters"] == measure(book).fields[
            "spine_text_characters"
        ]


class TestComparing:
    def test_a_first_run_records_and_a_second_agrees(self, tmp_path):
        books = shelf(tmp_path / "lib")
        signatures = tmp_path / "sig"

        first = compare(books, signatures, record=True)
        assert all(result.status == "new" for result in first)

        second = compare(books, signatures)
        assert all(result.status == "unchanged" for result in second), [
            (r.book, r.differences) for r in second
        ]
        assert "3 unchanged" in summarise(second)

    def test_a_changed_signature_is_reported_field_by_field(self, tmp_path):
        import json

        books = shelf(tmp_path / "lib")
        signatures = tmp_path / "sig"
        compare(books, signatures, record=True)

        reference = next(signatures.glob("*.json"))
        recorded = json.loads(reference.read_text(encoding="utf-8"))
        recorded["preserve"]["blocks"] = 999_999
        reference.write_text(json.dumps(recorded), encoding="utf-8")

        changed = [r for r in compare(books, signatures) if r.status == "changed"]
        assert len(changed) == 1
        assert any("blocks" in line for line in changed[0].differences)

    def test_the_same_book_filed_twice_keeps_one_signature(self, tmp_path):
        """Signatures are named by content, so a duplicate is not a new book —
        which is the right answer for a library that has one."""
        books = tmp_path / "lib"
        (books / "A").mkdir(parents=True)
        (books / "B").mkdir()
        make_modern_epub(str(books / "A" / "ta sama.epub"), title="Ta sama")
        make_modern_epub(str(books / "B" / "ta sama.epub"), title="Ta sama")

        signatures = tmp_path / "sig"
        compare(books, signatures, record=True)
        assert len(list(signatures.glob("*.json"))) == 1

    def test_the_copy_is_named_as_a_copy_and_not_measured_again(self, tmp_path, monkeypatch):
        """Measuring identical bytes twice cannot say anything the first did not,
        and cost four books on a real shelf: both copies were handed the same
        working directory, and on Windows one replaced a file the other still
        had open. Four `PermissionError`s, and on Linux the same race is silent.
        """
        from epubforge import corpus

        books = tmp_path / "lib"
        (books / "A").mkdir(parents=True)
        (books / "B").mkdir()
        make_modern_epub(str(books / "A" / "ta sama.epub"), title="Ta sama")
        make_modern_epub(str(books / "B" / "ta sama.epub"), title="Ta sama")

        taken = []
        real = corpus.signature
        monkeypatch.setattr(
            corpus, "signature",
            lambda book, scratch, previous=None: (taken.append(book), real(book, scratch, previous))[1],
        )
        results = compare(books, tmp_path / "sig", record=True)

        assert len(taken) == 1
        assert len(results) == 2, "the shelf holds two files and the report says so"
        copy = next(r for r in results if r.status == "duplicate")
        assert copy.ok, "a shelf with a duplicate on it is not a failing shelf"
        assert "ta sama.epub" in copy.differences[0]

    def test_a_book_filed_twice_is_counted_once_in_the_ledger(self, tmp_path):
        """`books` counts files, every other total counts books.

        The owner's second shelf holds four exact duplicates and its ledger read
        129 carried errors where the signatures hold 122: each total was read out
        of `{identifier}.json`, once per result rather than once per book.
        """
        import json

        from epubforge.corpus import Comparison, _log_run

        signatures = tmp_path / "sig"
        signatures.mkdir()
        (signatures / ("a" * 16 + ".json")).write_text(json.dumps({
            "source_epubcheck": {"errors": 0, "codes": {}},
            "minimal": {"written": True, "epubcheck": {"errors": 0, "codes": {}}},
            "preserve": {"written": True, "epubcheck": {"errors": 7, "codes": {"RSC-005": 7}}},
            "strict": {"written": True, "epubcheck": {"errors": 0, "codes": {}}},
        }), encoding="utf-8")
        twice = [
            Comparison("A/ta sama.epub", "a" * 16, "unchanged"),
            Comparison("B/ta sama.epub", "a" * 16, "duplicate"),
        ]

        _log_run(signatures, twice)
        entry = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))[-1]
        assert entry["books"] == 2
        assert entry["duplicates"] == 1
        assert entry["errors"] == 7, "seven errors in one book, not fourteen in two"
        assert entry["codes"] == {"RSC-005": 7}

    def test_nothing_is_written_next_to_the_books(self, tmp_path):
        books = shelf(tmp_path / "lib")
        before = {p for p in books.rglob("*")}
        compare(books, tmp_path / "sig", record=True)
        assert {p for p in books.rglob("*")} == before


class TestTheLedgerAndTheReportBlameTheSameThings:
    """0.2.18 fixed a summary line that added every code it saw under a heading
    reading "Ours". The ledger's `codes` field was doing the same and was not
    fixed with it, so the two disagreed about whose fault a defect was — on the
    mixed shelf, by 34 `RSC-005` against 9.
    """

    def shelf(self, tmp_path) -> "tuple":
        import json

        from epubforge.corpus import Comparison

        signatures = tmp_path / "sig"
        signatures.mkdir()
        (signatures / ("b" * 16 + ".json")).write_text(json.dumps({
            "source_epubcheck": {"errors": 5, "codes": {"RSC-005": 5}},
            "minimal": {"written": True, "epubcheck": {"errors": 5, "codes": {"RSC-005": 5}}},
            # Five carried from the book, one the rebuild really did add.
            "preserve": {"written": True, "epubcheck": {"errors": 6, "codes": {"RSC-005": 6}}},
            "strict": {"written": True, "epubcheck": {"errors": 0, "codes": {}}},
        }), encoding="utf-8")
        return signatures, [Comparison("ksiazka.epub", "b" * 16, "changed")]

    def test_the_ledger_counts_only_what_the_source_did_not_have(self, tmp_path):
        import json

        from epubforge.corpus import _log_run

        signatures, results = self.shelf(tmp_path)
        _log_run(signatures, results)
        entry = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))[-1]
        assert entry["codes"] == {"RSC-005": 1}, "five of the six are the book's own"

    def test_the_report_says_the_same_number(self, tmp_path):
        from epubforge.corpus import summarise

        signatures, results = self.shelf(tmp_path)
        assert "RSC-005" in summarise(results, signatures)
        assert "RSC-005 ×6" not in summarise(results, signatures)
