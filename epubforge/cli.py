"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import sys

from rich.console import Console
from rich.table import Table

from . import __version__, compat
from .pipeline import rebuild
from .policy import Policy
from .reader import EpubReadError, read_epub
from .quips import quip_for
from .report import Level, Report
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
    if args.keep_orphans:
        policy.drop_orphans = False
    if args.keep_layout:
        policy.reorganize_files = False
    if args.keep_watermark_markup:
        policy.normalize_watermarks = False
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


def print_report(console: Console, report: Report, verbose: bool) -> None:
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
        detail = f"\n  [dim]{finding.detail}[/dim]" if finding.detail and verbose else ""
        table.add_row(
            f"[{LEVEL_STYLE[finding.level]}]{finding.level.value}[/]",
            finding.stage,
            f"{finding.message}{location}{detail}",
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

    # Decoration, never a substitute for the counts above, and silent whenever
    # something went wrong.
    remark = quip_for(report, os.environ.get("EPUBFORGE_LANG", "pl")[:2])
    if remark:
        console.print(f"  [dim italic]{remark}[/]")


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

    exit_code = 0
    for source in inputs:
        if output_dir and os.path.isdir(output_dir):
            stem = os.path.splitext(os.path.basename(source))[0]
            destination = os.path.join(output_dir, f"{stem}.epub")
        elif output_dir:
            destination = output_dir
        else:
            stem = os.path.splitext(source)[0]
            destination = f"{stem}.forged.epub"

        if os.path.abspath(destination) == os.path.abspath(source):
            console.print(f"[red]Refusing to overwrite the source file:[/] {source}")
            exit_code = 1
            continue

        console.rule(f"[bold]{os.path.basename(source)}")
        result = rebuild(source, destination, policy)

        if args.check and result.output_path:
            validate(result.output_path, result.report)

        print_report(console, result.report, args.verbose)
        summarize(console, result.report)

        if result.output_path:
            size = os.path.getsize(result.output_path)
            console.print(f"  [bold green]written[/] {destination} ({size / 1024:.0f} KiB)")
        else:
            console.print("  [bold red]not written[/] — see errors above")
            exit_code = 1

        if args.report:
            report_path = (
                os.path.join(args.report, f"{os.path.basename(destination)}.json")
                if os.path.isdir(args.report)
                else args.report
            )
            with open(report_path, "w", encoding="utf-8") as handle:
                handle.write(result.report.to_json())

        if not result.report.ok:
            exit_code = max(exit_code, 2 if args.strict_exit else 0)

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
    parser.add_argument("--version", action="version", version=f"epub-forge {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="rebuild one or more EPUB files")
    build.add_argument("inputs", nargs="+", help="EPUB files or directories to process")
    build.add_argument("-o", "--output", help="output file, or directory for batch runs")
    build.add_argument("-v", "--verbose", action="store_true", help="show informational findings")
    build.add_argument("--check", action="store_true", help="run EPUBCheck on the result")
    build.add_argument("--report", help="write a JSON report to this file or directory")

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
    build.add_argument("--keep-orphans", action="store_true", help="keep unreferenced files")
    build.add_argument("--keep-layout", action="store_true", help="keep original filenames and folders")
    build.add_argument("--strict-exit", action="store_true", help="exit non-zero when findings remain")
    build.add_argument(
        "--keep-watermark-markup",
        action="store_true",
        help="leave publisher watermark markup exactly as found (tokens are never removed either way)",
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

    check = subparsers.add_parser("check", help="run EPUBCheck against existing files")
    check.add_argument("inputs", nargs="+")
    check.set_defaults(func=command_check)

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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
