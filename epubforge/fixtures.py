"""Named roles for specific real books, without naming the books.

The audit that opened this file lists two commercial EPUBs as *mandatory
fixtures* — books whose particular defects three findings are written against,
and which no synthetic file reproduces. It then recorded all three findings as
`BLOCKED`, "no files", and the owner's reply was the honest one: he had no idea
which files were meant.

That is the problem this solves, and it has two halves that pull against each
other. A test cannot assert anything about a book it cannot name. A public
repository cannot hold somebody's purchased copy, and — the owner's standing
rule — cannot name their titles either: a listing of a private shelf in a public
place says more about the shelf than about the tool.

So a *role* is committed and a *book* is not. `ksiazka-1` is a description of
what a book has to contain to play a part in the suite — an EPUB 2 package to
migrate, full-page images on the cover and two title pages, a dedication
composed against the bottom edge — plus the digest of the copy the measurements
were taken from. The title, the author and the file live on the owner's disk.
Somebody else's checkout sees a role with nothing filling it, and the tests
that need it skip and say what is missing.

Nothing has to be copied anywhere. The shelf the private corpus already uses is
searched, so a book that is on it is a fixture by being on it: a role is matched
first by the recorded digest, then — because editions get replaced and this must
survive that — by the structural profile that made the book worth choosing.

This lives in the package rather than in the tests for the same reason
`corpus.py` does: the person holding the books is not necessarily the person
holding a checkout, and the answer to "which file do you want" has to be
reachable without pytest.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import zipfile
from dataclasses import dataclass, field

#: Where a role's recorded profile is kept. Committed — it is counts and a
#: digest, and holds neither a title nor a byte of anybody's text.
PROFILES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"

#: Folders searched for a book to fill a role, in order. The first is the
#: private corpus, which is the point: a shelf already dropped there needs
#: nothing done to it. `EPUBFORGE_FIXTURES` is for a shelf kept elsewhere.
SEARCH = ("EPUBFORGE_FIXTURES", "EPUBFORGE_CORPUS")


@dataclass(frozen=True)
class Role:
    """A part in the test suite that only a real book can play.

    `profile` is what makes the match survive a new edition. The publisher
    reissues, the digest moves, and a fixture identified by digest alone would
    go missing on a book that is still sitting there and still has exactly the
    defect the finding is about.
    """

    id: str
    #: What this book is here to exercise, in the owner's language. Shown by
    #: `epubforge fixtures` and in the GUI, so "which file do you want" has an
    #: answer somebody can act on without opening the audit.
    exercises: tuple[str, ...]
    #: Findings that cannot be closed without it.
    findings: tuple[str, ...]
    #: Structural facts, checked loosely — see `_resembles`.
    profile: dict = field(default_factory=dict)


#: The two the audit calls mandatory. Deliberately not named: the mapping from
#: role to title is in the private notes repository, where the shelf is already
#: described. What is here is enough to recognise the book and not enough to
#: say whose it is.
ROLES: tuple[Role, ...] = (
    Role(
        id="ksiazka-1",
        exercises=(
            "pakiet EPUB 2, który trzeba przenieść do EPUB 3.3",
            "dokument okładki i dwie strony tytułowe z pełnostronicowymi obrazami",
            "te strony nie mają własnego stylowania i liczą na domyślne style czytnika",
            "obrazy w proporcjach strony książki, które muszą wejść w różne viewporty bez deformacji",
            "dedykacja skomponowana względem dolnej krawędzi strony",
            "możliwe ukryte znaczniki dystrybucyjne w dokumentach tekstowych",
        ),
        findings=("F-028",),
        profile={
            "package_version": "2.0",
            "documents": 29,
            "spine": 29,
            "images": 3,
            "fonts": 7,
            "stylesheets": 1,
        },
    ),
    Role(
        id="ksiazka-2",
        exercises=(
            "realne błędy podziału wyrazów — twarde łączniki zostawione w środku słowa",
            "typografia po konwersji, na której da się zmierzyć precyzję detektora",
            "długi spine z jednolitym stylowaniem, więc kandydaci nie giną w szumie",
        ),
        findings=("BA-2026-001", "BA-2026-002"),
        profile={
            "package_version": "2.0",
            "documents": 65,
            "spine": 65,
            "images": 3,
            "fonts": 4,
            "stylesheets": 1,
        },
    ),
)

BY_ID = {role.id: role for role in ROLES}


def digest_of(path: pathlib.Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def profile_of(path: pathlib.Path) -> dict:
    """The structural facts a role is matched on. Never any text."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        opf = next((n for n in names if n.endswith(".opf")), None)
        package_version = ""
        spine = 0
        if opf:
            declaration = archive.read(opf).decode("utf-8", "replace")
            found = re.search(r"<package[^>]*\sversion=\"([^\"]+)\"", declaration)
            package_version = found.group(1) if found else ""
            spine = len(re.findall(r"<itemref\b", declaration))

    def count(*suffixes: str) -> int:
        return sum(1 for n in names if n.lower().endswith(suffixes))

    return {
        "package_version": package_version,
        "documents": count(".xhtml", ".html", ".htm"),
        "spine": spine,
        "images": count(".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"),
        "fonts": count(".ttf", ".otf", ".woff", ".woff2"),
        "stylesheets": count(".css"),
    }


