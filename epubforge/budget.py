"""How much of a machine one book is allowed to cost.

The audit's F-019 and F-020. There were three limits — the archive's total size,
one entry's size, and the compression ratio — and they are a good start on the
one attack they cover: a ZIP that unpacks into more than a disk. Everything
past unpacking was unbounded. A hundred thousand tiny entries, a document
nested ten thousand deep, an image whose dimensions multiply out to a hundred
gigapixels, a stylesheet importing itself: each is small in the archive and
enormous in memory, and none of them was counted.

**What this is not.** These numbers are not in EPUB 3.3 and nothing here is a
conformance rule. They are an operational judgement about what a book can
plausibly need, set well above every real book measured on two shelves and far
below what breaks a machine. A book that trips one is not malformed; it is
outside what this program will spend without being told to.

**Why a refusal and not a warning.** The same argument as the read-side gate in
0.2.20: a limit that reports and continues produces a half-processed book with
a status nobody reads. Every limit here refuses, names itself, and says both
numbers — what was found and what was allowed — because a limit whose message
does not say what it was is a limit nobody can act on.

**On `huge_tree`.** The audit says to take it off the default path. The
intention is right and the mechanism is not the one this uses. Turning it off
hands the job to libxml2, which refuses with an opaque error at a threshold
nobody here chose and which differs between library versions; a book that
rebuilds today would start failing with a message this project did not write.
The limits below do the same job explicitly: bounded, chosen here, and reported
in this program's own words. Depth is measured on the bytes *before* a tree is
built, which is the part that actually protects the C stack.
"""

from __future__ import annotations

import contextvars
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

#: Entries in one archive. A real book runs to a few hundred; the largest on
#: either shelf is a nine-thousand-document omnibus. Twenty thousand is an order
#: of magnitude above anything anybody has sent and the point at which per-entry
#: bookkeeping alone becomes the cost.
MAX_ENTRIES = 20_000

#: Bytes of one XML document handed to a parser. The largest content document
#: measured is a 233 946-character chapter, about a quarter of a megabyte.
MAX_DOCUMENT_BYTES = 64 * 1024**2

#: Nesting depth. libxml2's own default is 256 and this is deliberately more
#: generous, because a converter that wraps every paragraph in three `<div>`s
#: produces genuinely deep markup and is not attacking anybody.
MAX_DEPTH = 1024

#: Pixels × frames in one image, after decompression. A 250-megapixel budget
#: passes any cover or plate a book has ever carried and refuses the 100 000 ×
#: 100 000 PNG that decodes to forty gigabytes of RGBA.
MAX_PIXELS = 250_000_000

#: Seconds for one book, end to end. Generous: the slowest real book measured
#: takes about two seconds per mode. This is not a performance target — it is
#: the line past which something has gone wrong rather than slowly.
MAX_SECONDS = 300.0


class Cancelled(BaseException):
    """Somebody asked for this rebuild to stop.

    A `BaseException` for the same reason `BudgetExceeded` is one: it travels
    through eleven stages of code that catch `Exception` to keep one bad
    document from sinking a book, and a cancellation any of them can swallow is
    a Cancel button that works when the program is idle.
    """

    def __str__(self) -> str:
        return "przerwane na życzenie"


class BudgetExceeded(BaseException):
    """One book asked for more than it is allowed. Carries both numbers.

    **`BaseException`, not `Exception`, and that is the point.** Wiring the
    document limit into the parsers made it fire — and a stage caught it with an
    `except Exception` two frames up, filed it as `xhtml.unparseable`, and
    published the book. A limit that any local handler can swallow is not a
    limit; it is a limit-shaped thing that reports a different defect. There are
    a dozen broad handlers in this program and every one of them is right about
    the case it was written for, which is exactly why this must not be in the
    class they catch.

    Same reasoning as `KeyboardInterrupt`: it is not an error some code failed
    to anticipate, it is a decision to stop. Only `rebuild` catches it, and it
    turns it into a blocked result with both numbers in the report.
    """

    def __init__(self, limit: str, found: object, allowed: object, where: str = "") -> None:
        self.limit = limit
        self.found = found
        self.allowed = allowed
        self.where = where
        super().__init__(f"{limit}: {found} where {allowed} is allowed" + (f" ({where})" if where else ""))


