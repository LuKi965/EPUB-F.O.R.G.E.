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
    PDF_HYPHEN_FLOOR,
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
        "broken_hyphens": 0,
        "legal_page": False,
        "image_pages": 0,
        "spine_documents": 20,
        "spine_text_characters": 200_000,
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
            ({"legal_page": True, "language": "pl"}, "polish-bookshop"),
        ],
    )
    def test_each_family_is_recognised(self, fields, expected):
        assert expected in families(book(**fields).fields)

    def test_a_layered_file_counts_towards_every_family_it_belongs_to(self):
        """Exported from InDesign, converted by Calibre. Both are true, and
        picking one would undercount both."""
        found = families(book(generators=["indesign", "calibre"]).fields)
        assert {"indesign-vellum", "calibre"} <= found

    def test_a_pdf_conversion_is_recognised_by_its_damage(self):
        """The generator signatures look for ABBYY, pdftohtml and `ft0` class
        names — three specific tools. A conversion done by a language model
        leaves none of them, and the file that started the InkBOOK case is
        exactly that: no generator trace at all, and hyphens frozen where a PDF
        line used to end. The family the roadmap calls the worst case for
        typography was the one the detector could not see."""
        assert "pdf-or-ocr" in families(book(broken_hyphens=16).fields)
        assert "pdf-or-ocr" in families(book(generators=["pdf-or-ocr"]).fields)

    def test_a_stray_hyphen_is_not_a_pdf(self):
        """Nine properly typeset books score exactly zero, so the floor has
        room. A false positive here says a family is covered when it is not,
        which is worse than saying nothing."""
        assert "pdf-or-ocr" not in families(book(broken_hyphens=0).fields)
        assert "pdf-or-ocr" not in families(book(broken_hyphens=PDF_HYPHEN_FLOOR - 1).fields)

    def test_the_legal_page_counts_as_well_as_the_watermark(self):
        """The roadmap names both — "znak wodny, strony prawne" — and only the
        watermark was implemented. On the owner's shelf that found 4 books out
        of 32 that were plainly bought, and a coverage number saying a family
        is empty when it is nearly full sends somebody out to buy books they
        already own."""
        assert "polish-bookshop" in families(book(legal_page=True, language="pl").fields)
        assert "polish-bookshop" not in families(book(language="pl").fields)

    def test_a_book_in_another_language_is_not_a_polish_bookshop(self):
        assert "polish-bookshop" not in families(book(legal_page=True, language="en").fields)

    def test_gutenberg_is_not_a_polish_bookshop(self):
        """Its licence page reads as a purchase notice to the watermark
        detector, and nobody bought that book."""
        found = families(
            book(generators=["gutenberg"], watermarked=True, legal_page=True, language="pl").fields
        )
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

    def test_a_comic_is_recognised_by_what_it_holds(self):
        """A CBZ converted by Calibre declares nothing about layout: EPUB 2,
        reflowable, one `<img>` per document. Three comics on the owner's disk
        counted as zero because `fixed_layout` reads the declaration, and the
        declaration was never made."""
        found = families(
            book(image_pages=5, spine_documents=5, spine_text_characters=9).fields
        )
        assert "fixed-layout" in found

    def test_an_illustrated_novel_is_not_a_comic(self):
        """The rule tried first counted image pages as a share of the spine, and
        called Pan Tadeusz a comic: that edition packs its whole text into three
        documents and its engraved plates into three more, which is 50%. What
        separates the two is that a comic has no prose in it at all."""
        found = families(
            book(image_pages=3, spine_documents=6, spine_text_characters=232_075).fields
        )
        assert "fixed-layout" not in found

    def test_a_cover_alone_does_not_make_a_picture_book(self):
        """Every ordinary book has exactly one image-only page, and it is the
        cover. A two-page pamphlet must not trip the floor."""
        found = families(
            book(image_pages=1, spine_documents=2, spine_text_characters=20).fields
        )
        assert "fixed-layout" not in found

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
                "polish-bookshop": {"legal_page": True, "language": "pl"},
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


