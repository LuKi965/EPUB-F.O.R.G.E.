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
#: interface; stamping it now costs one field and means a later change can be
#: announced instead of guessed at.
SCHEMA_VERSION = 1


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
        message: str,
        location: str | None = None,
        detail: str | None = None,
        rule: str | None = None,
    ) -> None:
        self.findings.append(Finding(stage, level, message, location, detail, rule))

    def count(self, level: Level) -> int:
        return sum(1 for f in self.findings if f.level is level)

    @property
    def ok(self) -> bool:
        return self.count(Level.ERROR) == 0

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (_ORDER[f.level], f.stage, f.message))

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "source": self.source,
            "output": self.output,
            "ok": self.ok,
            "stats": self.stats,
            "summary": {level.value: self.count(level) for level in Level},
            "findings": [asdict(f) | {"level": f.level.value} for f in self.sorted_findings()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_text(self, language: str = "en") -> str:
        """The report, rendered for a reader rather than for a machine.

        In a language other than English, a finding that carries an identifier
        is headed by what that identifier *means* in that language, and its
        original message follows underneath. The message is where the specifics
        live — how many entries, which file, which media type — and dropping it
        to gain a translation would trade information for language. Once every
        message is a template with its values alongside (37 of the 77 still
        interpolate directly), the second line stops being needed.
        """
        from . import rules

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
            if language != "en" and finding.rule:
                lines.append(f"  - {finding.stage}: {rules.describe(finding.rule, language)}{where}")
                lines.append(f"      {finding.message}")
            else:
                lines.append(f"  - {finding.stage}: {finding.message}{where}")
            if finding.detail:
                lines.append(f"      {finding.detail}")
        return "\n".join(lines)


def batch_to_dict(reports: "list[Report]") -> dict:
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
        "reports": [report.to_dict() for report in ordered],
    }


def batch_to_json(reports: "list[Report]") -> str:
    return json.dumps(batch_to_dict(reports), indent=2, ensure_ascii=False)
