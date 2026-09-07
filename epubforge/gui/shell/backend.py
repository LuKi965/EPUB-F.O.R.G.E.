"""The seam: one object the pages talk to, one place the engine is understood.

Everything above this line thinks in `models` dataclasses. Everything below it
is `Policy`, `Report`, `rebuild_all` and the rest of the program. The two never
meet — which is what makes the flow testable with `DemoBackend` and the engine
replaceable without opening a single page.

`policy_for` is the other half of the contract: **one** function turns a preset
and a set of overrides into a `Policy`, and it is tested on its own. The old
window built its policy by reading forty widgets scattered across a column;
that is exactly the arrangement in which one forgotten `isChecked()` becomes a
setting that silently does nothing.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ...policy import Policy
from .models import (
    BatchOutcome,
    BookItem,
    BookStatus,
    ChangeCategory,
    Preset,
    Progress,
    RebuildPlan,
)
from .options import OPTIONS

ProgressCallback = Callable[[Progress], None]
Cancelled = Callable[[], bool]
BookDone = Callable[[int, BookItem], None]


class ForgeUiBackend(Protocol):
    """What the interface needs from the program underneath it."""

    def analyse(self, paths: "list[pathlib.Path]", *, progress: ProgressCallback,
                cancelled: Cancelled) -> "list[BookItem]": ...

    def defaults_for(self, preset: Preset) -> dict: ...

    def rebuild(self, plan: RebuildPlan, books: "list[BookItem]", *,
                progress: ProgressCallback, cancelled: Cancelled,
                book_done: BookDone, resolver=None) -> BatchOutcome: ...

    def destination_for(self, source: pathlib.Path, folder: "pathlib.Path | None",
                        kepub: bool) -> str: ...

    def export_report(self, book: BookItem, destination: pathlib.Path) -> None: ...

    def export_batch(self, books: "list[BookItem]", destination: pathlib.Path) -> None: ...

    def reveal(self, path: pathlib.Path) -> None: ...


# --------------------------------------------------------------------------
# preset + overrides → Policy, in one place, with tests of its own
# --------------------------------------------------------------------------

#: Overrides whose key is not a `Policy` field. Each is handled explicitly in
#: `policy_for`; a key that is neither here nor a field of `Policy` is a bug,
#: and `test_shell_backend` proves the catalogue contains no such key.
NOT_POLICY_FIELDS = {
    "validate",       # whether EPUBCheck runs at all — an argument of the run
    "plan_only",      # a run that stops one step short of the destination
    "render_all",     # `render_sample` = 0 rather than a sample
    "ask",            # whether questions may interrupt — the resolver, not policy
    "meta.title", "meta.author", "meta.language",
    "compat.kindle", "compat.kobo", "compat.apple", "compat.legacy",
}


def policy_for(plan: RebuildPlan) -> "tuple[Policy, bool, bool]":
    """`(policy, run_epubcheck, plan_only)` for one plan.

    The preset is the engine's own (`Policy.preset`), so the three cards on the
    plan screen are the three modes the program has always had — not a fourth
    opinion invented in the interface.
    """
    policy = Policy.preset(plan.preset.value)
    overrides = dict(plan.overrides)

    profiles = tuple(
        name for name in ("kindle", "kobo", "apple", "legacy")
        if overrides.get(f"compat.{name}", False)
    )
    if profiles:
        policy.compat_profiles = profiles

    for key, value in overrides.items():
        if key in NOT_POLICY_FIELDS:
            continue
        if key == "memory_limit":
            policy.memory_limit = _bytes_or_none(value)
            continue
        if key == "time_budget_seconds":
            policy.time_budget_seconds = float(value)
            continue
        if hasattr(policy, key):
            setattr(policy, key, value)

    if overrides.get("render_all"):
        # "There has to be an option to check the whole book" — a sample is
        # somebody else's choice about which pages of your book matter.
        policy.render_sample = 0

    for name, key in (("title", "meta.title"), ("author", "meta.author"),
                      ("language", "meta.language")):
        value = str(overrides.get(key, "")).strip()
        if value:
            policy.metadata_overrides[name] = value
            if name == "language":
                policy.default_language = value

    return policy, bool(overrides.get("validate", True)), bool(overrides.get("plan_only", False))


def _bytes_or_none(value) -> "int | None":
    """A size a person typed, or nothing.

    Nothing is the right answer for an unparseable size: the field narrows a
    limit that already has a sane default, so falling back to the machine's own
    answer is what somebody who mistyped would have wanted.
    """
    text = str(value).strip()
    if not text:
        return None
    from ...cli import _bytes_from

    try:
        return _bytes_from(text)
    except ValueError:
        return None


def destination_for(source: pathlib.Path, folder: "pathlib.Path | None", kepub: bool) -> str:
    """Where one book will be written — the rule the old window used, verbatim.

    With no folder chosen the book lands beside its original as `.forged.epub`;
    with one, it keeps the source's clean name because the folder already says
    what it holds. Either way the original keeps its own name, which is half of
    why it survives.
    """
    from ... import plan as plan_module

    if folder:
        os.makedirs(folder, exist_ok=True)
        name = (
            f"{plan_module.stem_of(str(source))}{plan_module.KEPUB_EXTENSION}"
            if kepub else source.name
        )
        return os.path.join(str(folder), name)
    return plan_module.destination_for(str(source), None, kepub=kepub)


def defaults_from_policy(preset: Preset, *, epubcheck: bool = True) -> dict:
    """Every option's value under one preset, read from the engine.

    The drawer must show what the rebuild would actually do, so the defaults
    come from `Policy.preset` rather than from a table in the interface that
    would drift from it within a release.
    """
    policy = Policy.preset(preset.value)
    values: dict = {}
    for option in OPTIONS:
        key = option.key
        if key.startswith("compat."):
            values[key] = key.split(".", 1)[1] in policy.compat_profiles
        elif key.startswith("meta."):
            values[key] = policy.metadata_overrides.get(key.split(".", 1)[1], "")
        elif key == "validate":
            values[key] = epubcheck
        elif key == "plan_only":
            values[key] = False
        elif key == "render_all":
            values[key] = policy.render_sample == 0
        elif key == "ask":
            values[key] = True
        elif key == "memory_limit":
            values[key] = "" if policy.memory_limit is None else str(policy.memory_limit)
        elif key == "time_budget_seconds":
            values[key] = int(policy.time_budget_seconds)
        else:
            values[key] = getattr(policy, key, False)
    return values


# --------------------------------------------------------------------------
# the real thing
# --------------------------------------------------------------------------

@dataclass
class _Run:
    """Everything one batch carries, so `_rebuild_one` takes a book and a run.

    A batch is not a loop variable: the policy, the standing answers and the
    temporary room for a plan-only run all belong to the whole thing, and
    passing nine arguments down is how a loop body turns into a function
    nobody can call from a test.
    """

    plan: RebuildPlan
    policy: Policy
    run_check: bool
    plan_only: bool
    room: object
    resolver: object
    progress: object
    cancelled: object
    total: int
    #: Answers given "for all of them" — one dict for the batch, not per book.
    standing: dict = field(default_factory=dict)




class EngineBackend:
    """The adapter. Reads books, runs rebuilds, and translates both ways."""

    def __init__(self, language: str = "pl") -> None:
        self.language = language
        #: Source path → the `Report` of the last run of that book. The pages
        #: never see these; they ask for a file to be written and name the
        #: book. Kept because a saved report has to be the same JSON the old
        #: window saved — the same domain information, as the acceptance list
        #: puts it — and a rendered text is not that.
        self._reports: dict = {}

    # -- analysis ---------------------------------------------------------
    def analyse(self, paths, *, progress=None, cancelled=None) -> "list[BookItem]":
        """Read each file and say what it is. Nothing is written or changed.

        A file that cannot be read becomes a row that says so, and the rest of
        the batch is analysed anyway — the acceptance list asks for exactly
        that, and it is the difference between a batch and a queue.
        """
        books: list[BookItem] = []
        total = len(paths)
        for index, path in enumerate(paths, start=1):
            if cancelled is not None and cancelled():
                break
            source = pathlib.Path(path)
            if progress is not None:
                progress(Progress(index, total, source.name, "analysis"))
            books.append(self._analyse_one(source))
        return books

    def _analyse_one(self, source: pathlib.Path) -> BookItem:
        from ..strings import tr

        kind = "PDF" if source.suffix.lower() == ".pdf" else "EPUB"
        size = source.stat().st_size if source.exists() else 0
        item = BookItem(source=source, title=source.stem, kind=kind, size=size)

        if kind == "PDF":
            # Reading a PDF's text layer is the rebuild's own first stage and
            # costs as much as the rebuild does; analysis says what the file is
            # and leaves the reading to the run.
            item.status = BookStatus.READY
            item.summary = tr("shell.analysis.pdf")
            return item

        from ...reader import EpubReadError, read_epub
        from ...report import Report

        report = Report(source=str(source))
        try:
            parsed = read_epub(str(source), report)
        except EpubReadError as exc:
            item.status = BookStatus.FAILED
            item.error = tr("shell.analysis.unreadable", reason=str(exc))
            return item
        except Exception as exc:  # noqa: BLE001 — somebody else's file
            # lxml, zipfile and everything under them, on a file nobody
            # vouches for. A row that says what went wrong beats a window that
            # stops on the third book of thirty.
            item.status = BookStatus.FAILED
            item.error = tr("shell.analysis.unreadable", reason=f"{type(exc).__name__}: {exc}")
            return item

        metadata = parsed.metadata
        item.title = (metadata.title or source.stem).strip()
        item.author = ", ".join(creator.name for creator in metadata.creators)
        item.status = BookStatus.READY
        item.summary = tr(
            "shell.analysis.summary",
            version=parsed.source_version,
            resources=len(parsed.resources),
            spine=len(parsed.spine),
        )
        if parsed.has_drm:
            item.status = BookStatus.ATTENTION
            item.summary = tr("shell.analysis.drm")
        return item

    # -- the rebuild ------------------------------------------------------
    def rebuild(self, plan: RebuildPlan, books, *, progress=None, cancelled=None,
                book_done=None, resolver=None) -> BatchOutcome:
        """Rebuild every chosen book, one at a time, reporting as it goes.

        The loop is only a loop: what happens to one book is `_rebuild_one`,
        and where it is written is `_target_for`. Cancellation is checked
        between books **and** handed to the pipeline, so a large book stops in
        the middle rather than after.
        """
        import tempfile

        policy, run_check, plan_only = policy_for(plan)
        chosen = [book for book in books if book.chosen]
        room = tempfile.TemporaryDirectory(prefix="epubforge-plan-") if plan_only else None
        run = _Run(
            plan=plan, policy=policy, run_check=run_check, plan_only=plan_only,
            room=room, resolver=resolver, progress=progress, cancelled=cancelled,
            total=len(chosen),
        )
        finished = 0
        stopped = False
        try:
            for index, book in enumerate(chosen):
                if cancelled is not None and cancelled():
                    stopped = True
                    break
                if progress is not None:
                    progress(Progress(index, run.total, book.title, "rebuild"))
                self._rebuild_one(book, index, run)
                finished += 1
                if book_done is not None:
                    book_done(index, book)
        finally:
            if room is not None:
                room.cleanup()

        for book in chosen[finished:]:
            book.status = BookStatus.CANCELLED
        return BatchOutcome(
            books=tuple(chosen),
            cancelled=stopped or bool(cancelled is not None and cancelled()),
            destination=plan.destination,
        )

    def _target_for(self, book: BookItem, run: "_Run") -> "str | None":
        """Where this book goes, or `None` if that would be its own source.

        The one thing this program may never do, caught before the rebuild
        rather than inside it: the source is not even opened for a run that
        would end here.
        """
        from ..strings import tr

        destination = destination_for(book.source, run.plan.destination, run.policy.kepub)
        if run.room is not None:
            return os.path.join(run.room.name, os.path.basename(destination))
        if os.path.abspath(destination) == os.path.abspath(str(book.source)):
            book.status = BookStatus.FAILED
            book.error = tr("shell.overwrite.body", name=book.source.name)
            return None
        return destination

    def _rebuild_one(self, book: BookItem, index: int, run: "_Run") -> None:
        from ...pipeline import rebuild_all
        from ...report import Level, Report
        from ...validate import validate

        destination = self._target_for(book, run)
        if destination is None:
            return
        try:
            produced = rebuild_all(
                str(book.source), destination, run.policy, resolver=run.resolver,
                standing=run.standing,
                cancelled=(lambda: run.cancelled()) if run.cancelled is not None else None,
            )
            result = produced[0]
            if run.run_check:
                for one in produced:
                    # `report.validated` means the publication gate already
                    # asked EPUBCheck about these exact bytes; asking twice
                    # costs seconds and writes the verdict in twice.
                    if one.output_path and one.report.validated is None:
                        if run.progress is not None:
                            run.progress(Progress(index, run.total, book.title, "validate"))
                        validate(
                            one.output_path, one.report,
                            content_untouched=not run.policy.rewrite_content,
                        )
            if len(produced) > 1:
                # One row per source, so the siblings would otherwise be
                # written and never mentioned.
                result.report.add(
                    "package", Level.INFO, "package.renditions-written",
                    values={
                        "count": len(produced),
                        "names": ", ".join(
                            os.path.basename(one.output_path or "—") for one in produced
                        ),
                    },
                )
            self._absorb(book, result, plan_only=run.plan_only)
        except Exception as exc:  # noqa: BLE001 — surfaced in the window
            report = Report(source=str(book.source), output=destination)
            report.add(
                "gui", Level.ERROR, "gui.unexpected-failure",
                values={"error": f"{type(exc).__name__}: {exc}"},
            )
            book.status = BookStatus.FAILED
            book.error = f"{type(exc).__name__}: {exc}"
            book.report_text = report.to_text(self.language)

    @staticmethod
    def destination_for(source: pathlib.Path, folder: "pathlib.Path | None", kepub: bool) -> str:
        return destination_for(source, folder, kepub)

    def _absorb(self, book: BookItem, result, *, plan_only: bool) -> None:
        """Turn one `Result` into the row a person reads."""
        from ...pipeline import Status
        from ...report import Level

        report = result.report
        self._reports[str(book.source)] = report
        status = getattr(result, "status", None)
        book.fixed = report.count(Level.FIX)
        book.kept = report.count(Level.PRESERVED)
        book.issues = report.count(Level.ERROR) + report.count(Level.WARN)
        book.report_text = report.to_text(self.language)
        book.categories = self._categories(report)
        if status is not None and not status.wrote_a_file:
            book.status = BookStatus.BLOCKED if status is Status.BLOCKED else BookStatus.FAILED
            book.error = self._first_problem(report)
            book.output = None
            return
        book.output = None if plan_only else (
            pathlib.Path(result.output_path) if result.output_path else None
        )
        book.status = BookStatus.ATTENTION if report.count(Level.ERROR) else BookStatus.DONE
        if book.status is BookStatus.ATTENTION:
            book.error = self._first_problem(report)

    def _first_problem(self, report) -> str:
        from ...report import Level

        for finding in report.sorted_findings():
            if finding.level in (Level.ERROR, Level.WARN):
                return report.headline(finding, self.language).partition("\n")[0]
        return ""

    #: Stage name → the plain-language category it belongs to. Stages this
    #: table does not name land in "structure", which is what they are.
    CATEGORY_OF = {
        "navigation": "navigation", "nav": "navigation", "toc": "navigation",
        "style": "style", "typography": "style", "fonts": "style", "font_subset": "style",
        "images": "style", "cascade": "style",
        "epubcheck": "validation", "validate": "validation", "render": "validation",
        "package": "validation", "balance": "validation",
        "content": "text", "hyphens": "text", "paragraphs": "text",
        "substitutions": "text", "footnotes": "text", "pdf": "text",
        "metadata": "metadata", "opf": "metadata", "accessibility": "metadata",
    }

    def _categories(self, report) -> "tuple[ChangeCategory, ...]":
        """What changed, grouped the way a person would group it.

        Not by stage: "hyphens" and "substitutions" are one thing to a reader
        — the words changed — and three to the program.
        """
        from ...report import Level
        from ..strings import tr

        grouped: dict[str, list[str]] = {}
        for finding in report.sorted_findings():
            if finding.level not in (Level.FIX, Level.PRESERVED):
                continue
            name = self.CATEGORY_OF.get(finding.stage, "structure")
            if finding.level is Level.PRESERVED:
                name = "kept"
            line = report.headline(finding, self.language).partition("\n")[0]
            lines = grouped.setdefault(name, [])
            if line not in lines and len(lines) < 4:
                lines.append(line)
        order = ("navigation", "style", "text", "structure", "metadata", "validation", "kept")
        glyphs = {
            "navigation": "book", "style": "text", "text": "text", "structure": "folder",
            "metadata": "tag", "validation": "shield", "kept": "shield",
        }
        return tuple(
            ChangeCategory(glyphs[name], tr(f"shell.changes.{name}"), tuple(grouped[name]))
            for name in order if name in grouped
        )

    # -- what the results screen offers -----------------------------------
    def export_report(self, book: BookItem, destination: pathlib.Path) -> None:
        """Save one book's report: JSON if the name says so, else the text."""
        target = pathlib.Path(destination)
        report = self._reports.get(str(book.source))
        if target.suffix.lower() == ".json" and report is not None:
            target.write_text(report.to_json(self.language), encoding="utf-8")
            return
        target.write_text(book.report_text, encoding="utf-8")

    def export_batch(self, books, destination: pathlib.Path) -> None:
        """Every book of the run in one file — the old window's Ctrl+Shift+S.

        The question a batch raises is which of thirty books needs attention,
        and opening thirty files to answer it is slower than not asking.
        """
        from ...report import batch_to_json

        reports = [
            self._reports[str(book.source)] for book in books
            if str(book.source) in self._reports
        ]
        target = pathlib.Path(destination)
        if not reports:
            target.write_text("[]", encoding="utf-8")
            return
        target.write_text(batch_to_json(reports, self.language), encoding="utf-8")

    def reveal(self, path: pathlib.Path) -> None:
        """Open a folder in the system's file manager."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = pathlib.Path(path)
        folder = target if target.is_dir() else target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def defaults_for(self, preset: Preset) -> dict:
        from ...validate import find_epubcheck

        return defaults_from_policy(preset, epubcheck=find_epubcheck() is not None)


class DemoBackend:
    """Deterministic data for tests, screenshots and the empty-handed demo.

    It is not a mock of the engine: it is the *interface's* idea of a backend,
    which is exactly what a page should be testable against.
    """

    #: Deliberately generic: this repository is public (S-06), and a demo that
    #: ships three real titles is three titles somebody can read off a
    #: screenshot. They are descriptions of kinds of book, not anybody's book.
    TITLES = ("Powieść przykładowa", "Zbiór opowiadań", "Poradnik techniczny")

    def __init__(self, language: str = "pl") -> None:
        self.language = language

    def analyse(self, paths, *, progress=None, cancelled=None) -> "list[BookItem]":
        from ..strings import tr

        books = []
        chosen = list(paths) or [pathlib.Path(f"{title}.epub") for title in self.TITLES]
        for index, path in enumerate(chosen, start=1):
            source = pathlib.Path(path)
            if progress is not None:
                progress(Progress(index, len(chosen), source.stem, "analysis"))
            books.append(
                BookItem(
                    source=source,
                    title=source.stem.replace("_", " "),
                    author="—",
                    kind=source.suffix.lstrip(".").upper() or "EPUB",
                    size=1_800_000 + index * 300_000,
                    status=BookStatus.READY,
                    summary=tr("shell.analysis.summary", version="2.0", resources=120, spine=18),
                )
            )
        return books

    def defaults_for(self, preset: Preset) -> dict:
        return defaults_from_policy(preset)

    def rebuild(self, plan: RebuildPlan, books, *, progress=None, cancelled=None,
                book_done=None, resolver=None) -> BatchOutcome:
        from ..strings import tr

        chosen = [book for book in books if book.chosen]
        for index, book in enumerate(chosen):
            if cancelled is not None and cancelled():
                for rest in chosen[index:]:
                    rest.status = BookStatus.CANCELLED
                return BatchOutcome(tuple(chosen), cancelled=True, destination=plan.destination)
            if progress is not None:
                progress(Progress(index, len(chosen), book.title, "rebuild"))
            book.fixed = 4 + index * 3
            book.kept = index
            book.issues = 2 if index == 1 else 0
            book.status = BookStatus.ATTENTION if book.issues else BookStatus.DONE
            folder = plan.destination or book.source.parent
            book.output = pathlib.Path(folder) / f"{book.source.stem}.forged.epub"
            book.report_text = f"{book.title}\n{'-' * len(book.title)}\n(demo)"
            book.categories = (
                ChangeCategory("book", tr("shell.changes.navigation"), (tr("shell.changes.none"),)),
            )
            if book_done is not None:
                book_done(index, book)
        return BatchOutcome(tuple(chosen), destination=plan.destination)

    @staticmethod
    def destination_for(source: pathlib.Path, folder: "pathlib.Path | None", kepub: bool) -> str:
        return destination_for(source, folder, kepub)

    def export_report(self, book: BookItem, destination: pathlib.Path) -> None:
        pathlib.Path(destination).write_text(book.report_text, encoding="utf-8")

    def export_batch(self, books, destination: pathlib.Path) -> None:
        pathlib.Path(destination).write_text(
            "\n\n".join(book.report_text for book in books), encoding="utf-8"
        )

    def reveal(self, path: pathlib.Path) -> None:
        return None
