"""Rendering a page to pixels, so "does it still look like itself" can be asked.

F-028. The fidelity checks this program had compare *structure* — text, shapes,
media, reading order, style — and every one of them can pass on a book that
comes out cropped, stretched, blank or with the dedication pushed off the
bottom of the page. Nothing here had ever looked at a rendered page.

The renderer is Chromium, driven headless through its own command line. Two
things about that choice, both deliberate:

**The engine is the one we ship, and only that one.** Until 0.2.26 there was
none, so this module hunted for a browser: the `PATH`, the Program Files
directories, Playwright's downloads, an environment variable. All of it went in
0.2.28, once there was an engine in the installer to make it pointless. What
that apparatus really did was make every answer a property of the desk the
program was standing on — Edge, found on every Windows machine, disagreed with
Chromium about three of four kinds of damage and reported no version at all.

A checkout carries nothing, so there one variable remains — `EPUBFORGE_CHROME`
— and where even that is unset the answer is a paragraph saying so, reachable
from the window, because "the check you asked for needs something you do not
have, here is what" is an answer and a greyed-out button is not.

**The version is recorded, not assumed.** A rendered page is a function of the
engine that drew it, so a comparison across two engine versions measures the
engine. Every result carries the version string it was produced with, and the
gate refuses to compare two runs that do not share it.

What is compared is the *source* against the *output*, page by page, at a
viewport. That is the only form of the question this can answer honestly. "Is
this page laid out correctly" needs a designer; "does this page still look the
way it looked before this program touched it" needs two screenshots, and it is
the question F-028 is actually about.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass

from . import spawn

#: Names the engine to use **when this build carries none** — a checkout, a
#: `pip` install, this project's own render tests. That is the whole of its job
#: from 0.2.28; a release build has its own engine and never reads it.
ENV_BROWSER = "EPUBFORGE_CHROME"

#: Rendered at this size unless asked otherwise. A six-inch reader at 1×, which
#: is the device the owner's library is read on.
DEFAULT_VIEWPORT = (600, 800)

#: Chromium exits non-zero on a page it could not lay out; anything longer than
#: this is a hang and not a slow page.
_TIMEOUT = 60


@dataclass(frozen=True)
class Choice:
    """Which engine is going to draw, and where it came from.

    Exists so that question has an answer somebody can read. The owner spent a
    release watching this program start Edge with no way to find out why short
    of reading the source.
    """

    #: The engine, or ``None`` when there is none to be had.
    path: "pathlib.Path | None"
    #: ``carried`` (shipped with this build), ``named`` (the variable, and only
    #: where nothing is carried), or ``none``.
    origin: str = "none"

    @property
    def carried(self) -> bool:
        return self.origin == "carried"


def _named() -> "pathlib.Path | None":
    value = os.environ.get(ENV_BROWSER)
    return pathlib.Path(value) if value else None


def _usable(candidate: "pathlib.Path") -> bool:
    return candidate.is_file() and os.access(candidate, os.X_OK)


def chosen() -> Choice:
    """The engine this build carries, and nothing else if it carries one.

    **This program no longer looks for a browser on the machine.** Not the
    `PATH`, not the Program Files directories, not Playwright's download
    folder, and no environment variable able to overrule what is shipped. All
    of that existed for one reason — there was no engine of our own — and that
    reason ended in 0.2.26.

    The owner put it plainly: *we have Chromium built in, what do we need an
    "optional" Edge for.* He is right, and the apparatus was worse than
    redundant. Every path through it made the answer a property of the desk the
    program was standing on. A rendered comparison says something about the
    **book** only when the same engine drew both sides; run against whatever a
    machine happens to have, it says something about the machine. Edge was the
    proof rather than the exception — measured on the same four kinds of damage
    it disagreed with Chromium about three, and reported no version string at
    all, so two runs could not even be shown to be comparable.

    What is left is one fallback with one purpose: a build that carries **no**
    engine — a checkout, a `pip` install, this project's own render tests —
    reads :data:`ENV_BROWSER`. It cannot apply to a release, because a release
    always carries one, so the variable the owner had set for 0.2.25 is now
    inert on his machine whatever it points at.
    """
    from . import resources

    carried = resources.bundled_renderer()
    if carried is not None and _usable(carried):
        return Choice(carried, "carried")
    named = _named()
    if named is not None and _usable(named):
        return Choice(named, "named")
    return Choice(None, "none")


def _candidates() -> "list[pathlib.Path]":
    """Both places an engine can come from, best first. Kept for the tests that
    assert the order; :func:`chosen` is what runs."""
    from . import resources

    found = [resources.bundled_renderer(), _named()]
    return [path for path in found if path is not None]


def find_renderer() -> "pathlib.Path | None":
    return chosen().path


def describe() -> str:
    """One line for the window and the console: which engine, and from where.

    Human in the loop needs something to look at. Until 0.2.27 the only way to
    find out which of three engines had drawn a page was to read this file.
    """
    picked = chosen()
    if picked.path is None:
        return "silnik rysujący: brak"
    origin = {
        "carried": "dołączony do programu",
        "named": f"wskazany zmienną {ENV_BROWSER} (ten build nie ma własnego)",
    }.get(picked.origin, picked.origin)
    return f"silnik rysujący: {picked.path.name} ({origin})"


def why_not() -> str:
    """What to tell somebody who has no renderer. Sentences, not a stack trace.

    Only reachable from a checkout or a `pip` install: the Windows builds carry
    an engine, so this text is for somebody running from source.
    """
    return (
        "Ta kontrola rysuje strony i porównuje obrazy, więc potrzebuje "
        "silnika opartego na Chromium. Wydania dla Windowsa mają własny "
        "(chrome-headless-shell) i niczego nie szukają w systemie — ta "
        "instalacja go nie ma, bo działa z kodu źródłowego.\n\n"
        "Program celowo **nie** szuka przeglądarki na maszynie: ani w PATH, "
        "ani tam, gdzie instalują się Chrome, Edge czy Brave, ani w katalogu "
        "Playwrighta. Porównanie dwóch rysunków mówi coś o książce tylko "
        "wtedy, gdy oba zrobił ten sam silnik; puszczone na tym, co maszyna "
        "akurat ma, mówi coś o maszynie.\n\n"
        f"Jeżeli uruchamiasz z kodu źródłowego, wskaż silnik zmienną "
        f"{ENV_BROWSER} — najlepiej ten sam chrome-headless-shell, który "
        f"jedzie w wydaniu."
    )


def version(browser: "pathlib.Path | None" = None) -> str:
    """The engine's own version string, recorded with every result.

    A comparison across two engine versions measures the engine, so this is not
    decoration: `Fidelity.comparable_with` refuses a pair that disagrees.
    """
    browser = browser or find_renderer()
    if browser is None:
        return ""
    try:
        finished = spawn.run(
            [str(browser), "--version"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return " ".join(finished.stdout.split()) or ""


class RenderError(RuntimeError):
    """The browser ran and produced nothing usable."""


def shoot(
    page: "str | pathlib.Path",
    destination: "str | pathlib.Path",
    *,
    viewport: "tuple[int, int]" = DEFAULT_VIEWPORT,
    browser: "pathlib.Path | None" = None,
) -> pathlib.Path:
    """One page, one PNG, at *viewport*.

    `--virtual-time-budget` rather than a sleep: it tells the engine to run its
    clock forward until the page is quiet, so a page with a web font or a
    transition is captured settled rather than mid-way, and a page with neither
    is captured immediately. A fixed wait would have been both slower and less
    reliable, which is an unusual combination and worth naming.
    """
    browser = browser or find_renderer()
    if browser is None:
        raise RenderError("no renderer")
    target = pathlib.Path(destination)
    width, height = viewport
    # The browser writes its profile here and does not always let go of it
    # before the process exits, which on Windows makes deleting the directory
    # raise. A screenshot that succeeded must not fail on the tidying up.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        command = [
            str(browser),
            # `--headless=new` rather than bare `--headless`. The owner saw an
            # Edge window open on his machine and show nothing, which is exactly
            # what a browser does when it does not recognise the flag: it starts
            # normally. Bare `--headless` is the deprecated spelling and recent
            # Chrome and Edge builds no longer honour it the old way.
            #
            # A window opening and sitting blank is not a cosmetic problem. It
            # is a program doing something on somebody's screen that looks like
            # it should not be happening, which is a fair thing to be suspicious
            # of and a bad thing for a tool that is asking to be trusted with a
            # library.
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            # Nothing about a book should reach the network, and a page that
            # tries is a page whose rendering must not depend on whether it
            # succeeded.
            "--disable-background-networking",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            "--virtual-time-budget=5000",
            f"--screenshot={target}",
            pathlib.Path(page).absolute().as_uri(),
        ]
        try:
            # Through `spawn`, which on Windows says *do not give this child a
            # console*. Without that flag a windowed application opens one black
            # rectangle per screenshot — the owner watched it flash roughly once
            # a second for as long as a batch ran, and called it distracting and
            # suspicious to anybody nearby. He was right on both counts: a
            # program that looks like it is doing something it should not be is
            # a program nobody should hand a library to.
            spawn.run(
                command, capture_output=True, timeout=_TIMEOUT, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"renderer timed out on {page}") from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise RenderError(f"renderer produced nothing for {page}")
    return target


@dataclass(frozen=True)
class Ink:
    """Where the drawn content is on a page, and how much of it there is.

    Deliberately coarse. This exists to answer three questions a pixel-by-pixel
    diff cannot: is the page blank, has the content moved, has it been squashed.
    """

    #: Fraction of pixels that are not the page background.
    coverage: float
    #: Bounding box of everything drawn, as fractions of the viewport.
    left: float
    top: float
    right: float
    bottom: float

    @property
    def blank(self) -> bool:
        return self.coverage < 0.0005

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)


def ink_of(image_path: "str | pathlib.Path") -> Ink:
    """Measure where the content is, treating the commonest colour as paper."""
    from PIL import Image

    with Image.open(image_path) as opened:
        image = opened.convert("L")
        width, height = image.size
        # The commonest shade is the paper. Not "white": a book may be set on
        # cream, and a fixed-layout page may be a full-bleed photograph, where
        # the majority shade is whatever the photograph mostly is.
        paper = image.histogram().index(max(image.histogram()))
        # A tolerance, because anti-aliasing puts a halo of near-paper pixels
        # around every letter; counting those makes coverage a measure of the
        # font hinting. Done with `point` rather than a Python loop over the
        # pixels — half a million iterations per page, per viewport, per
        # document, on both sides of a comparison.
        mask = image.point(lambda shade: 255 if abs(shade - paper) > 24 else 0)
        box = mask.getbbox()
        drawn = mask.histogram()[255]
    if not drawn or box is None:
        return Ink(0.0, 0.0, 0.0, 0.0, 0.0)
    left, top, right, bottom = box
    return Ink(
        coverage=drawn / (width * height),
        left=left / width,
        top=top / height,
        right=right / width,
        bottom=bottom / height,
    )


def difference(one: "str | pathlib.Path", two: "str | pathlib.Path") -> float:
    """Fraction of pixels that differ, after putting both on one canvas.

    Two pages of different heights are compared over the taller one, with the
    shorter treated as paper below its end — otherwise a page that lost its last
    paragraph would compare as identical over the part that survived.
    """
    from PIL import Image, ImageChops

    with Image.open(one) as first, Image.open(two) as second:
        left = first.convert("L")
        right = second.convert("L")
        size = (max(left.width, right.width), max(left.height, right.height))
        canvas_one = Image.new("L", size, 255)
        canvas_two = Image.new("L", size, 255)
        canvas_one.paste(left, (0, 0))
        canvas_two.paste(right, (0, 0))
        delta = ImageChops.difference(canvas_one, canvas_two)
        histogram = delta.histogram()
    # Anything under a shade of difference is anti-aliasing.
    differing = sum(histogram[25:])
    return differing / (size[0] * size[1])


def engine_matches(recorded: str, measured: str) -> bool:
    """Same engine, same major version. Patch releases do not move type."""
    def major(text: str) -> str:
        found = re.search(r"(\D+)\s(\d+)\.", text)
        return f"{found.group(1).strip()} {found.group(2)}" if found else text

    return bool(recorded) and major(recorded) == major(measured)


__all__ = [
    "DEFAULT_VIEWPORT",
    "ENV_BROWSER",
    "Choice",
    "Ink",
    "RenderError",
    "chosen",
    "describe",
    "difference",
    "engine_matches",
    "find_renderer",
    "ink_of",
    "shoot",
    "version",
    "why_not",
]