@dataclass
class Budget:
    """What one rebuild may spend, and how much of it is gone.

    Created per book. The deadline starts when the object does, so a caller that
    keeps one around and reuses it is measuring the wrong thing — which is why
    `Context` makes a new one rather than taking a module-level default.
    """

    # Read at construction rather than baked into `__init__` at import. A
    # dataclass default is evaluated once, when the class is created, so
    # `entries: int = MAX_ENTRIES` makes the constant decorative: changing it
    # afterwards — which is what a test tuning a ceiling does, and what a
    # per-profile setting would do — changes nothing. The factories make the
    # constants above the single source of truth they read as.
    entries: int = field(default_factory=lambda: MAX_ENTRIES)
    document_bytes: int = field(default_factory=lambda: MAX_DOCUMENT_BYTES)
    depth: int = field(default_factory=lambda: MAX_DEPTH)
    pixels: int = field(default_factory=lambda: MAX_PIXELS)
    seconds: float = field(default_factory=lambda: MAX_SECONDS)
    started: float = field(default_factory=time.monotonic)

    #: Asked, at every checkpoint, whether the person changed their mind.
    #:
    #: A callable rather than a flag because the answer lives somewhere else —
    #: in the window's worker thread, in a signal handler — and this side has no
    #: business knowing where. `None` is "nobody can cancel this", which is what
    #: a library caller and the corpus both want.
    cancelled: "object | None" = None

    def checkpoint(self, where: str = "") -> None:
        """Both of the reasons to stop, asked together, cheaply enough to ask often.

        DELTA-2026-08-15-001: the deadline was asked before and after every
        stage, which bounds a rebuild made of eleven stages and does nothing for
        a *stage* that walks six hundred documents. The clock could be four
        minutes past a one-minute limit and the only checkpoint was the one at
        the end of the stage that spent them.

        Cancellation has the same shape and was worse: the window could only
        stop *between books*, so "cancel" on a large book meant "finish this one
        first". Both are one question asked in one place — the per-document
        accessor every stage goes through — and both raise, so the writer's
        cleanup removes the staging file and the destination is left alone.
        """
        if self.cancelled is not None and self.cancelled():
            raise Cancelled()
        self.deadline(where)

    def deadline(self, where: str = "") -> None:
        spent = time.monotonic() - self.started
        if spent > self.seconds:
            raise BudgetExceeded("wall clock", f"{spent:.0f}s", f"{self.seconds:.0f}s", where)

    def archive_entries(self, count: int) -> None:
        if count > self.entries:
            raise BudgetExceeded("archive entries", count, self.entries)

    def image(self, width: int, height: int, frames: int = 1, where: str = "") -> None:
        total = width * height * max(1, frames)
        if total > self.pixels:
            raise BudgetExceeded(
                "image pixels × frames", f"{total:,}", f"{self.pixels:,}", where
            )

    def document(self, data: bytes, where: str = "") -> None:
        """Refuse a document too large or too deep *before* a tree is built.

        Both halves are measured on the bytes, and the depth one is why: a tree
        deep enough to matter is one that overflows the C stack while being
        built, so noticing afterwards is noticing from the wrong side of the
        crash. Counting `<tag` against `</tag` over the raw bytes is crude and
        cheap, and crude in the right direction — it cannot under-report a
        genuine nest, and the few things it over-counts (a `<` inside a comment,
        say) are nowhere near a thousand deep.
        """
        if len(data) > self.document_bytes:
            raise BudgetExceeded(
                "document bytes", f"{len(data):,}", f"{self.document_bytes:,}", where
            )
        depth = _nesting(data)
        if depth > self.depth:
            raise BudgetExceeded("nesting depth", depth, self.depth, where)


#: An opening tag, a closing tag, or a self-closing one, in bytes. Deliberately
#: not a parser: this runs before parsing, on data nothing has vouched for.
_TAG = re.compile(rb"<(/?)([A-Za-z_][^\s/>]*)[^>]*?(/?)>", re.DOTALL)

# --------------------------------------------------------------------------
# The limit that was written and never wired in
# --------------------------------------------------------------------------
#
# **F-019, reopened by the 2026-08-14 baseline, and it was right.** `document()`
# above had a full test file to itself and **zero call sites in the program**. A
# reproduction set the depth ceiling to 10, handed the rebuild an eighty-deep
# document, and counted the calls: nought. The book was parsed, rebuilt and
# published. The test proved the *limit* worked; nothing proved it was *used*,
# and those are different claims — the same shape of error as a status tool that
# counts its own list and reports it as the audit's.
#
# So the check does not live at call sites any more. A budget is made active for
# the length of one rebuild and every parse in this program asks for it, which
# means a new parse added next year is bounded without anybody remembering to
# bound it. That is the only version of this fix that stays fixed.
#
# A `ContextVar` rather than a global because the window runs rebuilds on a
# worker thread and the corpus runs several at once; each gets its own, and a
# thread that was never given one gets `_UNBOUND` — the module defaults, which
# still refuse a gigabyte — rather than no limit at all.

_UNBOUND: "Budget | None" = None

_ACTIVE: contextvars.ContextVar["Budget | None"] = contextvars.ContextVar(
    "epubforge_budget", default=None
)


def current() -> "Budget":
    """The budget this rebuild is spending, or a fresh one with the defaults.

    Never `None`: a parse that happens outside any rebuild — diagnostics, the
    fidelity harness, a test — is still bounded. Being asked from nowhere is not
    a reason to allow anything.
    """
    global _UNBOUND
    active = _ACTIVE.get()
    if active is not None:
        return active
    if _UNBOUND is None:
        _UNBOUND = Budget()
    return _UNBOUND


@contextmanager
def active(budget: "Budget"):
    """Make *budget* the one every parse inside this block is charged against."""
    token = _ACTIVE.set(budget)
    try:
        yield budget
    finally:
        _ACTIVE.reset(token)


def bounded(data: bytes | None, where: str = "") -> None:
    """Refuse *data* before a parser sees it. Raises :class:`BudgetExceeded`.

    The one function every parse in this program calls. It is deliberately not
    optional and takes no "skip this" argument: the finding this exists for is
    precisely that a check with an opt-out is a check nobody remembers to opt
    into.
    """
    if data:
        current().document(data, where)


#: Elements that never nest and are frequently written unclosed in the wild.
#: Counting `<br>` as an opening tag reports a flat document as deeply nested.
_VOID = frozenset(
    b"area base br col embed hr img input link meta param source track wbr".split()
)


def _nesting(data: bytes) -> int:
    deepest = current = 0
    for match in _TAG.finditer(data):
        closing, name, self_closing = match.group(1), match.group(2).lower(), match.group(3)
        if closing:
            current = max(0, current - 1)
        elif self_closing or name in _VOID:
            continue
        else:
            current += 1
            deepest = max(deepest, current)
    return deepest
