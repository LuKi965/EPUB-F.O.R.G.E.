"""The corpus milestone has a definition of done, and this is it.

`docs/ROADMAP.md` point 1 does not ask for "thirty books". It asks for books
**chosen by provenance** — ten families, with a count each — because what a
book was made by decides what is wrong with it, and a hundred files from one
generator teach less than ten from ten.

Sixty-four books were collected and nothing ever checked which families they
belonged to, so the milestone was called finished on the only number anyone had
counted. The roadmap even names a family it knows is missing. This file makes
the gap measurable instead of remembered.
"""

from __future__ import annotations

import pathlib

import pytest

from epubforge.inventory import (
    CORPUS_FAMILIES,
    Book,
    coverage,
    coverage_report,
    families,
    measure,
)


def book(**fields) -> Book:
    base = {
        "generators": [],
        "watermarked": False,
        "language": "en",
        "version": "3.0",
        "fixed_layout": False,
        "has_cover": True,
        "spine_items": 20,
        "largest_image_mb": 0.2,
        "documents": 20,
    }
    entry = Book("0" * 16, 1.0)
    entry.fields.update(base | fields)
    return entry


class TestAFamilyIsWhatTheBookWasMadeBy:
    @pytest.mark.parametrize(
        "fields, expected",
        [
            ({"generators": ["calibre"]}, "calibre"),
            ({"generators": ["indesign"]}, "indesign-vellum"),
            ({"generators": ["vellum"]}, "indesign-vellum"),
            ({"generators": ["word"]}, "word"),
            ({"generators": ["pdf-or-ocr"]}, "pdf-or-ocr"),
            ({"generators": ["from-mobi"]}, "from-mobi"),
            ({"generators": ["gutenberg"]}, "public-domain"),
            ({"version": "2.0"}, "epub2"),
            ({"fixed_layout": True}, "fixed-layout"),
            ({"watermarked": True, "language": "pl"}, "polish-bookshop"),
        ],
    )
    def test_each_family_is_recognised(self, fields, expected):
        assert expected in families(book(**fields).fields)

    def test_a_layered_file_counts_towards_every_family_it_belongs_to(self):
        """Exported from InDesign, converted by Calibre. Both are true, and
        picking one would undercount both."""
        found = families(book(generators=["indesign", "calibre"]).fields)
        assert {"indesign-vellum", "calibre"} <= found

    def test_gutenberg_is_not_a_polish_bookshop(self):
        """Its licence page reads as a purchase notice to the watermark
        detector, and nobody bought that book."""
        found = families(book(generators=["gutenberg"], watermarked=True, language="pl").fields)
        assert "polish-bookshop" not in found
        assert "public-domain" in found

    @pytest.mark.parametrize(
        "fields",
        [
            {"has_cover": False},
            {"spine_items": 400},
            {"largest_image_mb": 8.0},
            {"documents": 1},
        ],
    )
    def test_the_edges_are_their_own_family(self, fields):
        """Memory and performance failures surface here and nowhere else."""
        assert "pathological" in families(book(**fields).fields)

    def test_an_unreadable_book_belongs_to_nothing(self):
        entry = Book("0" * 16, 1.0)
        entry.fields["error"] = "not an EPUB"
        assert families(entry.fields) == set()


class TestTheGapIsCountedNotRemembered:
    def test_every_roadmap_family_is_reported_even_at_zero(self):
        """A family with no books is the one worth seeing, so it cannot be
        omitted for having nothing to show."""
        rows = coverage([book(generators=["calibre"])])
        assert set(rows) == set(CORPUS_FAMILIES)
        assert rows["pdf-or-ocr"] == {
            "have": 0,
            "want": 3,
            "short": 3,
            "what": CORPUS_FAMILIES["pdf-or-ocr"][1],
        }

    def test_a_surplus_is_not_a_shortfall(self):
        rows = coverage([book(generators=["gutenberg"]) for _ in range(9)])
        assert rows["public-domain"]["have"] == 9
        assert rows["public-domain"]["short"] == 0

    def test_the_report_names_what_to_go_and_find(self):
        text = coverage_report([book(generators=["calibre"])])
        assert "pdf-or-ocr" in text
        assert "families short" in text

    def test_a_complete_corpus_says_so(self):
        books = []
        for name, (want, _) in CORPUS_FAMILIES.items():
            trait = {
                "polish-bookshop": {"watermarked": True, "language": "pl"},
                "indesign-vellum": {"generators": ["indesign"]},
                "calibre": {"generators": ["calibre"]},
                "word": {"generators": ["word"]},
                "pdf-or-ocr": {"generators": ["pdf-or-ocr"]},
                "from-mobi": {"generators": ["from-mobi"]},
                "epub2": {"version": "2.0"},
                "fixed-layout": {"fixed_layout": True},
                "pathological": {"has_cover": False},
                "public-domain": {"generators": ["gutenberg"]},
            }[name]
            books += [book(**trait) for _ in range(want)]
        assert "every family is represented" in coverage_report(books)


class TestTheCommittedCorpusIsMeasuredForReal:
    """Not a mock: the six Gutenberg books are in the repository, so the one
    family we can check without the owner's disk gets checked."""

    def test_the_public_books_are_recognised_as_public_domain(self):
        folder = pathlib.Path(__file__).parent / "corpus_gutenberg"
        books = [measure(path) for path in sorted(folder.glob("*.epub"))]
        assert books
        rows = coverage(books)
        assert rows["public-domain"]["have"] == len(books)
        assert rows["public-domain"]["short"] == 0

    def test_they_do_not_pretend_to_be_the_other_families(self):
        """Six books cannot close a ten-family corpus, and a check that said
        otherwise would be worse than none."""
        folder = pathlib.Path(__file__).parent / "corpus_gutenberg"
        rows = coverage([measure(path) for path in sorted(folder.glob("*.epub"))])
        short = [name for name, row in rows.items() if row["short"]]
        assert "pdf-or-ocr" in short
        assert len(short) >= 8
