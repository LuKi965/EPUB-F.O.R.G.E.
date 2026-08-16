"""Starting a child process without putting a window on somebody's screen.

A frozen GUI application on Windows has no console of its own. That is the
point of building it windowed — but it means every child process started from
it *gets* one: Windows creates a console for the child, which is a black
rectangle that appears on top of whatever the person was looking at, lives as
long as the child does, and then vanishes.

For the validator that was one window per book, and it was fixed where it was
found — inside `validate`. For the renderer it is **one window per screenshot**,
which the owner saw as a black box flashing roughly once a second for as long
as a batch ran, and described exactly right: distracting, and suspicious to
anybody standing near the screen. A program asking to be trusted with somebody's
library may not look like it is doing something it should not be.

The same fix in two modules is a fix waiting to be forgotten in a third, so it
lives here, and `test_no_child_process_opens_a_window` reads the source of the
whole package to make sure nothing spawns anything any other way.

Everywhere other than Windows this is empty and the calls are ordinary
`subprocess` calls, unchanged.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

#: Documented value of `CREATE_NO_WINDOW`, in case the constant is missing —
#: it only exists on Windows builds of Python, and `getattr` on a module that
#: does have it is still the right way to ask.
_CREATE_NO_WINDOW = 0x08000000


def no_console() -> "dict[str, Any]":
    """Keyword arguments that keep a child process off the screen.

    `CREATE_NO_WINDOW` is the documented way to say *do not give this child a
    console*. `STARTUPINFO` with `SW_HIDE` covers the other half: a child that
    creates a window of its own rather than inheriting a console. Neither exists
    outside Windows, hence the guard.
    """
    if os.name != "nt":
        return {}
    options: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)
    }
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    options["startupinfo"] = startupinfo
    return options


def run(command, **kwargs):
    """`subprocess.run`, with no window.

    A wrapper rather than a note in a docstring, because the note is what failed:
    `validate` had the flags from the day the problem was found there and
    `render` was written afterwards without them.
    """
    return subprocess.run(command, **no_console(), **kwargs)


def popen(command, **kwargs):
    """`subprocess.Popen`, with no window."""
    return subprocess.Popen(command, **no_console(), **kwargs)


__all__ = ["no_console", "popen", "run"]
