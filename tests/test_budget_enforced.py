"""F-019 and F-020: not "the limit works" but "the limit is reached".

The 2026-08-14 baseline reopened both, and it was right about both. This file
exists because `tests/test_resource_budget.py` was green the whole time.

That file calls `Budget(depth=10).document(...)` and asserts it refuses. It
does. What nothing asserted is that **anything in the program ever calls it** —
and nothing did. A reproduction set the ceiling to ten, handed the rebuild an
eighty-deep document, counted the calls to `Budget.document`, and got nought.
The book was parsed, rebuilt and published.

The same shape one level along for the clock: `deadline()` was asked *before*
each stage, which measures every stage except the one taking the time. A 0.05 s
limit with a stage sleeping 0.20 s produced a published book, because the only
checkpoint ran while there was still time left.

So every test here goes through `rebuild`. None of them constructs a `Budget`
and calls a method on it; that is the test that was already passing.

Two things came out of writing them, and both are in the code rather than here:

* Wiring the check in made it fire, and a stage caught it with an
  `except Exception` two frames up, filed `xhtml.unparseable`, and published the
  book anyway. `BudgetExceeded` is a `BaseException` now — the same reasoning as
  `KeyboardInterrupt`, because a limit any local handler can swallow is not a
  limit. `TestNobodyCanSwallowARefusal` is that, held to the program.
* The refusal is charged in `reader.parse_xml` and `xhtml.parse_document` rather
  than at their callers, so a parse added next year is bounded without anybody
  remembering to bound it.
"""

from __future__ import annotations

import os
import time
import zipfile

import pytest

from epubforge import budget as budget_module
from epubforge.budget import Budget, BudgetExceeded
from epubforge.pipeline import Status, rebuild, rebuild_all
from epubforge.policy import Policy
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Stage
from tests.factory import make_modern_epub, write_zip

CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/package.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)

NAV = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl"><head><title>N</title></head>'
    '<body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">R</a></li></ol></nav>'
    "</body></html>"
)

PACKAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:identifier id="i">urn:uuid:1</dc:identifier><dc:title>T</dc:title>'
    "<dc:language>pl</dc:language>"
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>'
    '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
    'properties="nav"/><item id="c" href="chapter.xhtml" '
    'media-type="application/xhtml+xml"/></manifest>'
    '<spine><itemref idref="c"/></spine></package>'
)


def book_with(body: str, path) -> str:
    page = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">'
        f"<head><title>R</title></head><body>{body}</body></html>"
    )
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": PACKAGE.encode(),
            "OEBPS/nav.xhtml": NAV.encode(),
            "OEBPS/chapter.xhtml": page.encode(),
        },
    )


def budget_findings(result) -> list:
    return [f for f in result.report.findings if f.rule == "package.budget-exceeded"]


class TestADeepDocumentIsRefusedByTheRebuild:
    """F-019, asked of the program rather than of the class."""

    @pytest.fixture
    def deep(self, tmp_path, monkeypatch):
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 10)
        source = book_with("<div>" * 80 + "tekst" + "</div>" * 80, tmp_path / "deep.epub")
        destination = tmp_path / "out.epub"
        return rebuild(source, str(destination), Policy.preset("preserve")), destination

    def test_it_is_blocked(self, deep):
        result, _ = deep
        assert result.status is Status.BLOCKED

    def test_nothing_is_written(self, deep):
        _, destination = deep
        assert not destination.exists()

    def test_the_report_says_both_numbers(self, deep):
        """A limit whose message does not say what it was is a limit nobody can
        act on — and one that says only "too deep" cannot be told from a bug."""
        result, _ = deep
        finding = budget_findings(result)[0]
        assert finding.values["limit"] == "nesting depth"
        assert int(finding.values["found"]) > 10
        assert int(finding.values["allowed"]) == 10

    def test_an_ordinary_book_is_untouched_by_any_of_this(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "zwykla.epub"))
        result = rebuild(source, str(tmp_path / "ok.epub"), Policy.preset("preserve"))
        assert result.status.wrote_a_file, result.report.to_text()


