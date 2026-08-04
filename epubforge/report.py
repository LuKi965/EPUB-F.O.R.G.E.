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
    ) -> None:
        self.findings.append(Finding(stage, level, message, location, detail))

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

    def to_text(self) -> str:
        lines = [f"EPUB-Forge report", f"  source: {self.source}", f"  output: {self.output}", ""]
        for key, value in self.stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        current_level = None
        for finding in self.sorted_findings():
            if finding.level is not current_level:
                current_level = finding.level
                lines.append(f"[{current_level.value.upper()}]")
            where = f" ({finding.location})" if finding.location else ""
            lines.append(f"  - {finding.stage}: {finding.message}{where}")
            if finding.detail:
                lines.append(f"      {finding.detail}")
        return "\n".join(lines)
