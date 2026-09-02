"""Structured record of everything the rebuild changed, kept, or refused."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Level(str, Enum):
    INFO = "info"
    FIX = "fix"
    #: Standards deviation kept on purpose because removing it would alter rendering.
    PRESERVED = "preserved"
    WARN = "warn"
    ERROR = "error"


_ORDER = {Level.ERROR: 0, Level.WARN: 1, Level.PRESERVED: 2, Level.FIX: 3, Level.INFO: 4}

#: What each stage of the pipeline is *about*, said the way somebody who owns
#: books would say it rather than the way the code is organised. Pillar C:
#: "pojęcia tłumaczone, nie rzucane". A stage with no entry falls back to its
#: own name, which is ugly and honest — better than a summary that invents a
#: friendly word for something it has not been taught.
_SUMMARY_STAGES_PL = {
    "xhtml": "treść stron",
    "css": "arkusze stylów",
    "structure": "układ i nazwy plików",
    "navigation": "spis treści",
    "metadata": "metadane",
    "accessibility": "dostępność",
    "fonts": "fonty",
    "profile": "zgodność z czytnikami",
    "hyphens": "łączniki w słowach",
    "substitutions": "litera zapisana zamiast innej",
    "pictures": "opisy obrazów",
    "tables": "tabele",
    "reader": "odczyt źródła",
    "package": "pakiet książki",
    "render": "wygląd stron",
    "epubcheck": "walidator EPUBCheck",
    "encoding": "kodowanie znaków",
}
_SUMMARY_STAGES_EN = {
    "xhtml": "page content",
    "css": "stylesheets",
    "structure": "file layout and names",
    "navigation": "table of contents",
    "metadata": "metadata",
    "accessibility": "accessibility",
    "fonts": "fonts",
    "profile": "reading-system compatibility",
    "hyphens": "hyphens inside words",
    "substitutions": "one letter written for another",
    "pictures": "image descriptions",
    "tables": "tables",
    "reader": "reading the source",
    "package": "the book's package",
    "render": "how the pages look",
    "epubcheck": "the EPUBCheck validator",
    "encoding": "character encoding",
}

#: The summary's own sentences. Kept here rather than in `rules.py` because
#: they describe the *report*, not the book — nothing in them names a finding.
_SUMMARY_WORDS_PL = {
    "heading": "W skrócie",
    "healthy": "Książka jest zdrowa — nic nie wymaga Twojej uwagi.",
    "warned": (
        "Książka jest sprawna, ale {count} {count:sprawę warto|sprawy warto|spraw warto} "
        "obejrzeć — {count:jest ona|są one|są one} niżej, oznaczona jako WARN."
    ),
    "errors": (
        "Książka ma {count} {count:błąd|błędy|błędów}, {count:który|które|których} program "
        "nie umiał rozstrzygnąć sam — są niżej, oznaczone jako ERROR."
    ),
    "refused": (
        "Plik nie powstał. Program woli nie zapisać nic, niż zapisać książkę, "
        "o której nie umie powiedzieć, że jest cała — powód jest niżej."
    ),
    "fixed": "Naprawiono {count} {count:rzecz|rzeczy|rzeczy}, najwięcej w tym: {where}.",
    "kept": (
        "{count} {count:rzecz zostawiono|rzeczy zostawiono|rzeczy zostawiono} celowo — "
        "przy każdej stoi powód, dla którego zmiana należy do Ciebie, a nie do programu."
    ),
    "warnings": "{count} {count:sprawa jest|sprawy są|spraw jest} do obejrzenia.",
    "notes": "{count} {count:sprawa jest|sprawy są|spraw jest} tylko do wiadomości.",
    "answered": (
        "{count} {count:zmiana weszła|zmiany weszły|zmian weszło} na Twoją odpowiedź "
        "w pytaniach."
    ),
    "waiting": (
        "{count} {count:pytanie czeka|pytania czekają|pytań czeka} na Twoją odpowiedź — "
        "bez niej nic się przy nich nie zmienia."
    ),
}
_SUMMARY_WORDS_EN = {
    "heading": "In short",
    "healthy": "The book is healthy — nothing here needs your attention.",
    "warned": (
        "The book is sound, but {count} thing(s) are worth a look — they are below, "
        "marked WARN."
    ),
    "errors": (
        "The book carries {count} problem(s) the program could not settle on its own — "
        "they are below, marked ERROR."
    ),
    "refused": (
        "No file was written. The program would rather write nothing than write a book "
        "it cannot say is whole — the reason is below."
    ),
    "fixed": "{count} thing(s) were repaired, most of them in: {where}.",
    "kept": (
        "{count} thing(s) were deliberately left alone — each one carries the reason "
        "why that change is yours to make and not the program's."
    ),
    "warnings": "{count} thing(s) are worth a look.",
    "notes": "{count} thing(s) are there for information only.",
    "answered": "{count} change(s) went in on your answer to a question.",
    "waiting": (
        "{count} question(s) are waiting for your answer — until it comes, nothing "
        "about them changes."
    ),
}

#: Version of the JSON shape written by :meth:`Report.to_dict`. The moment
#: anything outside this project reads ``--report`` output, that shape is an
#: interface; stamping it costs one field and means a change can be announced
#: instead of guessed at.
#:
#: **5** — one field added: `in_short`, the summary sentences the text report
#: opens with (pillar C), so a front end shows the same words rather than
#: composing its own out of the counts. It is deliberately not called
#: `summary`: that name has meant the per-level counts since version 1, and
#: changing what an existing field means breaks a consumer without saying so.
#: `stats` also gains `questions_unanswered`. Nothing was removed.
#:
#: **3** — two fields added: `changes`, the balance sheet of high-risk
#: transformations (see :class:`Change`), and `change_summary` beside it.
#: Nothing was removed and no existing field changed meaning.
#:
#: **2** — `message` is now rendered from the catalogue rather than written at
#: the call site, so its English wording changed for most findings. `rule` did
#: not change and is the field to match on; that is what it is for. Two fields
#: were added: `description`, the finding in the language asked for, and
#: `detail_description`, the same for the paragraph beneath it. Nothing was
#: removed.
SCHEMA_VERSION = 5


class Action(str, Enum):
    """What a transformation did to the thing it names. A closed vocabulary.

    Closed on purpose: the 2026-08-14 baseline's BA-2026-003 is that the report
    says a great deal about *why* and almost nothing about *what*, in any form
    a machine can add up. "4 of 10 rules removed" is a sentence; a balance sheet
    needs the verb as a value.
    """

    REMOVED = "removed"
    REPLACED = "replaced"
    MOVED = "moved"
    ADDED = "added"
    #: Kept exactly as found, deliberately, where a rule said otherwise.
    CARRIED = "carried"
    #: Read back out of damage — a parser's reading rather than the file's own.
    RECONSTRUCTED = "reconstructed"


class Automation(str, Enum):
    """Who decided, which is the field that says how much to trust the change."""

    #: One correct answer, derived from the book. Re-running gives the same one.
    DETERMINISTIC = "deterministic"
    #: A judgement this program made. Right on the corpus; not provable.
    HEURISTIC = "heuristic"
    #: A person answered. See `references.py` and the window's dialog.
    ASKED = "asked"


class Risk(str, Enum):
    """What this could cost the reader if the decision behind it is wrong."""

    #: Nothing a reader can see: an id renamed with every reference repointed.
    NONE = "none"
    #: The page could look different.
    APPEARANCE = "appearance"
    #: Something a reader would go looking for might not be there.
    CONTENT = "content"


@dataclass
class Change:
    """One thing this rebuild did, as data rather than as a sentence.

    The audit asked for a machine-readable balance of every high-risk
    transformation, and this is the smallest shape that answers it: what was
    done, to what, from what to what, whether it can be undone from the output
    alone, who decided, and what it risks.

    Deliberately *not* every change. A ledger of all six thousand edits a rebuild
    makes is a log, and a log is what the findings already are. This is the
    subset the audit names — removal, reconstruction, relocation, text, the
    navigation and cover — because those are the ones where being wrong costs a
    reader something.
    """

    stage: str
    action: Action
    #: What was acted on: an archive path, a metadata property, an element.
    subject: str
    before: str = ""
    after: str = ""
    automation: Automation = Automation.DETERMINISTIC
    risk: Risk = Risk.NONE
    #: Whether the output alone carries what would be needed to put it back.
    #: A renamed file is reversible — the map is in the report. A deleted
    #: stylesheet rule is not.
    reversible: bool = True
    #: The finding that explains it, so the two are not two accounts of one
    #: event that can drift apart.
    rule: str = ""


@dataclass
class Finding:
    stage: str
    level: Level
    message: str
    location: str | None = None
    detail: str | None = None
    #: Stable identifier from :mod:`epubforge.rules`. The message is a rendering
    #: of this, not the other way round — see that module for why. Optional
    #: while the call sites are being converted; `test_rules.py` holds the
    #: conversion to a ratchet so it cannot stall unnoticed.
    rule: str | None = None
    #: The specifics the message states — how many entries, which file, which
    #: media type. Held apart from the sentence so a translation can state them
    #: too; without this a Polish report had to carry the English line
    #: underneath it or lose the numbers.
    values: dict = field(default_factory=dict)


@dataclass
class Report:
    source: str = ""
    output: str = ""
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)
    #: The input→output reconciliation — see :mod:`epubforge.balance`. `None`
    #: until the rebuild reaches the writer, which is also the only point at
    #: which both sides exist.
    balance: object = None
    #: The balance sheet — see :class:`Change`. Separate from `findings` because
    #: they answer different questions: a finding says why somebody should look,
    #: a change says what happened to the book.
    changes: list[Change] = field(default_factory=list)
    #: EPUBCheck's verdict on the bytes that were published, once something has
    #: asked for it. Set by the publication gate, which validates the staged file
    #: immediately before it is renamed into place — the same bytes under a
    #: different name.
    #:
    #: Here so that nothing validates them a second time. In strict mode the
    #: window did exactly that: the gate ran EPUBCheck, the "check the result"
    #: pass ran it again on the finished file, and the report carried the same
    #: `epubcheck.clean` line twice. Measured at about four and a half seconds
    #: per book, spent to learn a thing already known.
    validated: object = None

    def add(
        self,
        stage: str,
        level: Level,
        rule: str,
        *,
        values: dict | None = None,
        location: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Record a finding by its identifier.

        The sentence is not passed in. It used to be, and then it lived twice —
        once at the call site and once in the catalogue that translates it —
        which is two places for one fact and therefore a place for them to
        disagree. The catalogue is the source; `message` is the English
        rendering of it, and `detail` the paragraph beneath.

        A caller may still pass `detail` for the eight findings whose paragraph
        is data rather than prose — a list of names, a generated identifier —
        where there is nothing to catalogue.
        """
        from . import rules

        values = values or {}
        self.findings.append(
            Finding(
                stage,
                level,
                rules.describe(rule, "en", values),
                location,
                detail if detail is not None else rules.describe_detail_en(rule, values),
                rule,
                values,
            )
        )

    def changed(
        self,
        stage: str,
        action: Action,
        subject: str,
        *,
        before: str = "",
        after: str = "",
        automation: Automation = Automation.DETERMINISTIC,
        risk: Risk = Risk.NONE,
        reversible: bool = True,
        rule: str = "",
    ) -> None:
        """Record one high-risk transformation in the balance sheet."""
        self.changes.append(
            Change(
                stage=stage,
                action=action,
                subject=subject,
                before=before,
                after=after,
                automation=automation,
                risk=risk,
                reversible=reversible,
                rule=rule,
            )
        )

    def irreversible(self) -> list[Change]:
        """Changes the output alone does not carry enough to undo.

        The question somebody asks before overwriting their only copy, and the
        one the report could not answer at all before this existed.
        """
        return [change for change in self.changes if not change.reversible]

    def count(self, level: Level) -> int:
        return sum(1 for f in self.findings if f.level is level)

    def summary(self, language: str = "en") -> "list[str]":
        """The report in a few sentences, before the technical account.

        Pillar C of the 0.4 plan, and the owner's own words for what was
        wrong with the report as it stood: *„dla czytającego to zupa"*.
        Measured on four books of his shelf — 39, 61, 94 and 122 findings —
        so what a reader met first was between forty and a hundred and
        twenty lines of stage names, bracketed level tags and repeated
        rules, and nowhere in it the one sentence anybody actually opens a
        report for: **is my book all right**.

        So this answers, in order, the four questions a person has:

        1. is the book healthy, and was it written;
        2. what was repaired — by area, in words, not by rule name;
        3. what was left alone deliberately, and that the reason is on the
           line below in each case;
        4. what is waiting for an answer, because until it comes nothing
           about it changes (S-05).

        Nothing here is a new fact. It is the same findings counted, which
        matters twice over: the summary cannot drift from the account below
        it, and a reader who distrusts a sentence can go and count.
        """
        from . import rules

        stages = _SUMMARY_STAGES_PL if language != "en" else _SUMMARY_STAGES_EN
        words = _SUMMARY_WORDS_PL if language != "en" else _SUMMARY_WORDS_EN

        def say(key: str, **values) -> str:
            # The report's own plural machinery, so "4 sprawy" and "5 spraw"
            # agree here exactly as they do in every finding below.
            return rules.fill(words[key], values) if values else words[key]
        errors = self.count(Level.ERROR)
        warnings = self.count(Level.WARN)
        fixes = self.count(Level.FIX)
        kept = self.count(Level.PRESERVED)
        notes = self.count(Level.INFO)

        if not self.output:
            verdict = say("refused")
        elif errors:
            verdict = say("errors", count=errors)
        elif warnings:
            verdict = say("warned", count=warnings)
        else:
            verdict = say("healthy")
        lines = [words["heading"], f"  {verdict}"]

        if fixes:
            counted: dict[str, int] = {}
            for finding in self.findings:
                if finding.level is Level.FIX:
                    name = stages.get(finding.stage, finding.stage)
                    counted[name] = counted.get(name, 0) + 1
            biggest = sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
            where = ", ".join(f"{name} ({count})" for name, count in biggest)
            lines.append(f"  {say('fixed', count=fixes, where=where)}")
        if kept:
            lines.append(f"  {say('kept', count=kept)}")
        # Only when the verdict was spent on something worse; otherwise the
        # first line already said it and a second one is padding.
        if warnings and errors and self.output:
            lines.append(f"  {say('warnings', count=warnings)}")
        if notes:
            lines.append(f"  {say('notes', count=notes)}")

        asked = sum(
            1 for change in self.changes if change.automation is Automation.ASKED
        )
        if asked:
            lines.append(f"  {say('answered', count=asked)}")
        # From the queue's own record (`pipeline` puts it here), never guessed
        # from the shape of a rule name: telling somebody their book waits on
        # them when it does not is the same kind of untruth as saying nothing.
        unanswered = self.stats.get("questions_unanswered") or 0
        if unanswered:
            lines.append(f"  {say('waiting', count=unanswered)}")
        return lines

    @property
    def ok(self) -> bool:
        return self.count(Level.ERROR) == 0

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (_ORDER[f.level], f.stage, f.message))

    def to_dict(self, language: str = "en") -> dict:
        """The report as data, with a description in the language asked for.

        `message` is always English and never moves: it is what a script that
        greps this file has been matching all along, and a translation that
        changes it is a broken interface wearing a feature's name. The reader's
        language goes in `description`, rendered from `rule` and `values` — the
        two fields that let any consumer render either language for itself.
        """
        from . import rules

        findings = []
        for finding in self.sorted_findings():
            entry = asdict(finding) | {"level": finding.level.value}
            if finding.rule:
                entry["description"] = rules.describe(finding.rule, language, finding.values)
            translated = self.detail_for(finding, language)
            if translated is not None and translated != finding.detail:
                entry["detail_description"] = translated
            findings.append(entry)
        return {
            "schema": SCHEMA_VERSION,
            "language": language,
            "source": self.source,
            "output": self.output,
            "ok": self.ok,
            "stats": self.stats,
            # Pillar C. The window and any other front end get the same
            # sentences the text report opens with, rather than each one
            # inventing its own summary out of the counts.
            #
            # *Not* `summary` — that name is taken, by the per-level counts
            # below, and has been in the JSON since anything outside this
            # project could read it. Adding a field is a schema bump; quietly
            # changing what an existing one means is how a consumer breaks
            # without a message.
            "in_short": self.summary(language)[1:],
            "balance": self.balance.as_dict() if self.balance is not None else None,
            "summary": {level.value: self.count(level) for level in Level},
            "findings": findings,
            # BA-2026-003. The findings say why; this says what, in a shape
            # something other than a person can add up.
            "changes": [
                asdict(change)
                | {
                    "action": change.action.value,
                    "automation": change.automation.value,
                    "risk": change.risk.value,
                }
                for change in self.changes
            ],
            "change_summary": {
                "total": len(self.changes),
                "irreversible": len(self.irreversible()),
                "by_action": {
                    action.value: sum(1 for c in self.changes if c.action is action)
                    for action in Action
                    if any(c.action is action for c in self.changes)
                },
                "by_risk": {
                    risk.value: sum(1 for c in self.changes if c.risk is risk)
                    for risk in Risk
                    if any(c.risk is risk for c in self.changes)
                },
            },
        }

    def to_json(self, language: str = "en") -> str:
        return json.dumps(self.to_dict(language), indent=2, ensure_ascii=False)

    def detail_for(self, finding: Finding, language: str = "en") -> str | None:
        """The paragraph beneath a finding, translated where there is one.

        Falls back to the English original rather than dropping it. A detail is
        where the file names and the reasons live, so losing it would be a worse
        translation than an untranslated one.
        """
        from . import rules

        if not finding.rule:
            return finding.detail
        return rules.describe_detail(finding.rule, language, finding.values) or finding.detail

    def headline(self, finding: Finding, language: str = "en") -> str:
        """One line for *finding*, in the language asked for.

        The window and the console were rendering this differently, which is
        how the console came to be English-only while the window was bilingual.
        """
        from . import rules

        if language == "en" or not finding.rule:
            return finding.message
        described = rules.describe(finding.rule, language, finding.values)
        if rules.renders_fully(finding.rule, language, finding.values):
            return described
        return f"{described}\n{finding.message}"

    def to_text(self, language: str = "en") -> str:
        """The report, rendered for a reader rather than for a machine.

        In a language other than English, a finding that carries an identifier
        is headed by what that identifier *means* in that language. Where the
        catalogue entry is a template and the finding carries its values, that
        line says everything the English one said and stands alone.

        Where it is not, the original message follows underneath. The message is
        where the specifics live — how many entries, which file, which media
        type — and dropping it to gain a translation would trade information for
        language. The second line is the visible edge of the conversion, and it
        disappears one finding at a time as the templates are written.
        """
        header = "EPUB-Forge report" if language == "en" else "Raport EPUB F.O.R.G.E."
        # Pillar C: the summary stands above the technical account, because a
        # reader who only reads the first six lines should still learn whether
        # the book is all right — and on this shelf that account runs from 39
        # to 122 findings.
        lines = [header, ""] + self.summary(language)
        lines += ["", f"  source: {self.source}", f"  output: {self.output}", ""]
        for key, value in self.stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        current_level = None
        for finding in self.sorted_findings():
            if finding.level is not current_level:
                current_level = finding.level
                lines.append(f"[{current_level.value.upper()}]")
            where = f" ({finding.location})" if finding.location else ""
            headline, _, original = self.headline(finding, language).partition("\n")
            lines.append(f"  - {finding.stage}: {headline}{where}")
            if original:
                lines.append(f"      {original}")
            detail = self.detail_for(finding, language)
            if detail:
                lines.append(f"      {detail}")
        return "\n".join(lines)