class TestTheLimitIsChargedWhereverAParseHappens:
    """The container and the package document are parsed before any stage runs,
    by a different function than content documents. Both are bounded, and both
    name themselves — a refusal that does not say which file is a refusal
    somebody has to bisect."""

    def test_a_huge_package_document_is_refused(self, tmp_path, monkeypatch):
        # Between the container (238 bytes) and the package document (566), so
        # what is under test is that the *package* is charged — the container
        # having already proved it in the fixture above.
        monkeypatch.setattr(budget_module, "MAX_DOCUMENT_BYTES", 400)
        source = book_with("<p>krótki</p>", tmp_path / "in.epub")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.status is Status.BLOCKED
        finding = budget_findings(result)[0]
        assert finding.values["limit"] == "document bytes"

    def test_the_refusal_names_the_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 10)
        source = book_with("<div>" * 80 + "x" + "</div>" * 80, tmp_path / "in.epub")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert budget_findings(result)[0].location, "refused, and would not say which file"


class TestNobodyCanSwallowARefusal:
    """The defect the fix itself produced, and the reason for `BaseException`.

    Wiring the check in made it fire; a stage caught it with `except Exception`,
    reported `xhtml.unparseable`, and published the book. The limit worked
    perfectly and the book came out anyway, under a finding about a different
    thing entirely — which is worse than no limit, because the report is now
    wrong as well as the outcome.
    """

    def test_it_is_not_in_the_class_broad_handlers_catch(self):
        assert issubclass(BudgetExceeded, BaseException)
        assert not issubclass(BudgetExceeded, Exception)

    def test_an_ordinary_handler_does_not_catch_it(self):
        try:
            raise BudgetExceeded("test", 1, 0)
        except Exception:  # noqa: BLE001 — that is the thing under test
            raise AssertionError("a broad handler swallowed a budget refusal")
        except BudgetExceeded:
            pass

    def test_the_stage_that_used_to_swallow_it_no_longer_does(self, tmp_path, monkeypatch):
        """The whole point, end to end: the document that used to come back as
        `xhtml.unparseable` now blocks the rebuild."""
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 10)
        source = book_with("<div>" * 80 + "x" + "</div>" * 80, tmp_path / "in.epub")
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        rules = {f.rule for f in result.report.findings}
        assert "xhtml.unparseable" not in rules
        assert "package.budget-exceeded" in rules


class TestTheClockCoversTheStageAndNotOnlyTheGapBeforeIt:
    """F-020."""

    @pytest.fixture
    def slow(self, tmp_path, monkeypatch):
        class SlowStage(Stage):
            name = "slow"

            def run(self, ctx):
                time.sleep(0.2)

        monkeypatch.setattr(budget_module, "MAX_SECONDS", 0.05)
        source = make_modern_epub(str(tmp_path / "in.epub"))
        destination = tmp_path / "out.epub"
        from epubforge.stages import DEFAULT_STAGES

        result = rebuild(
            source,
            str(destination),
            Policy.preset("preserve"),
            stages=[*DEFAULT_STAGES, SlowStage],
        )
        return result, destination

    def test_a_stage_that_runs_past_the_limit_blocks(self, slow):
        result, _ = slow
        assert result.status is Status.BLOCKED

    def test_and_publishes_nothing(self, slow):
        _, destination = slow
        assert not destination.exists()

    def test_the_refusal_is_the_wall_clock_one(self, slow):
        result, _ = slow
        assert budget_findings(result)[0].values["limit"] == "wall clock"

    def test_the_last_stage_is_checked_too(self, tmp_path, monkeypatch):
        """The version this replaces asked before each stage, so whatever the
        last stage spent was never measured at all — and the last stage is the
        one whose output gets published."""
        from epubforge.stages import DEFAULT_STAGES

        class SlowLast(Stage):
            name = "slow-last"

            def run(self, ctx):
                time.sleep(0.2)

        monkeypatch.setattr(budget_module, "MAX_SECONDS", 0.05)
        source = make_modern_epub(str(tmp_path / "in.epub"))
        destination = tmp_path / "out.epub"
        result = rebuild(
            source, str(destination), Policy.preset("preserve"), stages=[SlowLast]
        )
        assert result.status is Status.BLOCKED
        assert not destination.exists()


