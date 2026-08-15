"""What a book will cost to rebuild, before reading a byte of it.

`reader.py` has held a ceiling since early on: 2 GiB of content, 512 MiB per
entry. The audit's EF-020 says the whole publication is held in RAM and asks
for a benchmark before anything else is done about it. The benchmark was the
right order to do this in, because it turned out the ceiling answers a
different question than the one anybody thought it answered.

Measured — four purchased books and two synthetic ones, peak RSS of a whole
rebuild in its own process:

    tekst MB   binaria MB   szczyt RSS
       1.0          0.5        45 MB
       1.3         11.6        78 MB
       0.2         14.9        76 MB
       0.2         23.3        88 MB
      25.4          0.0       147 MB
     152.1          0.0       700 MB

Text costs about 4.6 times its own size and binaries about 2.8×.

**The multipliers are a property of this program and move with it.** Text was
12.0 when first fitted, 14.0 a day later when a stage was added that reads every
content document, and 4.6 once EF-020's second half removed the transient
allocation that dominated the whole rebuild: the last book went from 2042 MB to
700. That is why the table above is dated by measurement rather than assumed,
and why `test_memory.py` pins every row of it — the constants are a *safety*
estimate, and one that drifts low turns "this will not fit" into a process the
kernel kills.

Where the memory actually goes, measured per stage on the 152 MB book: reading
it costs 148 MiB — about 1× the bytes — and the profile stage costs 518 MiB,
which is the parse trees for 601 documents plus what measuring them needs.
Everything else is now noise. The 1681 MiB the profile stage used to cost, and
the 1345 MiB the hyphen stage used to cost, were both one mistake made twice:
building the whole book's text as a single string. Anybody optimising further
should start at the trees and not at the bytes — and specifically not with lazy
binaries, which would save about 1× the binary bytes on a book that was never at
risk and nothing at all on the one that is.

So the ceiling of 2 GiB of *content* is a promise that the process may reach
**twenty-four gigabytes of memory**. It is not a memory bound at all; it is a
content bound that nobody had converted. A machine with 2 GiB free dies at
around 160 MB of text, and dies by being killed — no report, no diagnosis, no
output, and on Windows no message a person can act on.

This module is the conversion. It is cheap on purpose: the sizes come out of
the ZIP central directory, so a book is measured without decompressing it, and
a refusal costs milliseconds. The estimate is deliberately a little
pessimistic. Being told "this needs more memory than you have" about a book
that would just have fitted costs somebody one switch; the other error costs
them the rebuild, the report and any idea of why.
"""

from __future__ import annotations

import os
import pathlib
import zipfile
from dataclasses import dataclass

#: Suffixes parsed into element trees. The multiplier below belongs to these.
TEXT_SUFFIXES = (".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".css", ".svg")

#: Measured, not assumed. See the table above — and re-measure when a stage is
#: added, because this is what the pipeline costs and not what text costs.
TEXT_MULTIPLIER = 4.6
BINARY_MULTIPLIER = 2.8

#: The interpreter with lxml, Pillow and the package imported, before a book is
#: opened. Measured at 33–35 MiB; carried at 40 so the smallest books, where the
#: fixed cost dominates and the multipliers have nothing to work with, keep a
#: margin like everything else.
BASELINE_BYTES = 40 * 1024**2

#: On top of the multipliers, because they are a fit and a fit has residuals.
#: Under is the wrong direction for a guard: an estimate that is a little low
#: turns "this will not fit" into a process the kernel kills. With the
#: multipliers above, 1.15 leaves between 13% and 28% of margin across the six
#: measured books, and the cost of it being too careful is one switch.
SAFETY = 1.15

#: How much of what the operating system reports as available this will plan to
#: use. Leaving a fifth is not caution for its own sake: `MemAvailable` is the
#: kernel's estimate, the rest of the machine keeps running during a rebuild,
#: and a batch of books in the window runs them one after another in the same
#: process — so the number this compares against is already optimistic.
HEADROOM = 0.8


@dataclass(frozen=True)
class Estimate:
    """What one book is expected to cost, and what it is made of."""

    text_bytes: int
    binary_bytes: int

    @property
    def peak_bytes(self) -> int:
        return int(
            SAFETY
            * (
                BASELINE_BYTES
                + self.text_bytes * TEXT_MULTIPLIER
                + self.binary_bytes * BINARY_MULTIPLIER
            )
        )

    def __str__(self) -> str:
        return (
            f"{human(self.text_bytes)} tekstu i {human(self.binary_bytes)} binariów "
            f"→ około {human(self.peak_bytes)} pamięci"
        )


def human(size: float) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} GiB"
    return f"{size / 1024**2:.0f} MiB"


def estimate(source: "str | pathlib.Path") -> "Estimate | None":
    """Read the central directory and add up what is declared there.

    `None` when the file is not a readable archive — this is a question asked
    before the reader runs, and answering "no idea" lets the reader produce the
    proper diagnosis instead of this module inventing one.

    The declared sizes are the archive author's claim, which is exactly what a
    hostile file controls. That is fine here and is not fine in `reader.py`:
    understating the size buys a bomb nothing, because the reader's own limits
    are measured on the decompressed stream and still refuse it. Overstating it
    only makes this refuse early, which is what it is for.
    """
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
    except (OSError, zipfile.BadZipFile):
        return None
    text = sum(
        entry.file_size
        for entry in entries
        if entry.filename.lower().endswith(TEXT_SUFFIXES)
    )
    total = sum(entry.file_size for entry in entries)
    return Estimate(text_bytes=text, binary_bytes=max(0, total - text))


def available_bytes() -> "int | None":
    """What the operating system says is free for a new allocation.

    `None` when it will not say, and `None` has to stay a real answer: refusing
    a book because a memory query failed would be this program inventing a
    reason to damage somebody's evening.
    """
    meminfo = pathlib.Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            for line in meminfo.read_text(encoding="ascii", errors="replace").splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    if os.name == "nt":
        try:
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except (OSError, AttributeError, ImportError):
            return None
    return None


@dataclass(frozen=True)
class Verdict:
    """Whether this machine can be expected to hold this book."""

    estimate: "Estimate | None"
    available: "int | None"
    limit: "int | None"

    @property
    def known(self) -> bool:
        return self.estimate is not None and self.limit is not None

    @property
    def fits(self) -> bool:
        """`True` whenever it is not known to be too big.

        The default is to go ahead. A machine that will not say how much memory
        it has is not a machine this program gets to refuse to work on, and
        every rebuild before this module existed went ahead anyway.
        """
        if not self.known:
            return True
        return self.estimate.peak_bytes <= self.limit

    def __str__(self) -> str:
        if self.estimate is None:
            return "nie da się oszacować: to nie jest czytelne archiwum"
        if self.limit is None:
            return f"{self.estimate}; system nie podaje, ile pamięci jest wolnej"
        if self.available is None:
            return f"{self.estimate}; budżet {human(self.limit)}"
        return (
            f"{self.estimate}; wolne {human(self.available)}, "
            f"budżet {human(self.limit)}"
        )


def check(source: "str | pathlib.Path", *, limit: "int | None" = None) -> Verdict:
    """Estimate the cost and compare it with what this machine has.

    `limit` overrides the machine entirely, which is what a person asking for a
    fixed budget means and what the tests use — otherwise the answer would
    depend on how much the container happened to have free that minute.
    """
    measured = estimate(source)
    if limit is not None:
        return Verdict(measured, None, limit)
    available = available_bytes()
    if available is None:
        return Verdict(measured, None, None)
    return Verdict(measured, available, int(available * HEADROOM))