def batch_to_dict(reports: "list[Report]", language: str = "en") -> dict:
    """Every book in one run, as one document.

    Saving reports one at a time is fine for one book and unusable for thirty:
    the question a batch actually raises is *which* of them needs attention,
    and answering it by opening thirty files is slower than not asking.

    So the whole-run counts come first, then the books ordered worst-first —
    the ones that wrote nothing, then the ones with errors, then the rest. Each
    book carries its complete report, so nothing here replaces the single-book
    file; it saves having to open thirty of them to find the two that matter.
    """
    def severity(report: "Report") -> tuple:
        return (
            0 if not report.ok else 1,
            -report.count(Level.ERROR),
            -report.count(Level.WARN),
            report.source or "",
        )

    ordered = sorted(reports, key=severity)
    summary = {level.value: sum(r.count(level) for r in reports) for level in Level}
    return {
        "schema": SCHEMA_VERSION,
        "kind": "batch",
        "books": len(reports),
        "written": sum(1 for r in reports if r.ok),
        "not_written": sum(1 for r in reports if not r.ok),
        "with_errors": sum(1 for r in reports if r.count(Level.ERROR)),
        "with_warnings": sum(1 for r in reports if r.count(Level.WARN)),
        "summary": summary,
        # Pillar C, one level up: the same sentences the window shows when a
        # batch finishes, so a front end never composes its own.
        "in_short": batch_summary(reports, language)[1:],
        # Worst first: a batch report is read from the top and abandoned as
        # soon as it stops being interesting.
        "language": language,
        "reports": [report.to_dict(language) for report in ordered],
    }


