"""F-019 / F-020 — how much of a machine one book may cost.

There were three limits: the archive's total size, one entry's size, and the
compression ratio. They cover one attack — a ZIP that unpacks into more than a
disk — and everything past unpacking was unbounded. A hundred thousand tiny
entries, a document nested ten thousand deep, an image whose dimensions
multiply out to a hundred gigapixels: each is small in the archive and enormous
in memory, and none of them was counted.

Every test here checks two things, and the second matters as much as the first:
that the limit refuses, and that the refusal is a **finding with both numbers in
it** rather than a traceback. A limit whose message does not say what it was is
a limit nobody can act on.

The numbers are not in EPUB 3.3 and this file does not pretend otherwise. They
are an operational judgement, set well above every real book measured on two
shelves and far below what breaks a machine — the last class checks that second
half, because a budget that refuses real books is not a safety feature.
"""

from __future__ import annotations

import io
import time
import zipfile

import pytest

from epubforge.budget import Budget, BudgetExceeded, _nesting
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy

from .factory import make_modern_epub


class TestCountingNesting:
    """The depth test runs on raw bytes, before a tree exists — a tree deep
    enough to matter is one that overflows the C stack while being built, so
    noticing afterwards is noticing from the wrong side of the crash."""

    def test_a_flat_document_is_shallow(self):
        assert _nesting(b"<html><body><p>x</p></body></html>") == 3

    def test_nesting_is_counted_to_its_deepest_point(self):
        assert _nesting(b"<a><b><c></c></b></a><d></d>") == 3

    def test_a_self_closing_tag_does_not_open_anything(self):
        assert _nesting(b"<html><img/><br/></html>") == 1

    def test_nor_does_a_void_element_left_unclosed(self):
        """`<br>` without a slash is how half the web is written, and counting
        it as an opening tag reports a flat document as a thousand deep."""
        assert _nesting(b"<html><br><br><br><img src='x'></html>") == 1

    def test_a_bomb_is_found(self):
        assert _nesting(b"<a>" * 5000 + b"</a>" * 5000) == 5000


class TestTheLimitsThemselves:
    def test_too_many_entries(self):
        with pytest.raises(BudgetExceeded) as raised:
            Budget(entries=10).archive_entries(11)
        assert raised.value.found == 11
        assert raised.value.allowed == 10

    def test_a_document_too_large_to_parse(self):
        with pytest.raises(BudgetExceeded, match="document bytes"):
            Budget(document_bytes=100).document(b"<p>" + b"x" * 200 + b"</p>", "chapter.xhtml")

    def test_a_document_too_deep_to_parse(self):
        with pytest.raises(BudgetExceeded, match="nesting depth"):
            Budget(depth=10).document(b"<a>" * 50 + b"</a>" * 50, "chapter.xhtml")

    def test_an_image_that_multiplies_out(self):
        """Small on disk, forty gigabytes of RGBA the moment anything decodes
        it. Asked of the header, before anything does."""
        with pytest.raises(BudgetExceeded, match="pixels"):
            Budget(pixels=1_000_000).image(100_000, 100_000, 1, "bomb.png")

    def test_frames_multiply_too(self):
        Budget(pixels=1000).image(10, 10, 10)
        with pytest.raises(BudgetExceeded):
            Budget(pixels=1000).image(10, 10, 11)

    def test_the_clock_runs_from_when_the_budget_was_made(self):
        """A budget made five seconds ago has spent five seconds, whoever asks.

        The first version wrote `Budget(seconds=0.0)` and expected the very next
        call to refuse — which works only where the clock has already moved by
        the time it is read. Windows' `time.monotonic()` ticks about every 16 ms,
        so `spent` came back an exact `0.0`, and `0.0 > 0.0` is false. The test
        was measuring the granularity of the platform clock while claiming to
        measure where the deadline starts. Backdating `started` measures the
        thing in the name of the test, and measures it the same everywhere.
        """
        budget = Budget(seconds=0.5, started=time.monotonic() - 5)
        with pytest.raises(BudgetExceeded, match="wall clock"):
            budget.deadline("content")

    def test_and_the_same_allowance_fresh_is_fine(self):
        """The other half: the refusal above came from the start time and not
        from the allowance being small."""
        Budget(seconds=0.5).deadline("content")

    def test_an_ordinary_book_spends_none_of_it(self):
        budget = Budget()
        budget.archive_entries(120)
        budget.document(b"<html><body><p>tekst</p></body></html>", "chapter.xhtml")
        budget.image(1600, 2400, 1, "cover.jpg")
        budget.deadline()


