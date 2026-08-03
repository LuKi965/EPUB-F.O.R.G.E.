"""Locating files that ship alongside the application.

When PyInstaller freezes the app, data files land next to the executable rather
than next to the source tree, and the bundled Java runtime has to be found by
absolute path. Everything that needs a shipped resource asks here so the frozen
and source layouts stay interchangeable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Set by PyInstaller's bootloader; absent when running from source.
_FROZEN_ROOT = getattr(sys, "_MEIPASS", None)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and _FROZEN_ROOT is not None


def bundle_root() -> Path | None:
    """Directory holding bundled resources, or ``None`` when running from source."""
    return Path(_FROZEN_ROOT) if is_frozen() else None


def java_executable() -> Path | None:
    """The bundled JRE launcher, if this build ships one."""
    root = bundle_root()
    if root is None:
        return None
    name = "java.exe" if os.name == "nt" else "java"
    candidate = root / "jre" / "bin" / name
    return candidate if candidate.is_file() else None


def epubcheck_jar() -> Path | None:
    root = bundle_root()
    if root is None:
        return None
    candidate = root / "epubcheck" / "epubcheck.jar"
    return candidate if candidate.is_file() else None


def bundled_epubcheck_command() -> list[str] | None:
    """Command prefix running the bundled EPUBCheck on the bundled JRE."""
    java = java_executable()
    jar = epubcheck_jar()
    if java is None or jar is None:
        return None
    return [str(java), "-jar", str(jar)]
