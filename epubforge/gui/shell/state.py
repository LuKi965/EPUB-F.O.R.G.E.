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
