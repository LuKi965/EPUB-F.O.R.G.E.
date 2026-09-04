"""The command line's paths the contract tests never walked.

The audit of 2026-09-03 measured `cli.py` at 50 % line coverage, and the
lines it named were not decoration: `--plan`, `--report` to a directory and
to a file, `--check`, `--first-rendition-only`, every flag that carries a
value, and the `inspect`, `check` and `health` commands. Each is something a
person runs a shelf through, so each gets a test that runs it in-process and
holds it to what it says it does.
"""

from __future__ import annotations

import json
import os

import pytest

from epubforge.cli import (
    EXIT_NOT_WRITTEN,
    EXIT_OK,
    _bytes_from,
    build_parser,
    build_policy,
    main,
)
from epubforge.validate import find_epubcheck

from .factory import make_modern_epub


def run(*args: str) -> int:
    return main(list(args))


def parsed(*flags: str):
    return build_policy(build_parser().parse_args(["build", "x.epub", *flags]))


@pytest.fixture
def book(tmp_path) -> str:
    return make_modern_epub(str(tmp_path / "book.epub"))


class TestAPlanRunWritesNothing:
    def test_the_destination_stays_absent_and_the_plan_is_printed(self, book, tmp_path, capsys):
        destination = str(tmp_path / "out.epub")
        code = run("build", book, "-o", destination, "--plan", "--gate", "off", "--render-gate", "off")
        printed = capsys.readouterr().out
        assert code == EXIT_OK
        assert not os.path.exists(destination), "a plan run must not touch the destination"
        assert "would write" in printed
        assert "plan" in printed


