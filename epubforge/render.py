"""Rendering a page to pixels, so "does it still look like itself" can be asked.

F-028. The fidelity checks this program had compare *structure* — text, shapes,
media, reading order, style — and every one of them can pass on a book that
comes out cropped, stretched, blank or with the dedication pushed off the
bottom of the page. Nothing here had ever looked at a rendered page.

The renderer is Chromium, driven headless through its own command line. Two
things about that choice, both deliberate:

**It is not a dependency of the program.** Nothing in a rebuild renders
anything, and an installer that carried a browser to repair an EPUB would be
absurd. This module *finds* a browser if the machine has one and says plainly
what is missing if it does not — reachable from the window either way, because
"the check you are asking for needs something you do not have, here is what"
is an answer and a greyed-out button is not.

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
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

#: Overridden first, because somebody with two browsers should be able to say
#: which — and because this is how the tests point it at a stub.
ENV_BROWSER = "EPUBFORGE_CHROME"

#: Names a browser goes by, in the order they are tried.
_NAMES = (
    "chromium", "chromium-browser", "chrome", "google-chrome",
    "google-chrome-stable", "msedge",
)

#: Where Playwright puts the browsers it downloads. Searched because a machine
#: that has run any Python browser automation already has one, and asking
#: somebody to install a second copy is asking for nothing.
_PLAYWRIGHT = "PLAYWRIGHT_BROWSERS_PATH"

#: Where Windows actually keeps the browser everybody already has.
#:
#: Found by a failed release build and worth stating plainly, because searching
#: `PATH` alone made the whole feature useless on the only platform this program
#: is released for. **Edge is installed on every Windows 10 and 11 machine and is
#: not on `PATH`** — it lives under Program Files, and so does Chrome. So
#: `find_renderer` answered `None` on a normal Windows box, the gate defaulted to
#: `stop`, and every rebuild from the command line was refused for want of a
#: browser sitting right there.
#:
#: That is exactly the outcome the owner ruled out — a missing tool holding
#: somebody's book hostage — arrived at by looking for the tool in one place.
_WINDOWS_PROGRAMS = (
    r"Microsoft\Edge\Application\msedge.exe",
    r"Google\Chrome\Application\chrome.exe",
    r"Chromium\Application\chrome.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
)

#: Rendered at this size unless asked otherwise. A six-inch reader at 1×, which
#: is the device the owner's library is read on.
DEFAULT_VIEWPORT = (600, 800)

#: Chromium exits non-zero on a page it could not lay out; anything longer than
#: this is a hang and not a slow page.
_TIMEOUT = 60


def _candidates() -> "list[pathlib.Path]":
    found: list[pathlib.Path] = []
    override = os.environ.get(ENV_BROWSER)
    if override:
        found.append(pathlib.Path(override))
    for name in _NAMES:
        located = shutil.which(name)
        if located:
            found.append(pathlib.Path(located))
    root = os.environ.get(_PLAYWRIGHT)
    if root and pathlib.Path(root).is_dir():
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe",
                        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
            found.extend(sorted(pathlib.Path(root).glob(pattern)))
    if os.name == "nt":
        found.extend(pathlib.Path(name) for name in windows_installs(os.environ))
    return found


def windows_installs(environ) -> "list[str]":
    """Where Edge and Chrome sit on Windows, as plain strings.

    Takes the environment and returns strings rather than reading `os.environ`
    and building `Path`s, for one reason: a `WindowsPath` cannot be constructed
    on Linux, so anything that builds one is a function only a Windows machine
    can test. That is the shape of defect this whole thing came out of, and it
    is not worth repeating one level down.
    """
    names: list[str] = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = environ.get(variable)
        if not base:
            continue
        for relative in _WINDOWS_PROGRAMS:
            names.append(base.rstrip("\\/") + "\\" + relative)
    return names


def find_renderer() -> "pathlib.Path | None":
    for candidate in _candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def why_not() -> str:
    """What to tell somebody who has no renderer. Sentences, not a stack trace."""
    return (
        "Ta kontrola rysuje strony i porównuje obrazy, więc potrzebuje "
        "przeglądarki opartej na Chromium — Chrome, Chromium albo Edge. "
        "Nie jest częścią programu i nie jest instalowana razem z nim: "
        "przebudowa książki niczego nie rysuje.\n\n"
        f"Szukane w PATH pod nazwami: {', '.join(_NAMES)}, a na Windowsie "
        f"dodatkowo tam, gdzie instalują się Edge i Chrome. Jeżeli masz "
        f"przeglądarkę gdzie indziej, wskaż ją zmienną {ENV_BROWSER}."
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
        finished = subprocess.run(
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
            subprocess.run(
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
    "Ink",
    "RenderError",
    "difference",
    "engine_matches",
    "find_renderer",
    "ink_of",
    "shoot",
    "version",
    "why_not",
]
