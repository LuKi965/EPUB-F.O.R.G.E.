"""What the application remembers between runs: preferences and history.

Two stores, deliberately separate. Preferences are Qt's business and live in
`QSettings` where the old window already keeps the language. History is a small
JSON file beside them, because a list of jobs is data a person may want to
read, copy or delete, and a registry key is none of those things.

What history holds is stated in `models.JobRecord` and enforced here: counts,
statuses, a preset name, a destination and at most three titles. No report
bodies, no book contents, nothing that would make this file a copy of somebody's
shelf.
"""

from __future__ import annotations

import json
import pathlib

from PySide6.QtCore import QSettings, QStandardPaths

from .models import JobRecord

#: How many jobs the list keeps. Old enough entries stop being history and
#: start being a log nobody reads.
KEEP_JOBS = 40


def settings() -> QSettings:
    """The same store the old window uses, so the language survives the change."""
    return QSettings("EPUB-Forge", "EPUB-Forge")


def history_path() -> pathlib.Path:
    location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    folder = pathlib.Path(location or pathlib.Path.home() / ".epubforge")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "history.json"


def load_history() -> list[JobRecord]:
    path = history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a history file that will not parse
        # Nobody's rebuild depends on this list. A file somebody edited, a
        # half-written file from a machine that lost power: the honest answer
        # is an empty list, not a window that will not open.
        return []
    if not isinstance(data, list):
        return []
    records = []
    for entry in data:
        if isinstance(entry, dict):
            try:
                records.append(JobRecord.from_dict(entry))
            except Exception:  # noqa: BLE001 — one malformed entry
                continue
    return records


def save_history(records: "list[JobRecord]") -> None:
    path = history_path()
    payload = [record.as_dict() for record in records[:KEEP_JOBS]]
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        # A read-only profile or a full disk. The job itself succeeded; losing
        # its line in the history is not worth an error dialog over it.
        pass


def remember(record: JobRecord) -> list[JobRecord]:
    """Put one finished job at the top and return the list as it now stands."""
    records = [record, *load_history()][:KEEP_JOBS]
    save_history(records)
    return records


def forget_history() -> None:
    save_history([])


# --------------------------------------------------------------------------
# where the dialogs open
# --------------------------------------------------------------------------

#: The folders worth remembering, each under its own key. Three, because they
#: are three different places: the shelf books come from, where rebuilt books
#: go, and where somebody keeps reports.
FOLDER_KINDS = ("input", "output", "report", "tool")


def remembering_folders() -> bool:
    """The setting, read where it is used rather than only shown in Settings.

    It has been in the window since the first version and did nothing at all:
    written to `QSettings` by the checkbox and never read by anybody.
    """
    return bool(settings().value("remember-folder", True, type=bool))


def last_folder(kind: str) -> str:
    """Where a dialog of this kind should open, or "" for the system default."""
    if kind not in FOLDER_KINDS or not remembering_folders():
        return ""
    return str(settings().value(f"folders/{kind}", "") or "")


def remember_folder(kind: str, path: str) -> None:
    """Remember the folder of *path* — the folder, never the file name."""
    if kind not in FOLDER_KINDS or not remembering_folders() or not path:
        return
    folder = pathlib.Path(path)
    if folder.is_file() or folder.suffix:
        folder = folder.parent
    settings().setValue(f"folders/{kind}", str(folder))


def forget_folders() -> None:
    """Switching the setting off is an instruction, not a pause.

    Somebody who unticks "remember the last folder" is saying they do not want
    the program keeping a note of where their books are. Leaving the values in
    place until the next run would honour the letter of that and none of it.
    """
    store = settings()
    for kind in FOLDER_KINDS:
        store.remove(f"folders/{kind}")


# --------------------------------------------------------------------------
# where the window was
# --------------------------------------------------------------------------

def save_geometry(x: int, y: int, width: int, height: int) -> None:
    """Remember where the window was, as four numbers.

    Four numbers rather than Qt's opaque `saveGeometry` blob, because what
    comes back has to be *checked* against the screens this machine has now,
    and a blob cannot be checked — `restoreGeometry` would simply put the
    window back where the second monitor used to be.
    """
    settings().setValue("window/where", [int(x), int(y), int(width), int(height)])


def remembered_geometry() -> "tuple[int, int, int, int] | None":
    stored = settings().value("window/where")
    if not stored or len(list(stored)) != 4:
        return None
    try:
        x, y, width, height = (int(value) for value in stored)
    except (TypeError, ValueError):
        return None
    if width < 200 or height < 150:
        return None
    return x, y, width, height