class TestTheBudgetIsActiveWhereverParsingHappens:
    """The mechanism, rather than one of its consequences: a parse that happens
    with no rebuild around it is still bounded. Diagnostics, the fidelity
    harness and the corpus all parse outside `rebuild`, and 'nobody set a
    budget' must not mean 'anything goes'."""

    def test_there_is_always_a_budget(self):
        assert isinstance(budget_module.current(), Budget)

    def test_a_rebuild_installs_its_own(self, tmp_path):
        seen = []
        real = budget_module.current

        def watch():
            answer = real()
            seen.append(id(answer))
            return answer

        source = make_modern_epub(str(tmp_path / "in.epub"))
        try:
            budget_module.current = watch
            rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        finally:
            budget_module.current = real
        assert seen, "no parse charged a budget during a whole rebuild"
        assert len(set(seen)) == 1, "one rebuild used more than one budget"

    def test_the_fallback_still_refuses(self, monkeypatch):
        """Outside a rebuild the module defaults apply, and they are limits
        rather than decoration."""
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 5)
        budget_module._UNBOUND = None
        with pytest.raises(BudgetExceeded):
            budget_module.bounded(b"<a>" * 50 + b"</a>" * 50, "nowhere.xhtml")
        budget_module._UNBOUND = None


class TestEveryPublicWayInHasTheSameBoundary:
    """DELTA-2026-08-15-001, and the finding is one line of `_renditions_of`.

    `BudgetExceeded` derives from `BaseException` so that no local
    `except Exception` can swallow a limit. That decision is right and it has a
    price: every place which genuinely means "answer nothing and let the proper
    path diagnose this" must now say so out loud. `_renditions_of` did not.

    The reproduction is one book and two entry points: a container nested past
    the depth limit came out of `rebuild` as a controlled `BLOCKED` with a
    report, and out of the public `rebuild_all` as a traceback. A limit that
    turns one entry point into a crash and another into a diagnosis is not one
    boundary; it is two, and the crashing one is the one a batch runs through.
    """

    @staticmethod
    def _with_deep_container(path, depth: int = 60) -> str:
        source = make_modern_epub(str(path))
        deep = "<c>" * depth + "</c>" * depth
        container = (
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles>'
            f"{deep}</container>"
        )
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                entries[name] = archive.read(name)
        entries["META-INF/container.xml"] = container.encode()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return source

    def test_rebuild_all_refuses_instead_of_raising(self, tmp_path, monkeypatch):
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 5)
        budget_module._UNBOUND = None
        source = self._with_deep_container(tmp_path / "in.epub")
        destination = tmp_path / "out.epub"
        try:
            results = rebuild_all(source, str(destination), Policy.preset("preserve"))
        finally:
            budget_module._UNBOUND = None
        assert [result.status for result in results] == [Status.BLOCKED]
        assert not destination.exists()

    def test_both_entry_points_agree_about_the_same_book(self, tmp_path, monkeypatch):
        """The assertion that would have caught it: not "rebuild_all blocks"
        but "rebuild_all blocks *because rebuild does*". Two entry points into
        one program may not disagree about whether a book is publishable."""
        monkeypatch.setattr(budget_module, "MAX_DEPTH", 5)
        budget_module._UNBOUND = None
        source = self._with_deep_container(tmp_path / "in.epub")
        try:
            one = rebuild(source, str(tmp_path / "a.epub"), Policy.preset("preserve"))
            many = rebuild_all(source, str(tmp_path / "b.epub"), Policy.preset("preserve"))
        finally:
            budget_module._UNBOUND = None
        assert one.status is many[0].status
        assert not (tmp_path / "a.epub").exists()
        assert not (tmp_path / "b.epub").exists()

    def test_the_reading_helpers_do_not_raise_either(self, tmp_path, monkeypatch):
        """`inspect` and `plan_merge` parse the same container. They answer a
        different question and they answer it without a rebuild around them, so
        neither has anywhere to put a refusal — which makes "does not raise" the
        whole requirement rather than a weaker one."""
        from epubforge import repair

        monkeypatch.setattr(budget_module, "MAX_DEPTH", 5)
        budget_module._UNBOUND = None
        source = self._with_deep_container(tmp_path / "in.epub")
        try:
            assert repair.inspect(source) is not None
            assert repair.plan_merge([source, source]) is not None
        finally:
            budget_module._UNBOUND = None


