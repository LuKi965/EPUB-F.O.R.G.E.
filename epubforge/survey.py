"""Survey a whole library and report what actually breaks, ranked.

A hundred separate reports are a hundred things to read. What a person needs
before deciding what to fix next is one answer to one question: *across this
library, which defects are common and which are curiosities?* A rule written
from a single book is a guess; the same defect in forty books is a fact.

Two design choices are worth stating, because both are about what the output is
safe to hand to somebody else.

**Findings are normalised before they are counted.** A message reading
"corrected 5 declarations" and one reading "corrected 12 declarations" are the
same finding; counting the raw strings would scatter one defect across a dozen
rows and hide exactly the pattern this exists to show. Numbers are folded to `N`.

**Book titles stay out of the output unless asked for.** The whole point of the
corpus arrangement is that nobody's library listing has to leave their disk, and
a survey that named files would quietly undo it. `--with-names` is there when
you want it, and it is a decision rather than a default.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .pipeline import rebuild
from .policy import Policy
from .reader import EpubReadError, read_epub
from .report import Level, Report

#: Any run of digits, and byte/percentage-looking values, become a placeholder
#: so that "5 declarations" and "12 declarations" count as one finding.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
#: Quoted fragments are usually a filename or a class name — specific to one
#: book, and noise when the question is which defects recur.
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"|“[^”]*”|„[^”]*”")


def normalise(message: str) -> str:
    return _NUMBER_RE.sub("N", _QUOTED_RE.sub("…", message)).strip()


@dataclass
class Finding:
    stage: str
    level: Level
    message: str
    #: How many books show it, and how many times in total.
    books: int = 0
    occurrences: int = 0
    #: Up to a handful of examples, only when names were asked for.
    examples: list[str] = field(default_factory=list)


@dataclass
class Survey:
    books: int = 0
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    drm: list[str] = field(default_factory=list)
    source_versions: Counter = field(default_factory=Counter)
    findings: dict[tuple[str, str, str], Finding] = field(default_factory=dict)
    #: Books whose rebuild raised — the number that should always be zero.
    crashed: list[tuple[str, str]] = field(default_factory=list)

    def ranked(self) -> list[Finding]:
        return sorted(
            self.findings.values(),
            key=lambda f: (-f.books, -f.occurrences, f.stage, f.message),
        )

    def to_dict(self, *, with_names: bool) -> dict:
        return {
            "schema": 1,
            "books": self.books,
            "unreadable": len(self.unreadable),
            "crashed": len(self.crashed),
            "drm": len(self.drm),
            "source_versions": dict(self.source_versions.most_common()),
            "findings": [
                {
                    "stage": f.stage,
                    "level": f.level.value,
                    "message": f.message,
                    "books": f.books,
                    "occurrences": f.occurrences,
                    **({"examples": f.examples} if with_names and f.examples else {}),
                }
                for f in self.ranked()
            ],
        }


def _record(survey: Survey, report: Report, name: str, with_names: bool) -> None:
    seen_here: set[tuple[str, str, str]] = set()
    for finding in report.findings:
        message = normalise(finding.message)
        key = (finding.stage, finding.level.value, message)
        entry = survey.findings.get(key)
        if entry is None:
            entry = Finding(finding.stage, finding.level, message)
            survey.findings[key] = entry
        entry.occurrences += 1
        if key not in seen_here:
            seen_here.add(key)
            entry.books += 1
            if with_names and len(entry.examples) < 3:
                entry.examples.append(name)


def survey_library(
    sources: list[str],
    policy: Policy | None = None,
    *,
    deep: bool = True,
    with_names: bool = False,
    on_book=None,
) -> Survey:
    """Read every book and aggregate what the pipeline says about it.

    ``deep`` runs the whole rebuild, so the findings are the ones a user would
    actually get; the result is written to a scratch directory and thrown away,
    because the question here is what the library contains and not what the
    rebuild would produce. Turning it off reads the books only, which is much
    faster and sees only the defects the reader can name on its own.
    """
    policy = policy or Policy.preset("preserve")
    survey = Survey()
    scratch = tempfile.mkdtemp(prefix="epubforge-survey-")
    try:
        for index, source in enumerate(sources):
            name = os.path.basename(source)
            survey.books += 1
            if on_book is not None:
                on_book(index, name)

            report = Report(source=source)
            try:
                if deep:
                    result = rebuild(source, os.path.join(scratch, "out.epub"), policy)
                    report = result.report
                    book = result.book
                    if book is None:
                        # `rebuild` handles an unreadable source itself and
                        # reports it rather than raising, so the except clause
                        # below never sees it in deep mode.
                        reason = next(
                            (f.message for f in report.findings if f.level is Level.ERROR),
                            "unreadable",
                        )
                        survey.unreadable.append((name, reason))
                        continue
                else:
                    book = read_epub(source, report)
            except EpubReadError as exc:
                survey.unreadable.append((name, str(exc)))
                continue
            except Exception as exc:  # noqa: BLE001 — a crash is a finding too
                survey.crashed.append((name, f"{type(exc).__name__}: {exc}"))
                continue

            if book is not None:
                survey.source_versions[book.source_version] += 1
                if book.has_drm:
                    survey.drm.append(name)
            _record(survey, report, name, with_names)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return survey


def to_json(survey: Survey, *, with_names: bool = False) -> str:
    return json.dumps(survey.to_dict(with_names=with_names), indent=2, ensure_ascii=False)


__all__ = ["Finding", "Survey", "normalise", "survey_library", "to_json"]
