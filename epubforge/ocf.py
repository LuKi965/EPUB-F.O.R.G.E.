"""Names inside the container, and what is wrong with them.

Every archive entry arrives as a string somebody else chose. It may hold a
backslash, a leading slash, a `..` segment, percent-encoding, or two spellings
of the same word in different Unicode normal forms. The reader used to fold
some of that away in one expression and store the result — so a name that had
been changed looked exactly like a name that had not, and two entries that
collided after folding left only the one that happened to come last.

This module answers two questions and answers them separately:

* what is the container path for this entry, and what had to be changed to get
  it — `canonical`;
* which entries end up meaning the same file, and in whose eyes — `collisions`.

The second question has four answers because filesystems disagree. Two entries
can be distinct in the archive and identical on disk: `Rozdział.xhtml` and
`rozdział.xhtml` are one file on Windows, and the NFC and NFD spellings of one
Polish word are one file on macOS. Neither is an error in the archive; both are
a book that will lose a document the moment somebody unpacks it.
"""

from __future__ import annotations

import posixpath
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote


@dataclass(frozen=True)
class Name:
    """One archive entry, as it arrived and as it will be used."""

    raw: str
    path: str
    #: What had to be changed, in words, for the report. Empty when the name
    #: arrived already canonical — which is the ordinary case.
    changes: tuple[str, ...] = ()
    #: True when the name could not be made into a container path at all.
    rejected: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def canonical(raw: str) -> Name:
    """The container path for an archive entry, and an account of the folding.

    Rejects rather than repairs the two cases where repairing would invent an
    answer: a name that escapes the container, and a name that empties out.
    """
    changes: list[str] = []
    name = raw

    # A name is terminated at the first null byte — the standard library does
    # this too, and calls it a virus trick in a comment. The difference is that
    # here it is written down rather than done on the way past.
    if "\0" in name:
        name = name.split("\0", 1)[0]
        changes.append("null byte")
    if "\\" in name:
        name = name.replace("\\", "/")
        changes.append("backslash separators")
    if name.startswith("/"):
        name = name.lstrip("/")
        changes.append("leading slash")
    if len(name) > 1 and name[1] == ":" and name[0].isalpha():
        name = name[2:].lstrip("/")
        changes.append("drive letter")

    if "%" in name:
        decoded = unquote(name)
        if decoded != name:
            name = decoded
            changes.append("percent-encoding")

    segments = [segment for segment in name.split("/") if segment not in ("", ".")]
    if len(segments) != len([s for s in name.split("/") if s != ""]):
        changes.append("empty or current-directory segments")

    resolved: list[str] = []
    escaped = False
    for segment in segments:
        if segment == "..":
            if resolved:
                resolved.pop()
            else:
                escaped = True
            continue
        resolved.append(segment)

    if escaped:
        return Name(
            raw=raw,
            path="",
            changes=tuple(changes),
            rejected=True,
            reason="the name climbs out of the container with '..'",
        )
    if not resolved:
        return Name(raw=raw, path="", changes=tuple(changes), rejected=True,
                    reason="the name is empty once normalised")
    if ".." in name.split("/"):
        changes.append("parent-directory segments")

    return Name(raw=raw, path=posixpath.join(*resolved), changes=tuple(changes))


@dataclass
class Collision:
    """Several entries that mean one file to somebody."""

    #: "identical", "case", "normalisation" or "percent-encoding".
    kind: str
    names: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        """Whether this must stop the read rather than merely be reported.

        Only exact collisions block. Two names that differ in case are legal and
        distinct inside the archive, and refusing the book would mean refusing
        one that reads perfectly well on Linux — the honest response there is a
        warning about the filesystem that will not survive it.
        """
        return self.kind == "identical"


#: How a name looks to each thing that might confuse two of them.
_VIEWS = (
    ("identical", lambda path: path),
    ("percent-encoding", lambda path: unquote(path)),
    ("normalisation", lambda path: unicodedata.normalize("NFC", path)),
    ("case", lambda path: unicodedata.normalize("NFC", path).casefold()),
)


def collisions(paths: list[str]) -> list[Collision]:
    """Group the paths that some filesystem or reader would treat as one.

    A pair is reported once, under the *narrowest* view that catches it: two
    identical names are not also reported as a case collision, because saying it
    twice makes the report longer without making it truer.
    """
    found: list[Collision] = []
    already: set[frozenset[str]] = set()

    for kind, view in _VIEWS:
        grouped: dict[str, list[str]] = {}
        for path in paths:
            grouped.setdefault(view(path), []).append(path)
        for members in grouped.values():
            if len(members) < 2:
                continue
            key = frozenset(members)
            if key in already:
                continue
            already.add(key)
            found.append(Collision(kind, sorted(members)))
    return found


__all__ = ["Collision", "Name", "canonical", "collisions"]
