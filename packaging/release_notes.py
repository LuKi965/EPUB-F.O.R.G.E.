"""The release notes for one version, taken from the changelog.

A release whose notes are written separately from the changelog ends up saying
something different from it, and the difference is never in the changelog's
favour — the summary is written once, at release time, by whoever is in a
hurry. This reads the section that is already there.

    python packaging/release_notes.py 0.2.0
    python packaging/release_notes.py 0.2.0 --output release-notes.md

Exits non-zero if there is no such section, so a release cannot quietly go out
with empty notes.

`--output` writes UTF-8 directly and is what the workflow uses. Printing works
too, but a Windows runner hands Python a cp1252 console, and this changelog is
Polish and full of em dashes and arrows — the first release attempt died on a
`→` after building everything.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

#: "## 0.2.0 — alpha", and the em dash is not optional in this file.
#:
#: "## Unreleased — will ship as 0.2.3" counts as that version's section. Work
#: accumulates there between releases, because the version number moves when a
#: release is built and not when a commit lands; at release time the heading is
#: renamed and this pattern stops matching it, which is the intended handover.
HEADING = re.compile(
    r"^## (?:(?P<version>\d+\.\d+\.\d+)|Unreleased\b.*?(?P<upcoming>\d+\.\d+\.\d+))(?P<rest>.*)$"
)


def section_for(version: str, text: str) -> str:
    """The body under the heading for `version`, without the heading itself."""
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if not match:
            continue
        if start is not None:
            return "\n".join(lines[start:index]).strip()
        if (match.group("version") or match.group("upcoming")) == version:
            start = index + 1
    if start is None:
        return ""
    return "\n".join(lines[start:]).strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="e.g. 0.2.0 or v0.2.0")
    parser.add_argument(
        "-o",
        "--output",
        help="write the notes here as UTF-8 instead of printing them",
    )
    args = parser.parse_args(argv[1:])

    version = args.version.lstrip("v")
    body = section_for(version, CHANGELOG.read_text(encoding="utf-8"))
    if not body:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1

    if args.output:
        # newline="" so the file says the same thing on both platforms. Text
        # mode translates "\n" to "\r\n" on Windows, which would make the notes
        # depend on which runner published them.
        pathlib.Path(args.output).write_text(body + "\n", encoding="utf-8", newline="")
        return 0

    # The console's encoding is whatever the platform chose, and on Windows
    # that is cp1252, which cannot hold most of this file.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