class TestTheToolsThatLeaveNoNameBehind:
    """Two conversions the signatures could not see, and what gives them away.

    Seventeen files were made specifically to fill six empty families, and seven
    of them landed nowhere: the detector had no pattern for what made them. That
    is a fault in the measurement, not in the effort — a coverage number that
    reads zero for a family somebody has just filled sends them out to do the
    work twice.
    """

    def test_calibres_pdf_input_says_so_in_a_meta_element(self):
        """It rewrites pdftohtml's class names to its own, so `ft0` is gone —
        but it writes `PDF Reflow conversion` into every document it produces,
        and names the pictures it lifts `index-<page>_<n>`."""
        from epubforge.inventory import GENERATOR_SIGNATURES
        import re

        patterns = GENERATOR_SIGNATURES["pdf-or-ocr"]
        for material in (
            '<meta content="PDF Reflow conversion" name="generator"/>',
            '<item id="id7" href="index-1_1.jpg" media-type="image/jpeg"/>',
        ):
            assert any(re.search(p, material) for p in patterns), material

    def test_google_docs_numbers_its_lists_with_its_own_editors_name(self):
        """`kix` is what Google calls the editor inside Docs. The roadmap puts
        Word and Google Docs in one family; only Word had any patterns."""
        from epubforge.inventory import GENERATOR_SIGNATURES
        import re

        patterns = GENERATOR_SIGNATURES["word"]
        for material in (
            "ol.lst-kix_list_7-0{list-style-type:none}",
            "@import url(https://themes.googleusercontent.com/fonts/css?kit=abc);",
            '<span id="docs-internal-guid-1234">',
            "<p class=MsoNormal>",
        ):
            assert any(re.search(p, material) for p in patterns), material


class TestTheInventoryAndThePipelineAgreeOnAWatermark:
    """They did not, and the disagreement was invisible until a real shelf.

    The inventory looked for a visible notice and recorded the answer in a
    field called `watermarked`. Against 32 books bought from Polish shops it
    said "yes" about **four** — while the pipeline, on the very same books,
    found and consolidated a marker in **29**. Polish shops watermark with an
    opaque token hidden by an inline style, not with a sentence, and the
    inventory could not see the kind of watermark that is actually used.

    Two implementations of one idea, and the shorter one was wrong. There is
    one now, in `watermark.py`, and this holds them to it.
    """

    @staticmethod
    def _pipeline_markers(path) -> int:
        import tempfile

        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        with tempfile.TemporaryDirectory() as tmp:
            report = rebuild(str(path), f"{tmp}/out.epub", Policy.preset("preserve")).report
        for finding in report.findings:
            if finding.rule == "xhtml.watermark-consolidated":
                return finding.values.get("count", 0)
        return 0

    def test_a_marker_the_pipeline_consolidates_is_a_marker_the_inventory_counts(self):
        """The check that would have caught it: run both over one book and
        compare. Any book carrying markers will do — the fixture carries some
        by construction."""
        import pathlib
        import tempfile

        from tests.public_corpus import build_all

        with tempfile.TemporaryDirectory() as tmp:
            books = build_all(pathlib.Path(tmp))
            watermarked = [
                book for book in books
                if measure(book).fields["watermark_markers"] or self._pipeline_markers(book)
            ]
            assert watermarked, "no fixture carries a watermark marker any more"
            for book in watermarked:
                counted = measure(book).fields["watermark_markers"]
                consolidated = self._pipeline_markers(book)
                assert counted >= consolidated, (book.name, counted, consolidated)

    def test_a_hidden_marker_counts_even_with_no_notice_anywhere(self):
        """The exact case the old detector missed: a token, hidden by an inline
        style, and not one readable sentence in the book."""
        from epubforge import watermark

        markup = '<p style="font-size:0">a1b2c3d4e5f6g7h8</p>'
        assert watermark.marks(markup) == (0, 1)

    def test_a_readable_notice_counts_wherever_it_sits(self):
        """Styled or not — a notice is defined by what it says."""
        from epubforge import watermark

        plain = "<p>Kopia dla: jan@example.com</p>"
        styled = '<p style="font-size:0">Kopia dla: jan@example.com</p>'
        assert watermark.marks(plain)[0] == 1
        # Styled, but a sentence the buyer is meant to read is never a token.
        assert watermark.marks(styled) == (1, 0)

    def test_ordinary_prose_is_neither(self):
        from epubforge import watermark

        assert watermark.marks("<p>Rozdział pierwszy, w którym nic się nie dzieje.</p>") == (0, 0)


