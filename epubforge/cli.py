"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys

from rich.console import Console
from rich.table import Table

from . import compat, version_string, watermark
from .pipeline import Status, rebuild, rebuild_all
from .plan import describe, plan_batch
from .policy import GATES, Policy
from .reader import EpubReadError, read_epub
from .quips import quip_for
from . import rules
from .report import Level, batch_to_json, Report
from . import validate as validate_module
from .validate import validate

LEVEL_STYLE = {
    Level.ERROR: "bold red",
    Level.WARN: "yellow",
    Level.PRESERVED: "cyan",
    Level.FIX: "green",
    Level.INFO: "dim",
}


def collect_inputs(raw_inputs: list[str]) -> list[str]:
    found: list[str] = []
    for entry in raw_inputs:
        if os.path.isdir(entry):
            for root, _, files in os.walk(entry):
                found.extend(
                    os.path.join(root, name) for name in sorted(files) if name.lower().endswith(".epub")
                )
        elif os.path.isfile(entry):
            found.append(entry)
        else:
            raise SystemExit(f"no such file or directory: {entry}")
    return found


def _source_date_epoch() -> str | None:
    """Honour the reproducible-builds convention, when it is set.

    Every ZIP entry already carries a fixed timestamp, so `dcterms:modified` is
    the last thing standing between two runs on one input and identical bytes.
    `SOURCE_DATE_EPOCH` is the established way to ask for that, and costs
    nothing when it is unset.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw.isdigit():
        return None
    import datetime as dt

    return dt.datetime.fromtimestamp(int(raw), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_policy(args: argparse.Namespace) -> Policy:
    preset = "strict" if args.strict else ("minimal" if args.minimal else "preserve")
    policy = Policy.preset(preset)
    if args.no_ncx:
        policy.write_ncx = False
    if args.strip_scripts:
        policy.strip_scripts = True
    if args.keep_dead:
        policy.remove_dead = False
    if args.remove_dead:
        policy.remove_dead = True
    if args.drop_orphans:
        policy.drop_orphans = True
    if args.keep_layout:
        policy.reorganize_files = False
    if args.keep_junk:
        policy.remove_junk = False
    if getattr(args, "reproducible", False):
        policy.reproducible = True
    # `None` means "whatever the mode says", which is not the same as "off" —
    # the preset already chose, and a default of "off" here would quietly
    # disarm strict's gate for everybody who never passes the flag.
    if getattr(args, "gate", None) is not None:
        policy.validate_before_publish = args.gate
    if args.keep_watermark_markup:
        policy.watermarks = "keep"
    if args.watermarks:
        policy.watermarks = args.watermarks
    if args.typography:
        policy.typography = True
    if args.no_a11y_metadata:
        policy.accessibility_metadata = False
    if args.claim_conformance:
        policy.claim_conformance = args.claim_conformance
    if args.compat:
        # Accept both --compat kindle --compat kobo and --compat kindle,kobo.
        names = [part for entry in args.compat for part in entry.split(",") if part.strip()]
        policy.compat_profiles = tuple(dict.fromkeys(name.strip().lower() for name in names))
    modified = getattr(args, "modified", None) or _source_date_epoch()
    if modified:
        policy.modified_override = modified
    if args.language:
        policy.default_language = args.language
        policy.metadata_overrides["language"] = args.language
    for field in ("title", "author", "publisher", "series"):
        value = getattr(args, field, None)
        if value:
            policy.metadata_overrides[field] = value
    return policy


def _default_language() -> str:
    """Which language the console speaks when nobody said.

    The window remembers a choice and the command line has nowhere to keep one,
    so it borrows the window's — a person who set the interface to Polish did
    not mean "Polish, except on the command line". Failing that, the locale;
    failing that, English.
    """
    try:  # The GUI's settings file, read without importing Qt.
        from PySide6.QtCore import QSettings

        stored = QSettings("EPUB-Forge", "EPUB-Forge").value("language")
        if stored in rules.CATALOGUES:
            return str(stored)
    except Exception:  # noqa: BLE001 — no Qt, no settings, no problem
        pass
    locale = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "")[:2].lower()
    return locale if locale in rules.CATALOGUES else "en"


def print_report(console: Console, report: Report, verbose: bool, language: str = "en") -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("level", width=9)
    table.add_column("stage", width=12)
    table.add_column("finding")

    hidden = 0
    for finding in report.sorted_findings():
        if not verbose and finding.level is Level.INFO:
            hidden += 1
            continue
        location = f" [dim]{finding.location}[/dim]" if finding.location else ""
        paragraph = report.detail_for(finding, language)
        detail = f"\n  [dim]{paragraph}[/dim]" if paragraph and verbose else ""
        headline, _, original = report.headline(finding, language).partition("\n")
        beneath = f"\n  [dim]{original}[/dim]" if original else ""
        table.add_row(
            f"[{LEVEL_STYLE[finding.level]}]{finding.level.value}[/]",
            finding.stage,
            f"{headline}{location}{beneath}{detail}",
        )
    if table.row_count:
        console.print(table)
    if hidden:
        console.print(f"[dim]{hidden} informational finding(s) hidden; use -v to show them.[/dim]")


def summarize(console: Console, report: Report) -> None:
    counts = {level: report.count(level) for level in Level}
    parts = [
        f"[green]{counts[Level.FIX]} fixed[/]",
        f"[cyan]{counts[Level.PRESERVED]} preserved[/]",
        f"[yellow]{counts[Level.WARN]} warnings[/]",
        f"[bold red]{counts[Level.ERROR]} errors[/]",
    ]
    console.print("  " + " · ".join(parts))

    # BA-2026-003, in one line. The full balance sheet goes to the JSON report;
    # what belongs on a terminal is the number somebody would want before
    # overwriting their only copy — how much of this cannot be put back.
    if report.changes:
        undoable = len(report.irreversible())
        line = f"  [dim]{len(report.changes)} zmian w bilansie"
        if undoable:
            line += f", [/][yellow]{undoable} nieodwracalnych[/]"
        else:
            line += ", wszystkie odwracalne[/]"
        console.print(line)

    # Decoration, never a substitute for the counts above, and silent whenever
    # something went wrong.
    remark = quip_for(report, os.environ.get("EPUBFORGE_LANG", "pl")[:2])
    if remark:
        console.print(f"  [dim italic]{remark}[/]")


#: What the shell learns from a run. Zero means "the file is good"; anything
#: else means somebody has to look. Before 0.1.7 a book that produced an ERROR
#: still exited 0 unless --strict-exit was passed, so an automated pipeline read
#: a damaged result as a success.
EXIT_OK = 0
EXIT_NOT_WRITTEN = 1
EXIT_WRITTEN_WITH_PROBLEMS = 2

#: Which outcome a batch reports when its books disagree. Ranked rather than
#: compared numerically, because the numbers are an interface for the shell and
#: not a severity scale: "nothing was written" is the worse news, and it is 1.
_SEVERITY = {EXIT_OK: 0, EXIT_WRITTEN_WITH_PROBLEMS: 1, EXIT_NOT_WRITTEN: 2}


class TerminalAsk:
    """The `--ask` resolver: the window's question, at a terminal.

    The window is where this feature belongs and where the owner will use it.
    It is here as well because the alternative is a rule that only holds when
    somebody is looking at a GUI — strict mode refuses a book over an
    unresolvable reference, and from a shell there would be no way to answer,
    only a way to give up. A script that pipes input gets no questions at all:
    `isatty` is the test for whether anybody is there.
    """

    def __init__(self, console: Console):
        self.console = console

    def resolve(self, question):
        from . import references

        if not sys.stdin.isatty():  # pragma: no cover - depends on the terminal
            return None
        self.console.print()
        self.console.rule("[bold]a link nothing here can resolve")
        self.console.print(f"  [dim]in[/] {question.document}")
        self.console.print(f"  [dim]points at[/] {question.reference}")
        if question.text:
            self.console.print(f'  [dim]link text[/] "{question.text}"')
        for index, candidate in enumerate(question.candidates[:40], start=1):
            self.console.print(f"    [cyan]{index:>3}[/] {candidate}")
        if len(question.candidates) > 40:  # pragma: no cover - long documents
            self.console.print(f"    [dim]… and {len(question.candidates) - 40} more[/]")
        self.console.print(
            "  [dim]number = point the link there · d = top of the document · "
            "Enter = leave it · a = leave every remaining one[/]"
        )
        try:
            answer = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - depends on the terminal
            self.console.print()
            return references.Decision(references.KEEP, apply_to_all=True)
        if answer.lower() == "d":
            return references.Decision(references.POINT_AT_DOCUMENT)
        if answer.lower() == "a":
            return references.Decision(references.KEEP, apply_to_all=True)
        if answer.isdigit() and 1 <= int(answer) <= len(question.candidates):
            return references.Decision(
                references.REPOINT, fragment=question.candidates[int(answer) - 1]
            )
        return references.Decision()


def _worse(current: int, candidate: int) -> int:
    return candidate if _SEVERITY[candidate] > _SEVERITY[current] else current


def command_build(args: argparse.Namespace) -> int:
    console = Console(stderr=False)
    inputs = collect_inputs(args.inputs)
    if not inputs:
        console.print("[yellow]No .epub files found.[/]")
        return 1

    policy = build_policy(args)
    output_dir = args.output
    if len(inputs) > 1 and output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Every destination is settled before the first book is touched. Deciding
    # them one at a time is how two books with one filename used to become one
    # book, silently, with a zero exit code.
    batch = plan_batch(inputs, output_dir)

    for collision in batch.collisions:
        console.print(f"[red]Two or more books would be written to:[/] {collision.destination}")
        for claimant in collision.sources:
            console.print(f"    [dim]{claimant}[/]")
    for offender in batch.self_targets:
        console.print(f"[red]Refusing to overwrite the source file:[/] {offender}")
    if not batch.ok:
        console.print(
            "\n  [dim]Nothing was written. Give each book its own destination, "
            "or write to a folder that mirrors the source tree.[/]"
        )
        return EXIT_NOT_WRITTEN

    if args.dry_run:
        for line in describe(batch):
            console.print(line, highlight=False)
        return EXIT_OK

    if batch.occupied and not args.force:
        console.print("[red]These destinations already exist:[/]")
        for existing in batch.occupied:
            console.print(f"    [dim]{existing}[/]")
        console.print(
            "\n  [dim]Nothing was written. Pass --force to replace them, "
            "or -o to write elsewhere.[/]"
        )
        return EXIT_NOT_WRITTEN

    exit_code = 0
    collected: list = []
    for job in batch.jobs:
        source, destination = job.source, job.destination

        console.rule(f"[bold]{os.path.basename(source)}")
        resolver = TerminalAsk(console) if args.ask else None
        # `rebuild_all` is `rebuild` for a book with one rendition, which is
        # every book but a handful; where a container offers several it writes
        # each into its own file, which is the owner's decision on F-025.
        produced = (
            [rebuild(source, destination, policy, resolver=resolver)]
            if args.first_rendition_only
            else rebuild_all(source, destination, policy, resolver=resolver)
        )
        if len(produced) > 1:
            console.print(
                f"  [cyan]{len(produced)} renditions[/] — each rebuilt into its own file"
            )
        result = produced[0]
        for extra in produced[1:]:
            if extra.status.wrote_a_file:
                console.print(f"  [bold green]written[/] {extra.output_path}")
            else:
                console.print(f"  [bold red]not written[/] {extra.output_path}")
                exit_code = _worse(exit_code, EXIT_NOT_WRITTEN)

        if args.check and result.output_path:
            validate(
                result.output_path,
                result.report,
                content_untouched=not policy.rewrite_content,
            )

        print_report(console, result.report, args.verbose, args.report_language)
        summarize(console, result.report)

        if result.status.wrote_a_file:
            size = os.path.getsize(result.output_path)
            if result.status is Status.SUCCEEDED:
                console.print(f"  [bold green]written[/] {destination} ({size / 1024:.0f} KiB)")
            else:
                # Written, but carrying errors. Saying only "written" here is how
                # a book with an unreadable image got reported as a success.
                console.print(
                    f"  [bold yellow]written with errors[/] {destination} ({size / 1024:.0f} KiB)"
                )
        else:
            reason = "refused" if result.status is Status.BLOCKED else "not written"
            console.print(f"  [bold red]{reason}[/] — see the report above")
            exit_code = _worse(exit_code, EXIT_NOT_WRITTEN)

        if args.report:
            if os.path.isdir(args.report):
                report_path = os.path.join(
                    args.report, f"{os.path.basename(destination)}.json"
                )
                with open(report_path, "w", encoding="utf-8") as handle:
                    handle.write(result.report.to_json(args.report_language))
            else:
                # Collected and written once at the end. Writing each book to
                # the same path in turn left only the last one, which looked
                # like a report and was a report about a different book.
                collected.append(result.report)

        if result.status is Status.SUCCEEDED_WITH_PROBLEMS:
            exit_code = _worse(exit_code, EXIT_WRITTEN_WITH_PROBLEMS)
        elif args.strict_exit and result.report.count(Level.WARN):
            exit_code = _worse(exit_code, EXIT_WRITTEN_WITH_PROBLEMS)

    if collected:
        # One book keeps the shape a single report has always had; several get
        # the batch document, whose whole point is answering "which of these
        # needs me" without opening them one at a time.
        payload = (
            collected[0].to_json(args.report_language)
            if len(collected) == 1
            else batch_to_json(collected, args.report_language)
        )
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(payload)

    return exit_code


def command_inspect(args: argparse.Namespace) -> int:
    console = Console()
    for source in collect_inputs(args.inputs):
        report = Report(source=source)
        console.rule(f"[bold]{os.path.basename(source)}")
        try:
            book = read_epub(source, report)
        except EpubReadError as exc:
            console.print(f"[red]unreadable:[/] {exc}")
            continue

        metadata = book.metadata
        table = Table(show_header=False, box=None)
        table.add_row("version", book.source_version)
        table.add_row("title", metadata.title)
        table.add_row("authors", ", ".join(c.name for c in metadata.creators) or "—")
        table.add_row("language", metadata.language or "[red]missing[/]")
        identifier = metadata.primary_identifier
        table.add_row("identifier", identifier.value if identifier else "[red]missing[/]")
        table.add_row("resources", str(len(book.resources)))
        table.add_row("spine items", str(len(book.spine)))
        table.add_row("toc entries", str(sum(1 for root in book.toc for _ in root.walk())))
        table.add_row("cover", book.cover_path or "[yellow]not detected[/]")
        table.add_row("nav document", book.nav_path or "[yellow]none (EPUB 2 style)[/]")
        table.add_row("obfuscated fonts", str(len(book.encrypted)) if book.encrypted else "no")
        table.add_row("DRM", "[red]yes[/]" if book.has_drm else "no")
        console.print(table)
        print_report(console, report, args.verbose)
    return 0


def command_check(args: argparse.Namespace) -> int:
    console = Console()
    exit_code = 0
    for source in collect_inputs(args.inputs):
        report = Report(source=source)
        result = validate(source, report)
        console.rule(f"[bold]{os.path.basename(source)}")
        if not result.available:
            console.print("[yellow]EPUBCheck is not installed.[/] Set EPUBCHECK_JAR or install epubcheck.")
            return 3
        if result.clean:
            console.print(f"[green]valid[/] — {result.warnings} warning(s)")
        else:
            console.print(f"[red]invalid[/] — {result.fatal} fatal, {result.errors} error(s)")
            for message in result.messages[:40]:
                console.print(f"  {message}")
            exit_code = 2
    return exit_code



def command_health(args: argparse.Namespace) -> int:
    """Is this file whole — asked of the bytes, not of the archive's own claims.

    A ZIP's central directory sits at the end of the file and lists what the
    archive says it holds. A truncated download can leave that list perfectly
    intact, so the only way to learn that an entry is gone is to decompress it.
    That is what this does, which is why it costs about what reading the book
    costs and why it is worth running on the day the books arrive rather than
    two years later.
    """
    from . import repair

    console = Console()
    worst = EXIT_OK
    for path in collect_inputs(args.inputs):
        health = repair.inspect(path)
        if health.healthy:
            console.print(f"  [green]całe[/] {health.summary()}")
            continue
        worst = _worse(worst, EXIT_NOT_WRITTEN)
        console.print(f"  [bold red]uszkodzone[/] {health.summary()}")
        if health.unreadable:
            console.print(f"      {health.unreadable}")
        for entry in health.damaged:
            console.print(f"      {entry.name} — {entry.reason}")
    if worst != EXIT_OK:
        console.print(
            "\n[dim]Uszkodzony plik naprawia się pobraniem go ponownie. "
            "Jeżeli masz dwie różne kopie, spróbuj `epubforge merge`.[/dim]"
        )
    return worst


def command_merge(args: argparse.Namespace) -> int:
    """One good book out of two damaged in different places.

    The only operation in this program that recovers anything rather than
    lowering a standard. Every entry is taken whole, byte for byte, from a copy
    that has it whole; nothing is reconstructed, nothing is averaged, and where
    two intact copies disagree it refuses rather than choosing.
    """
    from . import repair

    console = Console()
    plan = repair.plan_merge(args.inputs)
    if plan.refused:
        console.print(f"[bold red]nie da się scalić[/]: {plan.refused}")
        return EXIT_NOT_WRITTEN

    console.print(f"  wpisów do wzięcia: {len(plan.take)}")
    from_others = {
        name: source for name, source in plan.take.items() if source != plan.first
    }
    for name, source in sorted(from_others.items()):
        console.print(f"    [green]{name}[/] ← {os.path.basename(source)}")
    for name in plan.still_missing:
        console.print(f"    [bold red]{name}[/] — nie ma go w żadnej kopii")
    for name in plan.conflicts:
        console.print(f"    [yellow]{name}[/] — kopie różnią się i obie są całe")

    if not plan.usable:
        console.print(
            "\n[bold red]nic nie zapisano.[/] Scalenie ma sens tylko wtedy, gdy "
            "każdy wpis da się wziąć w całości z którejś kopii."
        )
        return EXIT_NOT_WRITTEN
    if not plan.repairs:
        console.print("\n[dim]pierwsza kopia ma wszystko — nie ma czego naprawiać[/dim]")

    # The person sees the plan before anything is written. `--yes` is for a
    # script that has already seen one; there is no default that writes without
    # somebody having looked.
    if not args.yes and not _confirmed(console):
        console.print("przerwane")
        return EXIT_NOT_WRITTEN

    result = repair.merge(args.inputs, args.output, plan)
    if not result.output_path:
        console.print(f"[bold red]nie zapisano[/]: {plan.refused or 'plan nie do użycia'}")
        return EXIT_NOT_WRITTEN
    console.print(
        f"  [bold green]zapisano[/] {result.output_path} "
        f"({result.written} wpisów, {plan.repairs} z drugiej kopii)"
    )
    return EXIT_OK


def _confirmed(console: Console) -> bool:
    """Ask, unless nobody is there to answer."""
    if not sys.stdin.isatty():
        return False
    try:
        return input("zapisać scaloną książkę? [t/N] ").strip().lower() in ("t", "tak", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def command_fidelity(args: argparse.Namespace) -> int:
    """Did the rebuild keep the book — asked of real files, not of a fixture.

    The audit's F-017/F-028 in the form a person can run: rebuild a book (or
    take one already rebuilt) and compare the two for the things a validator
    cannot see — text, structure, pictures, reading order.
    """
    import tempfile

    from . import fidelity as harness

    console = Console()
    # Its own mode rather than `build_policy`, which reads two dozen flags this
    # subcommand does not define. The question here is "did the rebuild keep the
    # book", and the mode is the only part of the rebuild that changes the answer.
    policy = Policy.preset(args.mode)
    exit_code = 0
    with tempfile.TemporaryDirectory() as room:
        for source in collect_inputs(args.inputs):
            console.rule(f"[bold]{os.path.basename(source)}")
            rebuilt = args.against
            if not rebuilt:
                rebuilt = os.path.join(room, os.path.basename(source))
                result = rebuild(source, rebuilt, policy)
                if not result.status.wrote_a_file:
                    console.print("[red]nothing was rebuilt to compare against[/]")
                    exit_code = _worse(exit_code, EXIT_NOT_WRITTEN)
                    continue
            measured = harness.compare(source, rebuilt)
            for check in measured.checks:
                style = "green" if check.ok else "bold red"
                console.print(f"  [{style}]{check.name}[/]" + (f" — {check.detail}" if check.detail else ""))
            if not measured.ok:
                exit_code = _worse(exit_code, EXIT_WRITTEN_WITH_PROBLEMS)
    return exit_code


def command_survey(args: argparse.Namespace) -> int:
    """What breaks across a whole library, ranked — not book by book."""
    from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

    from .survey import survey_library, to_json

    console = Console()
    inputs = collect_inputs(args.inputs)
    if not inputs:
        console.print("[yellow]No .epub files found.[/]")
        return 1

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("surveying", total=len(inputs))

        def tick(index: int, name: str) -> None:
            progress.update(task, completed=index, description=name[:40])

        survey = survey_library(
            inputs,
            Policy.preset("strict") if args.strict else None,
            deep=not args.shallow,
            with_names=args.with_names,
            on_book=tick,
        )

    console.print()
    console.print(f"[bold]{survey.books}[/] book(s) surveyed")
    versions = ", ".join(f"{v}: {n}" for v, n in survey.source_versions.most_common())
    if versions:
        console.print(f"  source versions: [dim]{versions}[/]")
    for label, items, style in (
        ("unreadable", survey.unreadable, "red"),
        ("crashed a stage", survey.crashed, "bold red"),
    ):
        if items:
            console.print(f"  [{style}]{len(items)} {label}[/]")
            for name, reason in items[:5]:
                shown = name if args.with_names else "(name withheld)"
                console.print(f"    [dim]{shown}: {reason}[/]")
    if survey.drm:
        console.print(f"  [yellow]{len(survey.drm)} carry DRM and were refused[/]")

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("books", justify="right", width=6)
    table.add_column("total", justify="right", width=6)
    table.add_column("level", width=9)
    table.add_column("stage", width=12)
    table.add_column("finding")
    for finding in survey.ranked()[: args.top]:
        if not args.verbose and finding.level is Level.INFO:
            continue
        table.add_row(
            str(finding.books),
            str(finding.occurrences),
            f"[{LEVEL_STYLE[finding.level]}]{finding.level.value}[/]",
            finding.stage,
            finding.message,
        )
    console.print()
    console.print(table)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(to_json(survey, with_names=args.with_names))
        console.print(f"\n  [green]written[/] {args.json}")
        if not args.with_names:
            console.print(
                "  [dim]No filenames are included. Pass --with-names if you want "
                "examples in it.[/]"
            )
    return 0


def command_corpus(args: argparse.Namespace) -> int:
    """Check a folder of books against recorded signatures, or record them."""
    import pathlib

    from .corpus import books_in, compare, summarise

    console = Console()
    books = pathlib.Path(args.books)
    signatures = pathlib.Path(args.signatures or (books / "expected"))
    if not books_in(books):
        console.print(f"[yellow]No .epub files in {books}[/]")
        return 1

    def announce(index: int, name: str) -> None:
        console.print(f"[dim][{index + 1}] {name[:60]}[/]", highlight=False)

    results = compare(
        books,
        signatures,
        record=args.record,
        on_book=announce,
        workers=getattr(args, "workers", None),
    )
    console.print()
    for result in results:
        if result.status == "changed":
            console.print(f"  [yellow]changed[/]  {result.book}")
            for line in result.differences:
                console.print(f"    [dim]{line}[/]")
        elif result.status == "failed":
            console.print(f"  [bold red]failed[/]   {result.book}")
            for line in result.differences:
                console.print(f"    [dim]{line}[/]")
        elif result.status == "new":
            console.print(f"  [cyan]new[/]      {result.book}")
        elif result.status == "duplicate":
            console.print(f"  [dim]same[/]     {result.book}")
            for line in result.differences:
                console.print(f"    [dim]{line}[/]")
    console.print(f"\n  {summarise(results, signatures)}")
    _report_streak(console, signatures)
    if args.record:
        console.print(f"  [green]signatures written to[/] {signatures}")
        return 0
    return 0 if all(r.ok for r in results) else 2


def _report_streak(console: "Console", signatures) -> None:
    """Say how many releases in a row came out clean, and what was passed over.

    Read from the ledger, never from memory. Counted only across releases that
    measured the same thing: every corpus run but one so far asked a larger
    question than the run before it, and a rule that reset the count on each of
    those made "green across three consecutive releases" a bar this project was
    forbidden to approach rather than one it could clear.
    """
    import json

    from .corpus import RUNS, green_streak, widenings

    ledger = signatures.parent / RUNS
    if not ledger.is_file():
        return
    try:
        history = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    streak = green_streak(history, minimum=30)
    grown = widenings(history, minimum=30)
    if streak:
        console.print(f"  green releases in a row: {len(streak)} ({', '.join(streak)})")
    else:
        console.print("  green releases in a row: none")
    if grown:
        console.print(f"  [dim]passed over as widenings: {', '.join(grown)}[/]")


def command_inventory(args: argparse.Namespace) -> int:
    """What the books are, as opposed to what the tool does to them."""
    import pathlib

    from .inventory import coverage, measure, summarise, to_json

    console = Console()
    inputs = collect_inputs(args.inputs)
    if not inputs:
        console.print("[yellow]No .epub files found.[/]")
        return 1

    books = []
    mapping = []
    for index, source in enumerate(inputs, 1):
        console.print(
            f"[dim][{index}/{len(inputs)}] {os.path.basename(source)[:60]}[/]", highlight=False
        )
        try:
            book = measure(pathlib.Path(source))
        except Exception as exc:  # noqa: BLE001 — one bad book must not stop the inventory
            import hashlib

            digest = hashlib.sha256(open(source, "rb").read()).hexdigest()[:16]
            from .inventory import Book

            book = Book(digest, 0.0, {"error": f"{type(exc).__name__}: {exc}"})
        books.append(book)
        mapping.append(f"{book.identifier}  {source}")

    console.print()
    console.print(summarise(books))

    with open(args.json, "w", encoding="utf-8") as handle:
        handle.write(to_json(books) + "\n")

    # The gap goes beside the measurements rather than only on screen: it is
    # the one part of an inventory that says what to do next, and a terminal
    # scrolls.
    gaps = os.path.splitext(args.json)[0] + "-coverage.json"
    with open(gaps, "w", encoding="utf-8") as handle:
        json.dump(coverage(books), handle, indent=2, ensure_ascii=False)
    console.print(f"[dim]coverage written to {gaps}[/dim]")
    console.print(f"\n  [green]written[/] {args.json}  [dim](safe to share — counts only)[/]")

    if args.map:
        with open(args.map, "w", encoding="utf-8") as handle:
            handle.write("\n".join(mapping) + "\n")
        console.print(
            f"  [green]written[/] {args.map}  "
            f"[yellow]keep this one[/][dim] — it is the only file tying a hash to a title[/]"
        )
    return 0


def command_compat(args: argparse.Namespace) -> int:
    """Print what each profile actually does, so --compat is not a guess."""
    console = Console()
    console.print(
        "Compatibility profiles are [bold]off by default[/]. Every measure is additive: "
        "it adds a file, a declaration or a legacy element, and never removes or "
        "rewrites what the book already had.\n"
    )
    for key in sorted(compat.PROFILES):
        profile = compat.PROFILES[key]
        console.rule(f"[bold]--compat {key}")
        console.print(f"  [dim]{profile.devices}[/]\n")
        for measure_key in profile.measures:
            measure = compat.MEASURES[measure_key]
            console.print(f"  [green]•[/] {measure.what}")
            console.print(f"    [dim]{measure.why}[/]")
            if measure.cost:
                console.print(f"    [yellow]costs:[/] {measure.cost}")
        console.print()
    return 0


def command_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import run
    except ImportError as exc:
        Console().print(
            f"[red]The GUI needs PySide6:[/] pip install 'epub-forge[gui]'\n[dim]{exc}[/dim]"
        )
        return 3
    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epubforge",
        description="Rebuild EPUB files into clean EPUB 3.3 while preserving their appearance.",
    )
    parser.add_argument("--version", action="version", version=f"epub-forge {version_string()}")
    parser.add_argument(
        "--separate-validator-process",
        action="store_true",
        help=(
            "start a new JVM for every book instead of holding one open. "
            "EPUBCheck spends about three and a half seconds compiling its "
            "schemas at every start, so this costs roughly four times the wall "
            "clock on a batch; it is here because 'turn the fast path off' is "
            "the first thing worth trying when a verdict looks wrong"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="rebuild one or more EPUB files")
    build.add_argument("inputs", nargs="+", help="EPUB files or directories to process")
    build.add_argument("-o", "--output", help="output file, or directory for batch runs")
    build.add_argument("-v", "--verbose", action="store_true", help="show informational findings")
    build.add_argument("--check", action="store_true", help="run EPUBCheck on the result")
    build.add_argument("--report", help="write a JSON report to this file or directory")
    build.add_argument(
        "--report-language",
        choices=sorted(rules.CATALOGUES),
        default=_default_language(),
        help=(
            "language for the console report and the description in --report "
            "(default: the window's setting, or LANG, or English)"
        ),
    )

    mode = build.add_mutually_exclusive_group()
    mode.add_argument(
        "--strict",
        action="store_true",
        help="prefer specification conformance over preserving appearance",
    )
    mode.add_argument(
        "--minimal",
        action="store_true",
        help="rebuild only the container; leave content files untouched",
    )

    build.add_argument("--no-ncx", action="store_true", help="omit the legacy NCX")
    build.add_argument("--strip-scripts", action="store_true", help="remove all scripting")
    build.add_argument(
        "--remove-dead",
        action="store_true",
        help="delete CSS rules and <span>s that have no effect (default in --strict)",
    )
    build.add_argument(
        "--keep-dead",
        action="store_true",
        help="keep them even under --strict; the report still counts them",
    )
    build.add_argument(
        "--drop-orphans",
        action="store_true",
        help=(
            "delete files nothing appears to reference. Off by default: the "
            "reference graph does not yet see srcset, <picture> or references "
            "made from inside an SVG, so a file still in use can be deleted"
        ),
    )
    build.add_argument("--keep-layout", action="store_true", help="keep original filenames and folders")
    build.add_argument(
        "--first-rendition-only",
        action="store_true",
        help=(
            "for a container offering several renditions, rebuild only the "
            "first into one file. By default each rendition is rebuilt into a "
            "file of its own, because each of them is a separate publication"
        ),
    )
    build.add_argument(
        "--reproducible",
        action="store_true",
        help=(
            "produce the same bytes every time: dcterms:modified is taken from "
            "the source instead of the clock, and a book with no identifier gets "
            "one derived from its content rather than a fresh uuid4"
        ),
    )
    build.add_argument(
        "--gate",
        choices=GATES,
        default=None,
        help=(
            "ask EPUBCheck before the file is published, not after. 'clean' "
            "refuses anything the validator calls invalid, whoever made it — "
            "the default in strict. 'no-new-errors' validates the source too "
            "and refuses only what this rebuild added, which is the honest "
            "form of the question when a book arrives broken. 'off' publishes "
            "and reports, the default everywhere else. A refusal never touches "
            "whatever is already at the destination"
        ),
    )
    build.add_argument(
        "--keep-junk",
        action="store_true",
        help=(
            "keep .DS_Store, Thumbs.db, __MACOSX/, .bak and the rest of what "
            "the archive picked up on the way. They are removed only where the "
            "book does not refer to them; this keeps them regardless"
        ),
    )
    build.add_argument(
        "--ask",
        action="store_true",
        help=(
            "stop and ask when a link names an anchor no document has, instead "
            "of leaving it as the publisher wrote it. The program never guesses "
            "at these: removing the fragment would point footnote seventeen at "
            "footnote one. Ignored when nothing is attached to the terminal"
        ),
    )
    build.add_argument(
        "--strict-exit",
        action="store_true",
        help="also exit non-zero on warnings (errors always do)",
    )
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="print where each book would be written, and write nothing",
    )
    build.add_argument(
        "--force",
        action="store_true",
        help="replace a file that already exists at the destination",
    )
    build.add_argument(
        "--watermarks",
        choices=list(watermark.MODES),
        help=(
            "what to do with a shop's opaque watermark token: keep it as found; "
            "consolidate its styling in place (default); gather it into the "
            "document's <head>, out of the text and its speech; or remove it. The "
            "last two take it out of the reading order, so neither is a default"
        ),
    )
    build.add_argument(
        "--keep-watermark-markup",
        action="store_true",
        help=argparse.SUPPRESS,  # superseded by --watermarks keep; still honoured
    )
    build.add_argument(
        "--typography",
        action="store_true",
        help=(
            "repair the text's typography: three dots become an ellipsis, and in "
            "Polish books single-letter conjunctions are bound to the word after "
            "them. Off by default and reached by no mode — this is the one pass "
            "that changes the text itself"
        ),
    )
    build.add_argument(
        "--no-a11y-metadata",
        action="store_true",
        help="skip the EPUB Accessibility 1.1 discovery metadata",
    )
    build.add_argument(
        "--claim-conformance",
        choices=["wcag-a", "wcag-aa", "wcag-aaa"],
        help=(
            "assert accessibility conformance in the metadata. EPUB-Forge cannot verify "
            "WCAG mechanically, so this records YOUR claim as publisher"
        ),
    )
    build.add_argument(
        "--compat",
        action="append",
        metavar="PROFILE",
        help=(
            "add concessions for a reader family: "
            + ", ".join(sorted(compat.PROFILES))
            + ". Repeatable, or comma-separated. Off by default, and every measure "
            "is additive — see 'epubforge compat' for what each one does"
        ),
    )
    build.add_argument(
        "--modified",
        metavar="ISO8601",
        help=(
            "pin dcterms:modified (e.g. 2026-01-01T00:00:00Z) instead of stamping now. "
            "Everything else in the output is already deterministic, so this makes two "
            "runs on the same book byte-identical. SOURCE_DATE_EPOCH is honoured too"
        ),
    )
    build.add_argument("--title", help="override dc:title")
    build.add_argument("--author", help="override the main dc:creator")
    build.add_argument("--publisher", help="override dc:publisher")
    build.add_argument("--series", help="set the series name")
    build.add_argument("--language", help="override dc:language (BCP 47)")
    build.set_defaults(func=command_build)

    inspect = subparsers.add_parser("inspect", help="report on a file without rebuilding it")
    inspect.add_argument("inputs", nargs="+")
    inspect.add_argument("-v", "--verbose", action="store_true")
    inspect.set_defaults(func=command_inspect)

    health = subparsers.add_parser(
        "health",
        help="check whether books are whole, by reading every entry",
    )
    health.add_argument("inputs", nargs="+", help="EPUB files or directories")
    health.set_defaults(func=command_health)

    merge_parser = subparsers.add_parser(
        "merge",
        help="one good book out of two copies damaged in different places",
    )
    merge_parser.add_argument("inputs", nargs="+", help="two or more copies; the first is the one being repaired")
    merge_parser.add_argument("-o", "--output", required=True, help="where to write the merged book")
    merge_parser.add_argument("--yes", action="store_true", help="skip the confirmation, for a script that has already seen the plan")
    merge_parser.set_defaults(func=command_merge)

    check = subparsers.add_parser("check", help="run EPUBCheck against existing files")
    check.add_argument("inputs", nargs="+")
    check.set_defaults(func=command_check)

    fidelity_command = subparsers.add_parser(
        "fidelity",
        help="compare a book with its rebuild: text, structure, pictures, reading order",
    )
    fidelity_command.add_argument("inputs", nargs="+")
    fidelity_command.add_argument(
        "--mode",
        choices=("preserve", "strict", "minimal"),
        default="preserve",
        help="which rebuild to compare against (default: preserve)",
    )
    fidelity_command.add_argument(
        "--against",
        metavar="FILE",
        help="an already-rebuilt file to compare with; without it, one is built in a temporary folder",
    )
    fidelity_command.set_defaults(func=command_fidelity)

    survey = subparsers.add_parser(
        "survey",
        help="report what breaks across a whole library, ranked by how many books it affects",
    )
    survey.add_argument("inputs", nargs="+", help="EPUB files or directories")
    survey.add_argument("--json", metavar="FILE", help="also write the survey as JSON")
    survey.add_argument(
        "--top", type=int, default=40, help="how many findings to show (default 40)"
    )
    survey.add_argument("-v", "--verbose", action="store_true", help="include informational findings")
    survey.add_argument(
        "--shallow",
        action="store_true",
        help="read the books only, without running the full rebuild — much faster, sees less",
    )
    survey.add_argument(
        "--with-names",
        action="store_true",
        help=(
            "include book filenames as examples. Off by default: a survey is meant to be "
            "shareable, and a list of titles says more about your shelf than about the tool"
        ),
    )
    survey.add_argument("--strict", action="store_true", help="survey what strict mode would do")
    survey.set_defaults(func=command_survey)

    corpus = subparsers.add_parser(
        "corpus",
        help="check a folder of books against recorded signatures, or record them",
    )
    corpus.add_argument("books", help="folder holding the books")
    corpus.add_argument(
        "--signatures",
        help="where the signatures live (default: an 'expected' folder beside the books)",
    )
    corpus.add_argument(
        "--record",
        action="store_true",
        help="rewrite the signatures from this run, after showing what moved",
    )
    corpus.add_argument(
        "--workers",
        type=int,
        metavar="N",
        help="how many books to measure at once (default: one per core, at most 8)",
    )
    corpus.set_defaults(func=command_corpus)

    inventory = subparsers.add_parser(
        "inventory",
        help="measure what a library is made of: origins, damage and typography",
    )
    inventory.add_argument("inputs", nargs="+", help="EPUB files or directories")
    inventory.add_argument(
        "--json", default="spis.json", metavar="FILE", help="where to write the measurements"
    )
    inventory.add_argument(
        "--map",
        metavar="FILE",
        help=(
            "also write hash→filename, so you can find a book the measurements point at. "
            "This is the one file that names your books; it is not written unless asked for"
        ),
    )
    inventory.set_defaults(func=command_inventory)

    compat_parser = subparsers.add_parser(
        "compat", help="explain the reader-compatibility profiles and what each costs"
    )
    compat_parser.set_defaults(func=command_compat)

    gui = subparsers.add_parser("gui", help="launch the desktop interface")
    gui.set_defaults(func=command_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "separate_validator_process", False):
        os.environ[validate_module.ENV_SHARED] = "0"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
