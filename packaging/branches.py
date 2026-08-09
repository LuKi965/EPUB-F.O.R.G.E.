#!/usr/bin/env python3
"""Which branches on origin have nothing left in them.

    python packaging/branches.py

Step 4 of the milestone cycle. It used to name a `tools/branches.py` that no
longer exists — lost when the documents moved to the private repository — so
the step quietly became "remember which branches are stale", which is not a
step, it is a hope.

Deleting a remote branch is refused from this environment (the proxy answers
403, the same as a tag push), so this only ever prints. The owner deletes them
in a browser, and a list is the most this side can honestly produce.

Three kinds of branch and only one is ever listed:

* `frozen/*` — never. That is the point of the prefix: a frozen branch is where
  you go back to after an accident, and it outlives every reason to tidy.
* `main`, `pre-alpha-stable` — never.
* `claude/*` — listed once its tip is an ancestor of `main`, meaning every
  commit on it is already on the trunk and the branch holds nothing that would
  be lost. A branch still ahead of `main` is printed too, in its own section,
  as work that has not landed — which is worth seeing and is not a deletion.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEEP = ("refs/heads/main", "refs/heads/pre-alpha-stable")
NEVER_STALE = "refs/heads/frozen/"


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def remote_heads() -> dict[str, str]:
    heads = {}
    for line in git("ls-remote", "--heads", "origin").splitlines():
        if not line.strip():
            continue
        commit, _, ref = line.partition("\t")
        heads[ref.strip()] = commit.strip()
    return heads


def merged(commit: str, into: str) -> bool | None:
    """Whether *commit* is already contained in *into*; None if unknown here.

    Unknown rather than False when the commit is not in this clone: a shallow
    or partial fetch would otherwise report every branch as unmerged and the
    list would say "delete nothing", which is the safe answer given for the
    wrong reason.
    """
    try:
        git("cat-file", "-e", f"{commit}^{{commit}}")
    except subprocess.CalledProcessError:
        return None
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, into],
        cwd=ROOT, capture_output=True,
    ).returncode == 0


def main() -> int:
    git("fetch", "origin", "main", "--quiet")
    heads = remote_heads()
    stale, ahead, unknown = [], [], []

    for ref, commit in sorted(heads.items()):
        if ref in KEEP or ref.startswith(NEVER_STALE):
            continue
        state = merged(commit, "origin/main")
        entry = (ref.removeprefix("refs/heads/"), commit[:8])
        (stale if state else ahead if state is False else unknown).append(entry)

    def show(title: str, rows: list[tuple[str, str]], note: str = "") -> None:
        if not rows:
            return
        print(f"\n{title}")
        if note:
            print(f"  {note}")
        for name, commit in rows:
            print(f"  {name}  ({commit})")

    print(f"{len(heads)} branch(es) on origin")
    show("Fully merged into main — safe to delete in the browser:", stale)
    show("Ahead of main — holds work that has not landed:", ahead)
    show("Cannot tell from this clone:", unknown, "fetch them if it matters")
    kept = [r.removeprefix("refs/heads/") for r in sorted(heads) if r.startswith(NEVER_STALE)]
    if kept:
        print(f"\nKept regardless ({len(kept)}): " + ", ".join(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