class TestStoppingInTheMiddleOfABook:
    """DELTA-2026-08-15-001's other half of F-020.

    The deadline was asked before and after every stage, which bounds a rebuild
    made of eleven stages and does nothing whatever for a *stage* walking six
    hundred documents. Cancellation had the identical shape and worse
    consequences: the window's loop looked at its flag between books, so Cancel
    on a large book meant "finish this one first".

    Both are the same question asked in the same place — the per-document
    accessor every stage goes through — and both raise a `BaseException`, so the
    writer's existing cleanup removes the staging file and whatever was already
    at the destination is untouched.
    """

    @staticmethod
    def _many_documents(path, count: int = 12) -> str:
        source = make_modern_epub(str(path))
        page = (
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>R</title></head><body><p>Tekst.</p></body></html>'
        )
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                entries[name] = archive.read(name)
        for index in range(count):
            entries[f"OEBPS/extra{index}.xhtml"] = page.encode()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return source

    def test_cancelling_stops_the_book_and_writes_nothing(self, tmp_path):
        source = self._many_documents(tmp_path / "in.epub")
        destination = tmp_path / "out.epub"
        result = rebuild(
            source, str(destination), Policy.preset("preserve"), cancelled=lambda: True
        )
        assert result.status is Status.BLOCKED
        assert not destination.exists()
        assert "package.cancelled" in {f.rule for f in result.report.findings if f.rule}

    def test_a_file_already_there_is_left_exactly_as_it_was(self, tmp_path):
        """The whole reason cancelling has to be a refusal rather than a crash:
        somebody stopping a rebuild must not lose the book they already had."""
        destination = tmp_path / "out.epub"
        destination.write_bytes(b"ksiazka, ktora juz tam byla")
        source = self._many_documents(tmp_path / "in.epub")
        rebuild(source, str(destination), Policy.preset("preserve"), cancelled=lambda: True)
        assert destination.read_bytes() == b"ksiazka, ktora juz tam byla"

    def test_nothing_half_written_is_left_beside_it(self, tmp_path):
        source = self._many_documents(tmp_path / "in.epub")
        rebuild(
            source, str(tmp_path / "out.epub"), Policy.preset("preserve"),
            cancelled=lambda: True,
        )
        assert not [p.name for p in tmp_path.glob("*.part.epub")]
        assert not [p.name for p in tmp_path.glob(".*")]

    def test_not_cancelling_changes_nothing(self, tmp_path):
        source = self._many_documents(tmp_path / "in.epub")
        result = rebuild(
            source, str(tmp_path / "out.epub"), Policy.preset("preserve"),
            cancelled=lambda: False,
        )
        assert result.status.wrote_a_file, result.report.to_text()

    def test_the_clock_is_asked_inside_a_stage_and_not_only_between_them(
        self, tmp_path, monkeypatch
    ):
        """The assertion that would have caught the original: count the
        checkpoints during one rebuild and require more of them than there are
        stages. A per-stage check passes any test that only asks whether the
        clock is consulted at all."""
        seen = []
        real = Budget.checkpoint

        def counted(self, where=""):
            seen.append(where)
            return real(self, where)

        monkeypatch.setattr(Budget, "checkpoint", counted)
        source = self._many_documents(tmp_path / "in.epub", count=12)
        rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert len(seen) > len(DEFAULT_STAGES), (
            f"{len(seen)} checkpoints for {len(DEFAULT_STAGES)} stages: "
            "the clock is still only asked between them"
        )
        assert len(set(seen)) > 1, "every checkpoint named the same place"