class TestTheReportGoesWhereItIsAsked:
    def test_a_directory_gets_one_file_per_book(self, book, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        destination = str(tmp_path / "out.epub")
        assert run("build", book, "-o", destination, "--report", str(reports),
                   "--gate", "off", "--render-gate", "off") == EXIT_OK
        written = list(reports.iterdir())
        assert [p.name for p in written] == ["out.epub.json"]
        payload = json.loads(written[0].read_text(encoding="utf-8"))
        assert payload["source"].endswith("book.epub")
        assert "schema" in payload

    def test_a_file_gets_the_single_report(self, book, tmp_path):
        report = tmp_path / "report.json"
        assert run("build", book, "-o", str(tmp_path / "out.epub"), "--report", str(report),
                   "--gate", "off", "--render-gate", "off") == EXIT_OK
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["source"].endswith("book.epub")

    def test_a_file_gets_the_batch_document_for_several_books(self, tmp_path):
        sources = [make_modern_epub(str(tmp_path / f"book-{n}.epub")) for n in (1, 2)]
        out = tmp_path / "out"
        report = tmp_path / "batch.json"
        assert run("build", *sources, "-o", str(out), "--report", str(report),
                   "--gate", "off", "--render-gate", "off") == EXIT_OK
        text = report.read_text(encoding="utf-8")
        json.loads(text)
        assert "book-1.epub" in text and "book-2.epub" in text, "both books are in one document"


class TestTheOtherBuildSwitches:
    def test_first_rendition_only_still_writes_an_ordinary_book(self, book, tmp_path):
        destination = str(tmp_path / "out.epub")
        assert run("build", book, "-o", destination, "--first-rendition-only",
                   "--gate", "off", "--render-gate", "off") == EXIT_OK
        assert os.path.exists(destination)

    def test_check_runs_the_validator_on_the_result(self, book, tmp_path, capsys):
        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        destination = str(tmp_path / "out.epub")
        # `-v`, because the validator's verdict on a clean book is an INFO line
        # and INFO is hidden by default.
        code = run("build", book, "-o", destination, "--check", "-v", "--gate", "off", "--render-gate", "off")
        printed = capsys.readouterr().out
        assert code == EXIT_OK
        assert "epubcheck" in printed.lower()


class TestTheFlagsThatCarryAValue:
    def test_the_gates(self):
        assert parsed("--render-gate", "off").render_gate == "off"
        assert parsed("--gate", "off").validate_before_publish == "off"
        # `--gate` unset means what the preset says — never silently "off".
        assert parsed("--strict").validate_before_publish != "off"

    def test_watermarks_and_the_markup_switch(self):
        assert parsed("--keep-watermark-markup").watermarks == "keep"
        assert parsed("--watermarks", "gather").watermarks == "gather"
        # The mode wins over the switch, in either order on the command line.
        assert parsed("--keep-watermark-markup", "--watermarks", "gather").watermarks == "gather"

    def test_compat_in_both_spellings(self):
        assert parsed("--compat", "kindle,kobo").compat_profiles == ("kindle", "kobo")
        assert parsed("--compat", "kindle", "--compat", "kobo").compat_profiles == ("kindle", "kobo")
        assert parsed("--compat", "Kindle, kindle").compat_profiles == ("kindle",)

    def test_metadata_overrides(self):
        policy = parsed("--language", "pl", "--title", "T", "--author", "A", "--publisher", "P", "--series", "S")
        assert policy.default_language == "pl"
        assert policy.metadata_overrides == {
            "language": "pl", "title": "T", "author": "A", "publisher": "P", "series": "S",
        }

    def test_modified_hyphen_review_and_memory(self, monkeypatch):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        assert parsed("--modified", "2026-01-01T00:00:00Z").modified_override == "2026-01-01T00:00:00Z"
        assert parsed().modified_override is None
        assert parsed("--hyphen-review", "each").hyphen_review == "each"
        assert parsed("--memory-limit", "512M").memory_limit == _bytes_from("512M") > 0


class TestTheReadOnlyCommands:
    def test_inspect_describes_the_book(self, book, capsys):
        assert run("inspect", book) == 0
        printed = capsys.readouterr().out
        assert "spine items" in printed and "nav document" in printed

    def test_check_runs_epubcheck_on_an_existing_file(self, book, capsys):
        if find_epubcheck() is None:
            pytest.skip("EPUBCheck is not installed here")
        code = run("check", book)
        printed = capsys.readouterr().out
        assert code in (0, 2)
        assert "valid" in printed

    def test_health_tells_a_whole_file_from_a_truncated_one(self, book, tmp_path, capsys):
        assert run("health", book) == EXIT_OK
        assert "całe" in capsys.readouterr().out
        cut = tmp_path / "cut.epub"
        data = open(book, "rb").read()
        cut.write_bytes(data[: len(data) // 2])
        assert run("health", str(cut)) == EXIT_NOT_WRITTEN
        assert "uszkodzone" in capsys.readouterr().out


class TestMergeFromTheCommandLine:
    """`repair.merge` has its own tests; this is the command around it — the
    plan printed, the confirmation that a script skips with `--yes` and a
    person without a terminal cannot give, and the whole book at the end."""

    @pytest.fixture
    def pair(self, book, tmp_path):
        import zipfile

        from tests.test_repair import corrupt

        with zipfile.ZipFile(book) as archive:
            documents = [name for name in archive.namelist() if name.endswith(".xhtml")]
        return (
            corrupt(book, str(tmp_path / "kopia-a.epub"), documents[0]),
            corrupt(book, str(tmp_path / "kopia-b.epub"), documents[1]),
        )

    def test_with_yes_the_merged_book_is_whole(self, pair, tmp_path, capsys):
        from epubforge import repair

        out = str(tmp_path / "scalona.epub")
        assert run("merge", *pair, "-o", out, "--yes") == EXIT_OK
        printed = capsys.readouterr().out
        assert "zapisano" in printed and "kopia-b.epub" in printed
        assert repair.inspect(out).healthy

    def test_without_a_terminal_nothing_is_written(self, pair, tmp_path, capsys):
        out = str(tmp_path / "scalona.epub")
        assert run("merge", *pair, "-o", out) == EXIT_NOT_WRITTEN
        assert "przerwane" in capsys.readouterr().out
        assert not os.path.exists(out)

    def test_one_copy_is_refused(self, book, tmp_path, capsys):
        assert run("merge", book, "-o", str(tmp_path / "x.epub"), "--yes") == EXIT_NOT_WRITTEN
        assert "nie da się scalić" in capsys.readouterr().out
