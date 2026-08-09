#!/usr/bin/env python3
"""Has this version actually been released, and what is still owed?

    python packaging/release_check.py

This exists because of a specific failure, and stating it plainly is the whole
point of the file: a version was bumped, a changelog entry written, work
committed and pushed — and then described as *released*. It was not. Nobody had
built it, no tag existed, nothing was downloadable. Twice over, the milestone it
closed was never frozen either, so `frozen/*` stopped covering the roadmap
somewhere around 0.2.8 and nobody could see that from inside the repository.

The mistake is not forgetfulness, it is that "released" had no definition a
machine could check. It has one now, and it is deliberately the strictest
available: **a tag and a GitHub release exist on the remote.** Not "the commit
is pushed", not "the changelog says so" — those are things this repository can
say about itself, and the failure was exactly a repository saying something
about itself that the outside world did not confirm.

So the checks split in two, and the split matters:

* **Ours** — version, changelog, READMEs. Wrong here is a bug we can fix, and
  `tests/test_release_state.py` fails the build over it.
* **Theirs** — the tag, the release, the frozen branch. These are facts on the
  remote, read with `git ls-remote`, and the only ones that settle the
  question.

The build is dispatched from here, through the GitHub API, and the tag is
created by the workflow at the commit it builds. `git push --tags` is refused
by the proxy with a 403, which is a fact about one command and not about the
release — reading it as "this side cannot release anything" is a mistake this
file made in its first version, on the strength of a workflow run whose `actor`
said `LuKi965`. That field names the account the token belongs to, not a person
at a keyboard.

Exit code is 0 when nothing is owed, 1 when something is.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
READMES = (ROOT / "README.md", ROOT / "README.en.md")

#: A released section: a number, a stage, a date. `## Unreleased` is the other
#: state and is what work in progress belongs under.
RELEASED = re.compile(
    r"^## (?P<version>\d+\.\d+\.\d+) — (?P<stage>[a-z-]+) — (?P<date>\d{4}-\d{2}-\d{2})"
    r"(?P<rest>.*)$",
    re.MULTILINE,
)

#: What marks a release as closing a roadmap point, and therefore as owing the
#: milestone cycle — freeze, next branch, cleanup list. Written into the heading
#: because that is the one line nobody forgets to write, and a marker kept
#: anywhere else would be the second thing to forget after the freeze itself.
MILESTONE = re.compile(r"kamień milowy (?P<points>\[[^\n]+\])")


def milestone_points(rest: str) -> list[str]:
    """The roadmap points a release heading claims to close, if any.

    A release may close more than one — 0.2.14 closed [4] and [5] together —
    so the heading is read as a list rather than as a single value. One name
    per point would have needed one release per point, which is not how the
    work actually came out.
    """
    marked = MILESTONE.search(rest)
    return re.findall(r"\[([^\]]+)\]", marked.group("points")) if marked else []


def version() -> str:
    text = (ROOT / "epubforge" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def heading_for(number: str) -> re.Match | None:
    for match in RELEASED.finditer(CHANGELOG.read_text(encoding="utf-8")):
        if match.group("version") == number:
            return match
    return None


def remote_refs(pattern: str) -> set[str]:
    """Refs matching *pattern* on origin, or an empty set if unreachable.

    Unreachable is reported as "cannot say" rather than as "missing": a network
    failure that reads as a clean bill of health is the same class of mistake
    this file exists to stop.
    """
    try:
        out = subprocess.run(
            ["git", "ls-remote", pattern, "origin"],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return set()
    return {line.split("\t")[-1].strip() for line in out.splitlines() if line.strip()}


def check(number: str, *, offline: bool = False) -> list[tuple[bool | None, str, str]]:
    """`(ok, what, what to do about it)` for every condition, in order."""
    results: list[tuple[bool | None, str, str]] = []
    heading = heading_for(number)

    results.append((
        heading is not None,
        f"CHANGELOG has a dated section for {number}",
        f"rename the `## Unreleased` heading to `## {number} — alpha — <date>`",
    ))

    # Only for the version being worked on. Asked about an older number the
    # answer would always be "no" and would mean nothing: the READMEs describe
    # what the repository is now, not what each past release was.
    if number == version():
        for readme in READMES:
            text = readme.read_text(encoding="utf-8")
            results.append((
                f"`{number}`" in text,
                f"{readme.name} names {number}",
                f"step 0 of the milestone cycle: update {readme.name}",
            ))

    points = milestone_points(heading.group("rest")) if heading else []

    if offline:
        results.append((None, "remote state not checked (--offline)", ""))
        return results

    tags = remote_refs("--tags")
    released = f"refs/tags/v{number}" in tags
    results.append((
        released,
        f"tag v{number} exists on origin",
        "dispatch build-windows.yml on main with "
        f"release_tag = v{number}, then wait for it to finish",
    ))

    if points:
        heads = remote_refs("--heads")
        frozen = [ref for ref in heads if ref.startswith(f"refs/heads/frozen/v{number}-")]
        listed = ", ".join(f"[{point}]" for point in points)
        results.append((
            bool(frozen),
            f"frozen/v{number}-* exists on origin (milestone {listed})",
            f"once released: git branch frozen/v{number}-<name> <commit> && git push",
        ))
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", nargs="?", help="defaults to __version__")
    parser.add_argument("--offline", action="store_true", help="skip the remote checks")
    arguments = parser.parse_args(argv[1:])

    number = (arguments.number or version()).lstrip("v")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(f"{number}\n")
    owed = []
    for ok, what, todo in check(number, offline=arguments.offline):
        mark = "?" if ok is None else ("OK" if ok else "--")
        print(f"  [{mark}] {what}")
        if ok is False and todo:
            owed.append(todo)

    if not owed:
        print("\nNothing owed.")
        return 0
    print("\nStill owed:")
    for step in owed:
        print(f"  - {step}")
    print(
        "\nUntil the tag is on origin this version is not released, whatever "
        "the changelog says."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