def _resembles(entry: dict, book: pathlib.Path, measured: dict) -> bool:
    """Could this be the recorded book in another edition?

    A *suggestion* and never a match — see `locate`. Measured on the owner's
    shelf while writing this: the counts alone put a Foundation novel forward as
    the Witcher fixture, because "EPUB 2, 29 documents, 3 images, 7 fonts, one
    stylesheet" is not a description of a book, it is a description of how one
    publisher's toolchain exports. Size is what pulls those apart, so it is in
    here too — and the whole thing is still only a shortlist for a person.
    """
    if entry.get("profile", {}).get("package_version") != measured.get("package_version"):
        return False
    recorded_bytes = entry.get("bytes") or 0
    if recorded_bytes and abs(book.stat().st_size - recorded_bytes) > recorded_bytes * 0.1:
        return False
    for key in ("documents", "spine", "images", "fonts", "stylesheets"):
        want, got = entry.get("profile", {}).get(key), measured.get(key)
        if want is None or got is None:
            continue
        if abs(got - want) > max(1, round(want * 0.1)):
            return False
    return True


def profile_path(role: str) -> pathlib.Path:
    return PROFILES / f"{role}.json"


def recorded(role: str) -> "dict | None":
    path = profile_path(role)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def record(role: str, book: pathlib.Path) -> dict:
    """Remember this copy as the one the measurements were taken from."""
    if role not in BY_ID:
        raise KeyError(role)
    entry = {
        "role": role,
        "sha256": digest_of(book),
        "bytes": book.stat().st_size,
        "profile": profile_of(book),
    }
    PROFILES.mkdir(parents=True, exist_ok=True)
    profile_path(role).write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entry


def shelves(extra: "pathlib.Path | None" = None) -> "list[pathlib.Path]":
    """Folders to search, in order, skipping the ones that are not there."""
    import os

    found: list[pathlib.Path] = []
    if extra is not None:
        found.append(pathlib.Path(extra))
    for variable in SEARCH:
        value = os.environ.get(variable)
        if value:
            found.append(pathlib.Path(value))
    found.append(pathlib.Path(__file__).resolve().parent.parent / "tests" / "corpus")
    return [path for path in found if path.is_dir()]


@dataclass
class Match:
    role: str
    path: "pathlib.Path | None" = None
    #: Books that could be the recorded one reissued. Offered to a person to
    #: confirm; never used as the answer.
    candidates: "tuple[pathlib.Path, ...]" = ()

    @property
    def found(self) -> bool:
        return self.path is not None

    def __str__(self) -> str:
        if self.found:
            return f"{self.role}: {self.path.name}"
        if self.candidates:
            names = ", ".join(p.name for p in self.candidates)
            return f"{self.role}: brak; podobne na półce: {names}"
        return f"{self.role}: brak"


def locate(role: str, *, extra: "pathlib.Path | None" = None) -> Match:
    """Find the book that fills *role*, by digest and by nothing else.

    A role is filled by the copy whose digest was recorded, and by no other
    file. The suggestion path was written first and measured second: on the
    owner's own shelf, matching by structural profile handed a different novel
    to the fixture, confidently and with a reassuring word next to it. That is
    the failure mode this project has a rule about — a wrong answer given
    quietly is worse than no answer given loudly — so resemblance now produces a
    shortlist and a question, and `epubforge fixtures record` is how a person
    answers it.
    """
    entry = recorded(role)
    if entry is None:
        return Match(role)
    wanted = entry.get("sha256")
    resembling: list[pathlib.Path] = []
    for shelf in shelves(extra):
        for book in sorted(shelf.rglob("*.epub")):
            try:
                if digest_of(book) == wanted:
                    return Match(role, book)
                if len(resembling) < 5 and _resembles(entry, book, profile_of(book)):
                    resembling.append(book)
            except (OSError, zipfile.BadZipFile, StopIteration):
                continue
    return Match(role, None, tuple(resembling))


def survey(*, extra: "pathlib.Path | None" = None) -> "list[Match]":
    return [locate(role.id, extra=extra) for role in ROLES]


def explain(role: Role) -> str:
    """What a person has to hand over, and why, in one block of text."""
    lines = [f"{role.id} — potrzebna do: {', '.join(role.findings)}"]
    lines += [f"  · {line}" for line in role.exercises]
    entry = recorded(role.id)
    if entry:
        lines.append(
            f"  zapisany odcisk: sha256:{entry['sha256'][:16]}…, {entry['bytes']} B, "
            f"pakiet {entry['profile'].get('package_version')}, "
            f"{entry['profile'].get('documents')} dokumentów, "
            f"{entry['profile'].get('spine')} w spine"
        )
    return "\n".join(lines)