class TestASignatureSaysWhenItWasTaken:
    """Entry into alpha asks for the corpus to be green "across three
    consecutive releases". A signature that does not say which release measured
    it can only answer that from memory — and memory is what got the family
    count wrong.
    """

    def test_the_release_is_recorded(self, tmp_path):
        import pathlib

        from epubforge import __version__
        from epubforge.corpus import signature

        from tests.public_corpus import build_all

        book = build_all(tmp_path / "src")[0]
        record = signature(pathlib.Path(book), tmp_path)
        assert record["version"] == __version__

    def test_the_release_is_not_part_of_the_comparison(self):
        """Otherwise bumping the version reports every book in the corpus as
        changed and buries the one book that really did."""
        from epubforge.corpus import differences

        before = {"version": "0.2.5", "preserve": {"blocks": 10}}
        after = {"version": "0.2.6", "preserve": {"blocks": 10}}
        assert differences(before, after) == []

        moved = {"version": "0.2.6", "preserve": {"blocks": 11}}
        assert differences(before, moved) == ["preserve.blocks: 10 → 11"]

    def test_a_partial_run_reads_as_partial(self):
        """35 books on one release and 38 on the next is the truth about a run
        made away from home, and it must not look like 73 on the newer one."""
        from epubforge.corpus import releases

        records = [{"version": "0.2.4"}] * 35 + [{"version": "0.2.5"}] * 38
        assert releases(records) == {"0.2.4": 35, "0.2.5": 38}

class TestTheStreakIsReadFromHistory:
    """"Green across three consecutive releases" is a question about history,
    and a signature holds a book's *latest* measurement only — so the moment a
    book is re-measured, the release it was green on before is gone from the
    record. Stamping the release into signatures made a partial run visible and
    still could not answer the question. The runs are logged instead.
    """

    @staticmethod
    def run(version, *, books=50, clean=True):
        return {"version": version, "books": books, "clean": clean}

    def test_consecutive_clean_runs_build_a_streak(self):
        from epubforge.corpus import green_streak

        history = [self.run("0.2.4"), self.run("0.2.5"), self.run("0.2.6")]
        assert green_streak(history) == ["0.2.4", "0.2.5", "0.2.6"]

    def test_one_dirty_run_starts_the_count_again(self):
        """Not "two out of three". The condition is consecutive, and a release
        that lost text is where the counting starts over."""
        from epubforge.corpus import green_streak

        history = [self.run("0.2.4"), self.run("0.2.5", clean=False), self.run("0.2.6")]
        assert green_streak(history) == ["0.2.6"]

    def test_a_run_too_small_to_mean_anything_does_not_extend_it(self):
        """A run over three books says nothing about a corpus of eighty-six,
        and letting it count would be the same mistake as counting books
        instead of families."""
        from epubforge.corpus import green_streak

        history = [self.run("0.2.4"), self.run("0.2.5", books=3), self.run("0.2.6")]
        assert green_streak(history, minimum=30) == ["0.2.4", "0.2.6"]

    def test_the_same_release_twice_counts_once(self):
        from epubforge.corpus import green_streak

        history = [self.run("0.2.6"), self.run("0.2.6")]
        assert green_streak(history) == ["0.2.6"]

    def test_the_ledger_lives_beside_the_signatures_not_among_them(self):
        """That folder means "one file per book". The owner's inventory landed
        in it once by accident and broke the analysis on the spot."""
        import pathlib

        from epubforge.corpus import RUNS, signature_files

        expected = pathlib.Path("tests/corpus/expected")
        assert not (expected / RUNS).exists()
        assert (expected.parent / RUNS).is_file()
        # And a stray file could not pass for a book even if it were there.
        assert all(len(p.stem) == 16 for p in signature_files(expected))
