"""Two things worth doing about a damaged file, since rebuilding is not one.

The rebuild refuses a source it could not read in full, and there is no setting
to make it stop refusing — the owner's decision of 2026-08-14, on the argument
that a book quietly missing its ornament is as damaged as one missing its
chapter, and that a program whose promise is *the book still looks like itself*
does not get to hand back either.

That leaves an honest gap: a refusal is correct and it is not help. Where a
damaged file actually comes from is almost never the shop — an interrupted
download, a dying disk, a converter that wrote one entry badly, years of bit rot
on a backup — and the real repair is a clean copy. So this module does the two
things that are actually useful:

**`inspect`** — open every entry and say which ones the archive will not give
up. Point it at a shelf on the day the books arrive, while re-downloading takes
a minute, rather than finding out two years later when the title has been
withdrawn.

**`merge`** — two copies of one book, damaged in different places, one good book
out of them. This is the only operation here that *recovers* anything rather
than lowering a standard, and it is exact: an entry is taken whole from a copy
that has it whole, byte for byte, with its CRC checked against the archive's own
record. Nothing is reconstructed and nothing is averaged.

**Nothing here decides anything on its own.** `merge` produces a plan and a
caller shows it before a byte is written; where two intact copies disagree about
the same entry it refuses to choose, because two different intact answers is
exactly the case where guessing produces a book neither copy was.
"""

from __future__ import annotations

import binascii
import hashlib
import os
import zipfile
from dataclasses import dataclass, field

#: Read in pieces so an entry that lies about its size costs a chunk to refuse
#: rather than its claimed length in memory.
_CHUNK = 1024 * 1024


@dataclass
class EntryHealth:
    """One member of one archive, and whether it can be had."""

    name: str
    #: Bytes as stored in the central directory. A claim, not a measurement.
    declared_size: int
    ok: bool
    #: Empty when `ok`. Otherwise what went wrong, in the words of whatever
    #: refused — a corrupt deflate stream, a CRC that does not match, a name.
    reason: str = ""
    #: SHA-256 of the contents, when there are contents. What `merge` compares:
    #: two copies of one book should agree byte for byte on every entry, and
    #: where they do not, somebody has two different books or one modified one.
    digest: str = ""


@dataclass
class BookHealth:
    path: str
    #: Empty when the archive could not be opened at all.
    entries: list[EntryHealth] = field(default_factory=list)
    #: Why the file is not an archive, when it is not one.
    unreadable: str = ""

    @property
    def damaged(self) -> list[EntryHealth]:
        return [entry for entry in self.entries if not entry.ok]

    @property
    def healthy(self) -> bool:
        return not self.unreadable and not self.damaged

    def summary(self) -> str:
        if self.unreadable:
            return f"{os.path.basename(self.path)}: {self.unreadable}"
        if not self.damaged:
            return f"{os.path.basename(self.path)}: {len(self.entries)} entries, all readable"
        return (
            f"{os.path.basename(self.path)}: {len(self.damaged)} of {len(self.entries)} "
            f"entries damaged"
        )


def inspect(path: str) -> BookHealth:
    """Read every entry of *path* and report which ones the archive refuses.

    Actually read, not asked about. A ZIP's central directory is a set of claims
    about entries, and a truncated download leaves the claims intact — the
    directory is at the end of the file and may be the only part that arrived
    whole. The only way to learn that an entry is gone is to try to decompress
    it, which is what this does, and why it costs about what reading the book
    costs.
    """
    health = BookHealth(path=path)
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        health.unreadable = f"{type(exc).__name__}: {exc}"
        return health

    with archive:
        try:
            members = archive.infolist()
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            health.unreadable = f"{type(exc).__name__}: {exc}"
            return health
        for info in members:
            if info.is_dir():
                continue
            health.entries.append(_read_one(archive, info))
    return health


