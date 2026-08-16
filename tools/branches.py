"""Which branches can go, and which must not.

Remote branches cannot be deleted from the build environment — the proxy
refuses the operation with a 403, the same way it refuses a tag push — so this
prints the list for whoever can. It is a script rather than a habit because a
habit produces a tidy repository right up until the week somebody is busy.

    python tools/branches.py

Safe to delete means all three of: merged into the trunk, so nothing is lost;
not a `frozen/` marker, which exist precisely to be kept; and not the branch
currently checked out or the trunk itself.
"""

from __future__ import annotations

import subprocess

TRUNK = "main"

#: Never suggested for deletion, whatever their merge state.
#:
#: `frozen/*` are the milestone markers. `pre-alpha-stable` is one too, under an
#: older naming. The tool branch is the one the build environment designates for
#: this session, and removing it out from under the harness is not this script's
#: decision to make.
PROTECTED = {
    TRUNK,
    "pre-alpha-stable",
    "claude/epub3-standardization-tool-279ib6",
}
PROTECTED_PREFIXES = ("frozen/",)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def remote_branches() -> list[str]:
    lines = _git("ls-remote", "--heads", "origin").splitlines()
    return sorted(line.split("refs/heads/")[-1] for line in lines if "refs/heads/" in line)


def protected(branch: str) -> bool:
    return branch in PROTECTED or branch.startswith(PROTECTED_PREFIXES)


def merged(branch: str) -> bool:
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", f"origin/{branch}", f"origin/{TRUNK}"],
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    _git("fetch", "--prune", "origin")
    current = _git("rev-parse", "--abbrev-ref", "HEAD")

    disposable: list[str] = []
    kept: list[tuple[str, str]] = []
    for branch in remote_branches():
        if protected(branch):
            kept.append((branch, "protected"))
        elif branch == current:
            kept.append((branch, "in use"))
        elif not merged(branch):
            kept.append((branch, "NOT merged — would lose commits"))
        else:
            disposable.append(branch)

    print("Keep:")
    for branch, why in kept:
        print(f"  {branch:44} {why}")

    print("\nSafe to delete (everything in them is in the trunk):")
    if not disposable:
        print("  nothing — the repository is already tidy")
    for branch in disposable:
        print(f"  {branch}")
    if disposable:
        print("\n  https://github.com/LuKi965/EPUB-F.O.R.G.E./branches")
        print("  or, from a machine that can push deletions:")
        print("    git push origin --delete " + " ".join(disposable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