def batch_summary(reports: "list[Report]", language: str = "en") -> "list[str]":
    """The whole shelf in a few sentences — pillar C, one level up.

    `Report.summary` answers *is this book all right*. After a run over a
    hundred and sixty books that question becomes *which of them do I have
    to look at*, and answering it by opening a hundred and sixty reports is
    slower than not asking — the same argument `batch_to_dict` was written
    on, carried from the JSON to the person.

    Frequencies are counted **by book, not by finding**, which is
    `survey.py`'s rule and it is the right one here for the same reason:
    one book with forty of something is a curiosity, forty books with one
    each is a fact about the shelf. A total mixes the two and reads like
    the fact.
    """
    words = _BATCH_WORDS_PL if language != "en" else _BATCH_WORDS_EN
    stages = _SUMMARY_STAGES_PL if language != "en" else _SUMMARY_STAGES_EN
    from . import rules

    def say(key: str, **values) -> str:
        return rules.fill(words[key], values) if values else words[key]

    total = len(reports)
    if not total:
        return [words["heading"], f"  {say('nothing')}"]

    refused = sum(1 for report in reports if not report.output)
    with_errors = sum(
        1 for report in reports if report.output and report.count(Level.ERROR)
    )
    with_warnings = sum(
        1 for report in reports
        if report.output and not report.count(Level.ERROR) and report.count(Level.WARN)
    )
    healthy = total - refused - with_errors - with_warnings

    lines = [words["heading"], f"  {say('books', count=total, healthy=healthy)}"]
    if refused:
        lines.append(f"  {say('refused', count=refused)}")
    if with_errors:
        lines.append(f"  {say('errors', count=with_errors)}")
    if with_warnings:
        lines.append(f"  {say('warnings', count=with_warnings)}")

    repaired: dict[str, int] = {}
    for report in reports:
        for stage in {f.stage for f in report.findings if f.level is Level.FIX}:
            name = stages.get(stage, stage)
            repaired[name] = repaired.get(name, 0) + 1
    if repaired:
        biggest = sorted(repaired.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
        where = ", ".join(f"{name} ({count})" for name, count in biggest)
        lines.append(f"  {say('repaired', where=where)}")

    waiting = sum(
        1 for report in reports if report.stats.get("questions_unanswered")
    )
    if waiting:
        lines.append(f"  {say('waiting', count=waiting)}")
    return lines


#: The shelf summary's sentences. Separate from the single-book table because
#: they count books rather than findings, and a word reused across the two
#: would end up meaning both.
_BATCH_WORDS_PL = {
    "heading": "W skrócie — cała półka",
    "nothing": "Nie przebudowano żadnej książki.",
    "books": (
        "Przebudowano {count} {count:książkę|książki|książek}; "
        "{healthy} z nich {healthy:jest zdrowa|są zdrowe|jest zdrowych}."
    ),
    "refused": (
        "{count} {count:książka nie powstała|książki nie powstały|książek nie powstało} — "
        "program wolał nie zapisać nic, niż zapisać książkę, o której nie umie "
        "powiedzieć, że jest cała."
    ),
    "errors": (
        "{count} {count:książka ma błąd|książki mają błędy|książek ma błędy}, "
        "{count:którego|których|których} program nie umiał rozstrzygnąć sam."
    ),
    "warnings": (
        "W {count} {count:książce|książkach|książkach} są sprawy warte obejrzenia."
    ),
    "repaired": "Najczęściej naprawiane obszary (w ilu książkach): {where}.",
    "waiting": (
        "W {count} {count:książce|książkach|książkach} pytania czekają na Twoją odpowiedź."
    ),
}
_BATCH_WORDS_EN = {
    "heading": "In short — the whole shelf",
    "nothing": "No book was rebuilt.",
    "books": "{count} book(s) were rebuilt; {healthy} of them are healthy.",
    "refused": (
        "{count} book(s) were not written — the program would rather write nothing "
        "than write a book it cannot say is whole."
    ),
    "errors": "{count} book(s) carry a problem the program could not settle on its own.",
    "warnings": "{count} book(s) have things worth a look.",
    "repaired": "Most often repaired (in how many books): {where}.",
    "waiting": "{count} book(s) have questions waiting for your answer.",
}


def batch_to_json(reports: "list[Report]", language: str = "en") -> str:
    return json.dumps(batch_to_dict(reports, language), indent=2, ensure_ascii=False)