def _read_one(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> EntryHealth:
    digest = hashlib.sha256()
    running = 0
    try:
        with archive.open(info) as stream:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                running += len(chunk)
    except BaseException as exc:  # noqa: BLE001
        # Everything, including the `BadZipFile` that a wrong CRC raises at the
        # end of the stream and the `zlib.error` a corrupt one raises in the
        # middle. This function exists to answer "can this be had", and any way
        # of not having it is the same answer.
        return EntryHealth(
            name=info.filename,
            declared_size=info.file_size,
            ok=False,
            reason=f"{type(exc).__name__}: {exc}",
        )
    return EntryHealth(
        name=info.filename,
        declared_size=info.file_size,
        ok=True,
        reason="",
        digest=digest.hexdigest(),
    )


@dataclass
class MergePlan:
    """What a merge would do, before it does any of it."""

    #: `{entry name: path it would be taken from}`.
    take: dict[str, str] = field(default_factory=dict)
    #: Entries no copy could give up. A merge with any of these still produces a
    #: damaged book, and the caller is told before rather than after.
    still_missing: list[str] = field(default_factory=list)
    #: `{entry name: [digest per copy]}` where two copies both read cleanly and
    #: disagree. Not resolved here on purpose — see the module docstring.
    conflicts: dict[str, list[str]] = field(default_factory=dict)
    #: Why these files cannot be merged at all, when they cannot.
    refused: str = ""

    @property
    def usable(self) -> bool:
        return not self.refused and not self.still_missing and not self.conflicts

    @property
    def repairs(self) -> int:
        """Entries this merge would recover — ones the first copy has lost."""
        return sum(1 for source in self.take.values() if source != self.first)

    #: The copy that would be treated as the book being repaired. Everything
    #: else is a donor.
    first: str = ""


def plan_merge(paths: list[str]) -> MergePlan:
    """Work out which copy each entry would come from, and decide nothing else.

    Two or more copies of what should be one book. For every entry name, the
    plan takes it from the first copy that reads it cleanly — and records a
    conflict instead if two copies read it cleanly and disagree, because two
    different intact answers is not something to average.
    """
    plan = MergePlan()
    if len(paths) < 2:
        plan.refused = "a merge needs at least two copies"
        return plan

    health = [inspect(path) for path in paths]
    unreadable = [h for h in health if h.unreadable]
    if len(unreadable) == len(health):
        plan.refused = "none of these files is a readable archive"
        return plan

    plan.first = paths[0]
    readable = [h for h in health if not h.unreadable]

    # Same book? Compared on the entries both copies have intact, because the
    # package document is the thing most worth checking and also the thing most
    # likely to be the damaged one. Agreement on the content documents is a
    # stronger signal than a matching identifier anyway: an identifier is one
    # string a converter can rewrite.
    names = {entry.name for h in readable for entry in h.entries}
    for name in sorted(names):
        answers: dict[str, str] = {}
        for h in readable:
            for entry in h.entries:
                if entry.name == name and entry.ok:
                    answers[h.path] = entry.digest
        if not answers:
            plan.still_missing.append(name)
            continue
        distinct = sorted(set(answers.values()))
        if len(distinct) > 1:
            plan.conflicts[name] = distinct
            continue
        # First copy that has it, in the order the caller gave them: the caller
        # decides which copy is "the" book by putting it first.
        plan.take[name] = next(path for path in paths if path in answers)
    return plan


@dataclass
class MergeResult:
    plan: MergePlan
    output_path: str | None = None
    #: Entries written, and how many came from somewhere other than the first
    #: copy — the number that says whether this achieved anything.
    written: int = 0


def merge(paths: list[str], destination: str, plan: MergePlan | None = None) -> MergeResult:
    """Write one archive taking each entry from a copy that has it whole.

    *plan* is the one the caller showed somebody; passing it back is how this
    stays a decision made by a person rather than by a function called twice.
    Recomputed when absent, which is the batch case.

    An unusable plan writes nothing. So does an existing destination: this is a
    repair, and a repair that overwrites is the failure it was meant to prevent.
    """
    plan = plan or plan_merge(paths)
    result = MergeResult(plan=plan)
    if not plan.usable:
        return result
    if os.path.exists(destination):
        plan.refused = "the destination already exists"
        return result

    opened = {path: zipfile.ZipFile(path) for path in set(plan.take.values())}
    try:
        staging = destination + ".part"
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED) as out:
            # `mimetype` first and stored, or the result is not an OCF archive
            # whatever else is right about it.
            ordered = sorted(plan.take, key=lambda name: (name != "mimetype", name))
            for name in ordered:
                source = opened[plan.take[name]]
                info = source.getinfo(name)
                data = source.read(name)
                if name == "mimetype":
                    out.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_STORED)
                else:
                    out.writestr(info, data)
                result.written += 1
        os.replace(staging, destination)
    finally:
        for archive in opened.values():
            archive.close()
        if os.path.exists(destination + ".part"):
            try:
                os.unlink(destination + ".part")
            except OSError:
                pass
    result.output_path = destination
    return result


def crc_matches(path: str) -> bool:
    """Whether every entry's contents match the CRC the archive recorded.

    `zipfile` checks this itself while reading and raises `BadZipFile`, so
    `inspect` already covers it; this is here for the case somebody wants the
    question asked on its own.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None
    except (zipfile.BadZipFile, OSError, ValueError, binascii.Error):
        return False
