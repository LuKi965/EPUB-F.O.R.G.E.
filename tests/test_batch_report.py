"""One file for a whole run, instead of thirty opened one at a time.

Saving a report per book is right for one book and unusable for thirty. The
question a batch actually raises is *which* of them needs attention, and
answering it by opening every file is slower than not asking.

The command line had a defect of the same shape: `--report out.json` with five
books wrote all five to one path in turn, so what survived was a report about
whichever book happened to be last — indistinguishable from a report about the
run.
"""

from __future__ import annotations

import json

from epubforge.report import Level, Report, batch_to_dict, batch_to_json


def report(name: str, *levels: Level) -> Report:
    made = Report(source=f"{name}.epub", output=f"out/{name}.epub")
    for level in levels:
        made.add("stage", level, f"{level.value} w {name}")
    return made


class TestWhatTheDocumentSays:
    def test_it_counts_the_run_not_just_the_books(self):
        payload = batch_to_dict([report("a", Level.ERROR), report("b", Level.FIX)])
        assert payload["books"] == 2
        assert payload["with_errors"] == 1
        assert payload["summary"]["error"] == 1
        assert payload["summary"]["fix"] == 1

    def test_every_book_keeps_its_whole_report(self):
        """The batch is an index, not a replacement. Anything that was in the
        single-book file has to still be here, or people will keep saving
        thirty files."""
        payload = batch_to_dict([report("a", Level.WARN)])
        book = payload["reports"][0]
        assert book["source"] == "a.epub"
        assert book["findings"][0]["message"] == "warn w a"
        assert book["summary"]["warn"] == 1

    def test_a_book_that_wrote_nothing_counts_separately(self):
        failed = Report(source="x.epub", output="out/x.epub")
        failed.add("stage", Level.ERROR, "nie zapisano")
        payload = batch_to_dict([report("ok", Level.FIX), failed])
        assert payload["written"] == 1
        assert payload["not_written"] == 1

    def test_it_is_json_and_keeps_polish_letters(self):
        text = batch_to_json([report("zażółć", Level.FIX)])
        assert "zażółć" in text
        json.loads(text)


class TestWorstFirst:
    """Read from the top and abandoned as soon as it stops being interesting —
    which only works if the interesting ones are at the top."""

    def test_a_book_that_wrote_nothing_comes_before_one_with_errors(self):
        wrote_nothing = Report(source="none.epub", output="o")
        wrote_nothing.add("s", Level.ERROR, "x")
        payload = batch_to_dict([report("clean", Level.FIX), wrote_nothing])
        assert payload["reports"][0]["source"] == "none.epub"

    def test_errors_come_before_warnings_and_warnings_before_quiet(self):
        payload = batch_to_dict(
            [
                report("quiet", Level.INFO),
                report("warned", Level.WARN),
                report("errored", Level.ERROR),
            ]
        )
        assert [r["source"] for r in payload["reports"]] == [
            "errored.epub",
            "warned.epub",
            "quiet.epub",
        ]

    def test_two_books_with_the_same_trouble_keep_a_stable_order(self):
        """Otherwise two runs of the same batch produce two different files and
        a diff between them says nothing."""
        first = batch_to_dict([report("b", Level.WARN), report("a", Level.WARN)])
        second = batch_to_dict([report("a", Level.WARN), report("b", Level.WARN)])
        assert [r["source"] for r in first["reports"]] == [
            r["source"] for r in second["reports"]
        ]


class TestTheCommandLineNoLongerOverwrites:
    def test_several_books_into_one_path_produce_a_batch(self, tmp_path):
        from epubforge.cli import main

        from .factory import make_modern_epub

        sources = [
            make_modern_epub(str(tmp_path / f"{name}.epub"), title=name)
            for name in ("jeden", "dwa", "trzy")
        ]
        target = tmp_path / "raport.json"
        code = main(["build", *sources, "--output", str(tmp_path / "out"), "--report", str(target)])
        assert code in (0, 2), code

        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["kind"] == "batch"
        assert payload["books"] == 3
        assert len(payload["reports"]) == 3

    def test_one_book_still_produces_a_plain_report(self, tmp_path):
        """Changing the shape for a single book would break anything already
        reading these files."""
        from epubforge.cli import main

        from .factory import make_modern_epub

        source = make_modern_epub(str(tmp_path / "sam.epub"))
        target = tmp_path / "raport.json"
        main(["build", source, "--output", str(tmp_path / "out"), "--report", str(target)])

        payload = json.loads(target.read_text(encoding="utf-8"))
        assert "kind" not in payload
        assert payload["source"].endswith("sam.epub")

    def test_a_directory_still_gets_one_file_per_book(self, tmp_path):
        from epubforge.cli import main

        from .factory import make_modern_epub

        sources = [
            make_modern_epub(str(tmp_path / f"{name}.epub"), title=name)
            for name in ("a", "b")
        ]
        folder = tmp_path / "raporty"
        folder.mkdir()
        main(["build", *sources, "--output", str(tmp_path / "out"), "--report", str(folder)])
        assert len(list(folder.glob("*.json"))) == 2
