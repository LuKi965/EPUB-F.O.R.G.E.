"""EF-020: the ceiling that was in the wrong unit.

`reader.py` has refused a book over 2 GiB of content since early on, and that
number was read by everybody — this file included, until it was measured — as
"the most memory this can use". It is not. The audit asked for a benchmark
before anything was done about the memory model, and the benchmark is why this
module exists rather than a rewrite of the reader.

Peak RSS of a whole rebuild, in its own process, four purchased books and two
synthetic ones:

    tekst MB   binaria MB   szczyt RSS      ponad interpreter
       1.0          0.5        52 MB
       1.3         11.6        78 MB
       0.2         14.9        75 MB
       0.2         23.3        87 MB
      25.4          0.0       340 MB
     152.1          0.0      2042 MB

Text costs about fourteen times its own size, so 2 GiB of content permits a
process of nearly thirty gigabytes, and between the two numbers the outcome is
not a refusal but a kill: no report, no diagnosis, no output.

The multiplier moved from 12.0 to 14.0 within a day of being fitted, because a
stage was added that reads every content document and the big synthetic book
went from 1861 MB to 2042. The row above is the *current* measurement and the
test that pins it is the reason a drift like that cannot go unnoticed: the
constants are a safety estimate, and a safety estimate that quietly goes stale
fails in the one direction that matters.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import memory
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import make_modern_epub


def book_of(path, *, text_bytes: int = 0, binary_bytes: int = 0) -> str:
    """An archive declaring the sizes, which is all the estimate reads."""
    make_modern_epub(str(path), title="Miara")
    if text_bytes or binary_bytes:
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
            if text_bytes:
                archive.writestr("OEBPS/duzy.xhtml", b"x" * text_bytes)
            if binary_bytes:
                archive.writestr("OEBPS/duzy.bin", b"y" * binary_bytes)
    return str(path)


class TestWhatABookIsExpectedToCost:
    def test_text_is_counted_apart_from_everything_else(self, tmp_path):
        measured = memory.estimate(book_of(tmp_path / "a.epub", text_bytes=1_000_000))
        assert measured.text_bytes >= 1_000_000
        heavier = memory.estimate(book_of(tmp_path / "b.epub", binary_bytes=1_000_000))
        assert heavier.binary_bytes >= 1_000_000

    def test_a_megabyte_of_text_costs_more_than_a_megabyte_of_pictures(self, tmp_path):
        """The whole finding in one assertion. A book's *size* does not predict
        what it costs; the share of it that gets parsed does."""
        text = memory.estimate(book_of(tmp_path / "a.epub", text_bytes=8_000_000))
        binary = memory.estimate(book_of(tmp_path / "b.epub", binary_bytes=8_000_000))
        assert text.peak_bytes > binary.peak_bytes * 2

    def test_it_is_read_from_the_directory_and_not_by_decompressing(self, tmp_path):
        """A refusal has to be cheap or it is not a safeguard: decompressing to
        find out whether there is room to decompress is the failure it prevents.
        A stored entry declaring its size is enough."""
        source = book_of(tmp_path / "a.epub", text_bytes=50_000_000)
        assert tmp_path.joinpath("a.epub").stat().st_size < 1_000_000
        assert memory.estimate(source).text_bytes >= 50_000_000

    def test_something_that_is_not_an_archive_gets_no_estimate(self, tmp_path):
        broken = tmp_path / "nie.epub"
        broken.write_bytes(b"nie jestem archiwum")
        assert memory.estimate(broken) is None

    def test_the_estimate_covers_what_was_measured(self):
        """The six rows in the docstring, as an assertion rather than a note.

        The model is allowed to be pessimistic and is not allowed to be
        optimistic: an estimate that comes in under the truth turns "this will
        not fit" into a process the kernel kills, which is the outcome the whole
        module exists to replace.
        """
        for text_mb, binary_mb, peak_mb in (
            (1.0, 0.5, 52), (1.3, 11.6, 78), (0.2, 14.9, 75),
            (0.2, 23.3, 87), (25.4, 0.0, 340), (152.1, 0.0, 2042),
        ):
            estimate = memory.Estimate(
                text_bytes=int(text_mb * 1e6), binary_bytes=int(binary_mb * 1e6)
            )
            assert estimate.peak_bytes >= peak_mb * 1024**2, (
                f"{text_mb} MB tekstu i {binary_mb} MB binariów zmierzono na "
                f"{peak_mb} MiB, a szacunek to {memory.human(estimate.peak_bytes)}"
            )


class TestTheVerdictAgainstAMachine:
    def test_a_fixed_budget_beats_asking_the_machine(self, tmp_path):
        source = book_of(tmp_path / "a.epub", text_bytes=50_000_000)
        assert not memory.check(source, limit=64 * 1024**2).fits
        assert memory.check(source, limit=8 * 1024**3).fits

    def test_a_machine_that_will_not_say_is_not_a_reason_to_refuse(self, tmp_path, monkeypatch):
        """`None` is a real answer and has to stay one. Refusing a book because
        a memory query failed would be this program inventing a reason to ruin
        somebody's evening."""
        monkeypatch.setattr(memory, "available_bytes", lambda: None)
        source = book_of(tmp_path / "a.epub", text_bytes=500_000_000)
        verdict = memory.check(source)
        assert verdict.fits
        assert not verdict.known

    def test_an_unreadable_file_is_left_to_the_reader_to_diagnose(self, tmp_path):
        broken = tmp_path / "nie.epub"
        broken.write_bytes(b"nie jestem archiwum")
        assert memory.check(broken, limit=1).fits

    def test_the_verdict_says_the_numbers(self, tmp_path):
        source = book_of(tmp_path / "a.epub", text_bytes=50_000_000)
        said = str(memory.check(source, limit=64 * 1024**2))
        assert "MiB" in said or "GiB" in said

    def test_headroom_is_left_rather_than_planning_to_use_it_all(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory, "available_bytes", lambda: 1000 * 1024**2)
        verdict = memory.check(book_of(tmp_path / "a.epub"))
        assert verdict.limit < verdict.available


