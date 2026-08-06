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

#: Version of the JSON shape written by :meth:`Report.to_dict`. The moment
#: anything outside this project reads ``--report`` output, that shape is an
#: interface; stamping it costs one field and means a change can be announced
#: instead of guessed at.
#:
#: **2** — `message` is now rendered from the catalogue rather than written at
#: the call site, so its English wording changed for most findings. `rule` did
#: not change and is the field to match on; that is what it is for. Two fields
#: were added: `description`, the finding in the language asked for, and
#: `detail_description`, the same for the paragraph beneath it. Nothing was
#: removed.
SCHEMA_VERSION = 2


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

    def count(self, level: Level) -> int:
        return sum(1 for f in self.findings if f.level is level)

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
            "summary": {level.value: self.count(level) for level in Level},
            "findings": findings,
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
        lines = [header, f"  source: {self.source}", f"  output: {self.output}", ""]
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
        # Worst first: a batch report is read from the top and abandoned as
        # soon as it stops being interesting.
        "language": language,
        "reports": [report.to_dict(language) for report in ordered],
    }


def batch_to_json(reports: "list[Report]", language: str = "en") -> str:
    return json.dumps(batch_to_dict(reports, language), indent=2, ensure_ascii=False)
