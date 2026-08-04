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


def _resource_candidates(*names: str) -> list[Path]:
    root = bundle_root()
    packaging = Path(__file__).resolve().parent.parent / "packaging"
    directories = [d for d in (root, packaging) if d is not None]
    return [directory / name for directory in directories for name in names]


def app_icon() -> Path | None:
    """The application icon, whether frozen or running from a checkout.

    PyInstaller's ``icon=`` only stamps the executable's Windows resource, which
    Explorer reads. The window and taskbar icons come from the toolkit at
    runtime and need the actual file.

    The ``.ico`` comes first here because ``QIcon`` reads every size it holds and
    picks the one that fits the slot being drawn. Use :func:`app_image` instead
    for anything that renders a single fixed-size bitmap.
    """
    return next((path for path in _resource_candidates("epubforge.ico", "epubforge.png") if path.is_file()), None)


def app_image() -> Path | None:
    """The icon as a single high-resolution bitmap, for drawing at one size.

    ``QPixmap`` loading a multi-size ``.ico`` takes the *first* directory entry,
    which is the 16×16 one — scaling that up to a 64-point badge is what made
    the About dialog's logo a blur. The PNG is a single 256×256 image, so it
    scales down cleanly to whatever size is asked for.
    """
    return next((path for path in _resource_candidates("epubforge.png", "epubforge.ico") if path.is_file()), None)


def set_windows_app_id(app_id: str = "EpubForge.EpubForge") -> None:
    """Give Windows an explicit AppUserModelID.

    Without one, a frozen Python GUI is grouped under the host interpreter and
    the taskbar shows that interpreter's icon instead of the application's.
    A no-op everywhere else.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        # Cosmetic only; never let it stop the application from starting.
        pass


def bundled_epubcheck_command() -> list[str] | None:
    """Command prefix running the bundled EPUBCheck on the bundled JRE."""
    java = java_executable()
    jar = epubcheck_jar()
    if java is None or jar is None:
        return None
    return [str(java), "-jar", str(jar)]
