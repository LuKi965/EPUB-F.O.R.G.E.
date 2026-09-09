"""What the specialist tools actually do, with no window around it.

Three tools — the library survey, the diagnostics, the regression corpus — were
written as panels: the question, the widgets, the thread and the text that
comes out, all in one class. That was fine while there was one window. There
are two now, and a second copy of "what a survey prints" would drift from the
first within a release, so the work moved here and the panels became what they
should have been: a way of asking.

Nothing in this module imports Qt. Every function takes what it needs, reports
progress through a callback, and returns a `ToolAnswer` — the text a person
reads, the payload a Save button writes, and the one line that used to go to
the status bar. That is the whole contract, and it is what lets the same
survey run under the old window, the new one, and a test with no window at all.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from .strings import language, tr

#: What a long tool reports as it goes: how many done, how many there are, and
#: what it is working on. The same shape the old panels' `emit` had.
ProgressTick = "callable"


def _quietly(done: int, total: int, name: str) -> None:
    """The default tick: a tool run without anybody watching still runs."""


@dataclass
class ToolAnswer:
    """What a tool produced, in the four parts an interface needs.

    `text` is what the person reads. `payload` is what Save writes and is
    empty when there is nothing worth saving. `headline` is the one line that
    used to go to the status bar. `used` carries the one piece of state a
    corpus run leaves behind: which folder of signatures it compared against.

    `facts` is the structural summary the handoff asks for (F11): the few
    numbers a tool *already has* on its way to writing `text`, as
    `(label, value)` pairs. Filled by the tool that knows them and by nothing
    else — the audit is explicit that a summary must not be regexed back out
    of a paragraph written for a person, because a sentence that changes then
    silently empties a card.
    """

    text: str = ""
    payload: str = ""
    headline: str = ""
    suggestion: str = ""
    used: str = ""
    facts: "tuple[tuple[str, str], ...]" = ()


# --------------------------------------------------------------------------
# the library: two questions about a shelf, neither of them changing anything
# --------------------------------------------------------------------------

def books_on_the_shelf(folder: str) -> "list[str]":
    from ..cli import collect_inputs

    return collect_inputs([folder])


def survey_shelf(folder: str, *, with_names: bool = False, tick=_quietly) -> ToolAnswer:
    """What this program would repair across a whole library, and how often."""
    from ..survey import survey_library, to_json

    books = books_on_the_shelf(folder)
    total = len(books)
    result = survey_library(
        books, with_names=with_names, on_book=lambda index, name: tick(index, total, name)
    )
    return ToolAnswer(
        text=render_survey(result),
        payload=to_json(result, with_names=with_names),
        headline=tr("common.done", count=result.books),
        suggestion="przeglad.json",
        # Numbers `Survey` already holds, not numbers read back out of the
        # paragraph above (F11).
        facts=(
            (tr("shell.facts.books"), str(result.books)),
            (tr("shell.facts.unreadable"), str(len(result.unreadable))),
            (tr("shell.facts.findings"), str(len(result.findings))),
            (tr("shell.facts.crashed"), str(len(result.crashed))),
        ),
    )


def take_inventory(folder: str, *, tick=_quietly) -> ToolAnswer:
    """What these books *are*, and which families of them are thin on the shelf."""
    from ..inventory import coverage_report, measure, summarise, to_json

    books = books_on_the_shelf(folder)
    total = len(books)
    measured = []
    for index, path in enumerate(books):
        tick(index, total, os.path.basename(path))
        measured.append(measure(pathlib.Path(path)))
    # Coverage was written from the beginning and shown only by the command
    # line, which the person holding the library does not use. Which families
    # are short is the *question* the inventory answers; printing everything
    # but the answer was the wrong half.
    report = summarise(measured) + "\n\n" + coverage_report(measured, language())
    return ToolAnswer(
        text=report,
        payload=to_json(measured),
        headline=tr("common.done", count=len(measured)),
        suggestion="spis.json",
        facts=(
            (tr("shell.facts.books"), str(len(measured))),
            (tr("shell.facts.versions"),
             str(len({one.version for one in measured if one.version}))),
        ),
    )


def library(folder: str, *, inventory: bool = False, with_names: bool = False,
            tick=_quietly) -> ToolAnswer:
    """Either question, chosen by the caller rather than by two entry points."""
    if inventory:
        return take_inventory(folder, tick=tick)
    return survey_shelf(folder, with_names=with_names, tick=tick)


def render_survey(survey) -> str:
    lines = [tr("survey.books", count=survey.books), ""]
    versions = ", ".join(f"{v}: {n}" for v, n in survey.source_versions.most_common())
    if versions:
        lines.append(tr("survey.versions", versions=versions))
    # The reason, not just the count. "stage failures: 3" on screen and
    # nothing else is a dead end for whoever has the three books.
    for key, entries in (
        ("survey.unreadable", survey.unreadable),
        ("survey.crashed", survey.crashed),
    ):
        if not entries:
            continue
        lines.append(f"{tr(key)}: {len(entries)}")
        for name, reason in entries[:5]:
            lines.append(f"    {name}: {reason}")
    if survey.drm:
        lines.append(tr("survey.drm", count=len(survey.drm)))
    lines += [
        "",
        f"{tr('survey.head.books'):>6} {tr('survey.head.total'):>6}  "
        f"{tr('survey.head.level'):<10} {tr('survey.head.stage'):<14} "
        f"{tr('survey.head.finding')}",
        "",
    ]
    for finding in survey.ranked():
        lines.append(
            f"{finding.books:>6} {finding.occurrences:>6}  "
            f"{finding.level.value:<10} {finding.stage:<14} {finding.message}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# diagnostics: five questions, none of which changes a file
# --------------------------------------------------------------------------

def books_for(path: str) -> "list[str]":
    """One file, or every book in a folder."""
    from ..corpus import books_in

    if not path:
        return []
    place = pathlib.Path(path)
    if place.is_file():
        return [str(place)]
    return [str(book) for book in books_in(place)]


def describe(book: str) -> "list[str]":
    """What is actually in the file, before anything touches it."""
    from .. import memory
    from ..reader import EpubReadError, read_epub
    from ..report import Report

    report = Report(source=book)
    try:
        parsed = read_epub(book, report)
    except EpubReadError as exc:
        return [f"  nie da się odczytać: {exc}"]
    metadata = parsed.metadata
    identifier = metadata.primary_identifier
    rows = [
        ("wersja", parsed.source_version),
        ("tytuł", metadata.title or "—"),
        ("autorzy", ", ".join(c.name for c in metadata.creators) or "—"),
        ("język", metadata.language or "BRAK"),
        ("identyfikator", identifier.value if identifier else "BRAK"),
        ("zasoby", str(len(parsed.resources))),
        ("kolejność czytania", str(len(parsed.spine))),
        ("wpisy spisu treści", str(sum(1 for root in parsed.toc for _ in root.walk()))),
        ("okładka", parsed.cover_path or "nie wykryto"),
        ("nawigacja", parsed.nav_path or "brak (styl EPUB 2)"),
        ("zaciemnione fonty", str(len(parsed.encrypted)) if parsed.encrypted else "nie"),
        ("DRM", "TAK" if parsed.has_drm else "nie"),
        # Asked before the rebuild rather than found out during it. On a book
        # big enough to matter this is the difference between a line here and a
        # process the system kills without a word.
        ("pamięć", str(memory.check(book))),
    ]
    return [f"  {name:<20} {value}" for name, value in rows]


def compare_render(book: str) -> "list[str]":
    """Rebuild it and compare the two books as *pictures*.

    F-028. Everything else here reads the file; this one draws it. The answer
    when no browser is installed is a paragraph saying which browsers count and
    how to point at one, because "this needs something you do not have" is an
    answer and a disabled control is not.
    """
    from .. import render

    if render.find_renderer() is None:
        return ["  " + line for line in render.why_not().splitlines()]
    # Which engine drew this, said out loud. A result whose engine is not named
    # is a result about somebody's browser, and the person reading it has no
    # way to know that.
    lines = ["  " + line for line in render.describe().splitlines()] + [""]
    return lines + _rendered_pages(book)


def _rendered_pages(book: str) -> "list[str]":
    import tempfile

    from .. import render_fidelity
    from ..pipeline import rebuild
    from ..policy import Policy

    with tempfile.TemporaryDirectory() as room:
        destination = os.path.join(room, os.path.basename(book))
        result = rebuild(book, destination, Policy.for_measurement())
        if not result.status.wrote_a_file:
            return ["  nie udało się przebudować, więc nie ma czego porównać"]
        measured = render_fidelity.compare(book, destination)
        lines = [f"  {measured.summary()}"]
        for page in measured.pages:
            mark = "!!" if page.problems else ("··" if page.notes else "ok")
            lines.append(f"  {mark} {page}")
        return lines


def compare_fidelity(book: str) -> "list[str]":
    """Rebuild it into a temporary folder and compare the two.

    Nothing is written where anybody will find it: the question is about the
    rebuild, and the answer does not need the file kept. Everything this
    reports is something EPUBCheck has no opinion about.
    """
    import tempfile

    from .. import fidelity
    from ..pipeline import rebuild
    from ..policy import Policy

    with tempfile.TemporaryDirectory() as room:
        destination = os.path.join(room, os.path.basename(book))
        result = rebuild(book, destination, Policy.preset("preserve"))
        if not result.status.wrote_a_file:
            return ["  nie udało się przebudować, więc nie ma czego porównać"]
        measured = fidelity.compare(book, destination)
        return [f"  {check}" for check in measured.checks]


def check_health(book: str) -> "list[str]":
    """Every entry, actually decompressed. See `epubforge.repair`."""
    from .. import repair

    health = repair.inspect(book)
    if health.unreadable:
        return [f"  nie da się otworzyć jako archiwum: {health.unreadable}"]
    if not health.damaged:
        return [f"  całe — {len(health.entries)} plików w środku, wszystkie czytelne"]
    lines = [
        f"  USZKODZONE — {len(health.damaged)} z {len(health.entries)} plików "
        f"nie da się rozpakować:"
    ]
    lines.extend(f"    {entry.name} — {entry.reason}" for entry in health.damaged)
    lines.append(
        "    Naprawa: pobierz książkę ponownie. Jeżeli masz drugą, inaczej "
        "uszkodzoną kopię, scal je: epubforge merge kopia-a.epub kopia-b.epub -o cala.epub"
    )
    return lines


def validate_book(book: str) -> "list[str]":
    from ..report import Report
    from ..validate import SHARED, validate

    result = validate(book, Report(source=book))
    if not result.available:
        return ["  EPUBCheck nie jest dostępny"]
    lines = (
        [f"  poprawny — ostrzeżeń: {result.warnings}"]
        if result.clean
        else [
            f"  NIEPOPRAWNY — błędów krytycznych: {result.fatal}, błędów: {result.errors}",
            *(f"    {message}" for message in result.messages[:40]),
        ]
    )
    # Said out loud rather than kept inside. A batch that quietly went back to a
    # JVM per book is four times slower for a reason somebody would otherwise
    # have to guess at.
    if SHARED.reason:
        lines.append(f"  (osobny proces walidatora: {SHARED.reason})")
    return lines


#: The five questions, by the name the interface uses for them. A dictionary
#: rather than a chain of `elif`, so a control and its answer are one entry.
ANSWERS = {
    "inspect": describe,
    "validate": validate_book,
    "fidelity": compare_fidelity,
    "health": check_health,
    "render": compare_render,
}


def use_shared_validator(shared: bool) -> None:
    """Turn the one-process-per-batch validator on or off for this run."""
    from .. import validate as validate_module

    os.environ[validate_module.ENV_SHARED] = "1" if shared else "0"
    if not shared:
        validate_module.SHARED.stop()


def diagnose(books: "list[str]", question: str, *, shared: bool = True,
             tick=_quietly) -> ToolAnswer:
    """Ask one of the five questions of every book."""
    use_shared_validator(shared)
    return answer_for_each(books, ANSWERS[question], tick=tick)


def answer_for_each(books: "list[str]", answer, *, tick=_quietly) -> ToolAnswer:
    """Ask *answer* of every book, and lay the replies out under its name.

    Takes the function rather than its name so a caller that already has one —
    the old window picks it from a row of radio buttons — does not have to
    translate it into a string and back.
    """
    lines: list[str] = []
    for index, book in enumerate(books):
        tick(index, len(books), os.path.basename(book))
        lines.append(f"--- {os.path.basename(book)}")
        lines.extend(answer(book))
        lines.append("")
    text = "\n".join(lines)
    return ToolAnswer(
        text=text,
        payload=text,
        headline=tr("common.done", count=len(books)),
        suggestion="diagnostyka.txt",
        facts=(
            (tr("shell.facts.books"), str(len(books))),
            (tr("shell.facts.lines"), str(len(lines))),
        ),
    )


# --------------------------------------------------------------------------
# the corpus: a library keeping the tool honest
# --------------------------------------------------------------------------

def signatures_for(books: str, signatures: str = "") -> pathlib.Path:
    """Where the recorded answers live: chosen, or `expected` beside the books."""
    folder = pathlib.Path(books)
    return pathlib.Path(signatures) if signatures else folder / "expected"


def corpus_check(books: str, signatures: str = "", *, record: bool = False,
                 tick=_quietly) -> ToolAnswer:
    """Compare every book against what it did last time, or record what it does."""
    from ..corpus import books_in, compare

    folder = pathlib.Path(books)
    target = signatures_for(books, signatures)
    total = len(books_in(folder))
    results = compare(
        folder, target, record=record, on_book=lambda index, name: tick(index, total, name)
    )
    answer = render_corpus(results, target)
    answer.used = str(target)
    return answer


def render_corpus(results, signatures) -> ToolAnswer:
    from ..corpus import summarise

    labels = {
        "unchanged": tr("corpus.status.unchanged"),
        "changed": tr("corpus.status.changed"),
        "new": tr("corpus.status.new"),
        "failed": tr("corpus.status.failed"),
        "duplicate": tr("corpus.status.duplicate"),
    }
    lines: list[str] = []
    for result in results:
        if result.status == "unchanged":
            continue
        lines.append(f"{labels[result.status]:>10}  {result.book}")
        lines.extend(f"            {difference}" for difference in result.differences)

    summary = summarise(results, signatures)
    said = streak(signatures)
    if said:
        summary += "\n" + said
    return ToolAnswer(
        text=summary + ("\n\n" + "\n".join(lines) if lines else ""),
        headline=summary.splitlines()[0] if summary else "",
    )


def streak(signatures) -> str:
    """How many releases in a row came out clean, read from the ledger.

    Answering this from memory is how the family count came to be wrong, and
    the owner has been asking it from outside the program: he remembered three
    green metrics and watched the count go back to zero, with no way to check
    which of us was right. It is one file and two functions, and the person who
    owns the books is the person who should be able to read it without a
    checkout.
    """
    import json

    from ..corpus import RUNS, green_streak, widenings

    if signatures is None:
        return ""
    ledger = pathlib.Path(signatures).parent / RUNS
    if not ledger.is_file():
        return ""
    try:
        history = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    # The same floor the streak rule uses: a run over three books says nothing
    # about a corpus of ninety.
    clean = green_streak(history, minimum=30)
    grown = widenings(history, minimum=30)
    if clean:
        said = tr("corpus.streak", count=len(clean), releases=", ".join(clean))
    else:
        said = tr("corpus.streak.none")
    if grown:
        said += " " + tr("corpus.streak.widened", releases=", ".join(grown))
    return said


def build_edge_cases(folder: str, tick=_quietly) -> ToolAnswer:
    """The one family nobody can go and buy: build it."""
    from ..edge_cases import EDGES, build_edges

    tick(0, len(EDGES), tr("corpus.edges.working"))
    written = build_edges(folder)
    return render_edges(written)


def render_edges(written) -> ToolAnswer:
    from ..edge_cases import EDGES

    # What each file is for, in the language the window is speaking. Four
    # unfamiliar names appearing in a corpus folder is not an explanation.
    index = 2 if language() == "en" else 1
    what = {name: entry[index] for name, entry in EDGES.items()}
    headline = tr("corpus.edges.done", count=len(written))
    lines = [f"    {path.name:26} {what.get(path.stem, '')}" for path in written]
    return ToolAnswer(text=headline + "\n" + "\n".join(lines), headline=headline)


def fixtures_survey(folder: str = "", tick=_quietly) -> ToolAnswer:
    """Which of the purchased books the suite still cannot see.

    The chosen folder is searched as well as the configured shelves, so a
    person who has just pointed a tool at their library gets the answer for
    *that* library without setting an environment variable first.
    """
    from ..fixtures import ROLES, survey

    extra = pathlib.Path(folder) if folder and os.path.isdir(folder) else None
    tick(0, len(ROLES), tr("corpus.fixtures.working"))
    return render_fixtures(survey(extra=extra))


def render_fixtures(matches) -> ToolAnswer:
    from ..fixtures import BY_ID, explain

    lines: list[str] = []
    for match in matches:
        role = BY_ID[match.role]
        lines.append(explain(role))
        if match.found:
            lines.append(f"  {tr('corpus.fixtures.present')} — {match.path}")
        else:
            lines.append(f"  {tr('corpus.fixtures.missing')}")
            for candidate in match.candidates:
                lines.append("    " + tr("corpus.fixtures.similar", name=str(candidate)))
        lines.append("")
    absent = sum(1 for match in matches if not match.found)
    return ToolAnswer(
        text="\n".join(lines),
        headline=f"{len(matches) - absent}/{len(matches)} {tr('corpus.fixtures.present')}",
    )


def fixture_roles() -> "list[str]":
    from ..fixtures import BY_ID

    return list(BY_ID)


def assign_fixture(role: str, path: str) -> ToolAnswer:
    """Say that this file is the book that role has been waiting for."""
    from ..fixtures import record

    entry = record(role, pathlib.Path(path))
    said = tr("corpus.fixtures.done", role=role, name=os.path.basename(path))
    return ToolAnswer(text=f"{said}\nsha256:{entry['sha256']}", headline=said)