class TestTheRebuildRefusesBeforeItAllocates:
    def test_a_book_too_big_for_the_budget_is_refused_with_a_report(self, tmp_path):
        source = book_of(tmp_path / "a.epub", text_bytes=50_000_000)
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", memory_limit=64 * 1024**2),
        )
        assert not result.status.wrote_a_file
        assert any(
            finding.rule == "package.memory-refused" for finding in result.report.findings
        )

    def test_the_message_says_both_numbers_and_where_they_come_from(self, tmp_path):
        source = book_of(tmp_path / "a.epub", text_bytes=50_000_000)
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", memory_limit=64 * 1024**2),
        )
        said = result.report.to_text()
        assert "64 MiB" in said, said
        # Not just "too big": which part of the book is expensive, because that
        # is the only part of this a person can do anything about.
        assert "tekst" in said or "text" in said

    def test_nothing_is_written_where_the_output_would_have_gone(self, tmp_path):
        target = tmp_path / "out.epub"
        rebuild(
            book_of(tmp_path / "a.epub", text_bytes=50_000_000),
            str(target),
            Policy.preset("preserve", memory_limit=64 * 1024**2),
        )
        assert not target.exists()

    def test_a_book_that_fits_is_not_mentioned_at_all(self, tmp_path):
        result = rebuild(
            book_of(tmp_path / "a.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", memory_limit=8 * 1024**3),
        )
        assert result.status.wrote_a_file
        assert not any(
            finding.rule == "package.memory-refused" for finding in result.report.findings
        )

    def test_the_switch_turns_it_off(self, tmp_path):
        """The owner's standing rule. The estimate is a model built from six
        books; the person in front of the machine may know better."""
        result = rebuild(
            book_of(tmp_path / "a.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", check_memory=False, memory_limit=1),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        # A limit of one byte, and it publishes: proof the switch is read and
        # not merely present.
        blocked = rebuild(
            book_of(tmp_path / "b.epub"),
            str(tmp_path / "out2.epub"),
            Policy.preset("preserve", memory_limit=1),
        )
        assert not blocked.status.wrote_a_file

    def test_it_costs_nothing_on_an_ordinary_book(self, tmp_path):
        """Measured rather than asserted by eye: the guard reads the central
        directory, so it must not scale with the book."""
        import time

        source = book_of(tmp_path / "a.epub", text_bytes=20_000_000)
        started = time.monotonic()
        for _ in range(20):
            memory.check(source, limit=8 * 1024**3)
        assert time.monotonic() - started < 1.0


class TestTheSizesPeopleType:
    @pytest.mark.parametrize(
        "typed, expected",
        [("2G", 2 * 1024**3), ("512M", 512 * 1024**2), ("1500000", 1_500_000),
         ("2GB", 2 * 1024**3), ("1.5G", int(1.5 * 1024**3))],
    )
    def test_a_size_is_read_the_way_it_was_written(self, typed, expected):
        from epubforge.cli import _bytes_from

        assert _bytes_from(typed) == expected