class TestARefusalIsAFindingAndNotATraceback:
    def bomb(self, tmp_path, entries: int) -> str:
        """An archive with more members than any book has."""
        path = tmp_path / "bomb.epub"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            for index in range(entries):
                archive.writestr(f"OEBPS/junk/{index}.bin", b"x")
        return str(path)

    @pytest.fixture
    def refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr("epubforge.budget.MAX_ENTRIES", 50)
        return rebuild(self.bomb(tmp_path, 200), str(tmp_path / "out.epub"),
                       Policy.preset("preserve"))

    def test_nothing_is_written(self, refused, tmp_path):
        assert refused.status is Status.BLOCKED
        assert refused.output_path is None
        assert not (tmp_path / "out.epub").exists()

    def test_the_report_says_which_limit_and_both_numbers(self, refused):
        finding = next(
            f for f in refused.report.findings if f.rule == "package.budget-exceeded"
        )
        assert finding.values["limit"] == "archive entries"
        # 200 junk members plus `mimetype`, which is an entry like any other.
        assert finding.values["found"] == 201
        assert finding.values["allowed"] == 50

    def test_an_image_bomb_is_refused_the_same_way(self, tmp_path, monkeypatch):
        Image = pytest.importorskip("PIL.Image")
        monkeypatch.setattr("epubforge.budget.MAX_PIXELS", 1000)

        buffer = io.BytesIO()
        Image.new("RGB", (200, 200), "red").save(buffer, format="PNG")
        source = make_modern_epub(str(tmp_path / "plain.epub"), title="T")
        with zipfile.ZipFile(source) as archive:
            entries = {n: archive.read(n) for n in archive.namelist()}
        picture = next((n for n in entries if n.endswith(".png")), None)
        if picture is None:
            pytest.skip("the plain fixture carries no raster image")
        entries[picture] = buffer.getvalue()

        path = tmp_path / "in.epub"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            for name, data in entries.items():
                if name != "mimetype":
                    archive.writestr(name, data)

        result = rebuild(str(path), str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        finding = next(
            f for f in result.report.findings if f.rule == "package.budget-exceeded"
        )
        assert "pixels" in finding.values["limit"]


class TestTheCeilingsAreAboveRealBooks:
    """A budget that refuses real books is not a safety feature. These are the
    numbers as shipped, against what has actually been measured."""

    def test_the_entry_ceiling_clears_the_largest_book_seen(self):
        """The biggest on either shelf is a nine-thousand-document omnibus."""
        from epubforge.budget import MAX_ENTRIES

        assert MAX_ENTRIES >= 20_000

    def test_the_document_ceiling_clears_the_largest_chapter_seen(self):
        """233 946 characters, in a Polish translation of Baskerville."""
        from epubforge.budget import MAX_DOCUMENT_BYTES

        assert MAX_DOCUMENT_BYTES >= 64 * 1024**2

    def test_the_depth_ceiling_is_above_what_a_converter_produces(self):
        """A converter that wraps every paragraph in three `<div>`s makes deep
        markup and is not attacking anybody."""
        from epubforge.budget import MAX_DEPTH

        assert MAX_DEPTH >= 1024

    def test_the_pixel_ceiling_clears_any_plate_a_book_carries(self):
        from epubforge.budget import MAX_PIXELS

        assert MAX_PIXELS >= 250_000_000

    @pytest.mark.parametrize("preset", ["preserve", "strict", "minimal"])
    def test_an_ordinary_book_rebuilds_untouched_by_any_of_it(self, tmp_path, preset):
        source = make_modern_epub(str(tmp_path / "in.epub"), title="T")
        result = rebuild(source, str(tmp_path / f"out-{preset}.epub"), Policy.preset(preset))
        assert result.status is Status.SUCCEEDED
        assert "package.budget-exceeded" not in {
            f.rule for f in result.report.findings if f.rule
        }
