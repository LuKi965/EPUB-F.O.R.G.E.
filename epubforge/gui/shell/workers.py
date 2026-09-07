"""Long work, off the window's thread, with progress and a way to stop it.

One `QObject` per job, moved to its own `QThread`; only dataclasses cross the
line, and they are copies — the worker never mutates an object a page is
drawing. Cancellation is a flag the worker checks *and hands down to the
pipeline*, so pressing Cancel stops the rebuild rather than hiding the bar.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QObject, Qt, QThread, Signal


class _Job(QObject):
    """Shared plumbing: a cancel flag and the two signals every job has."""

    progress = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _report(self, step) -> None:
        self.progress.emit(step)


class AnalysisJob(_Job):
    """Read the chosen files and say what they are. Nothing is written."""

    finished = Signal(object)  # list[BookItem]

    def __init__(self, backend, paths) -> None:
        super().__init__()
        self._backend = backend
        self._paths = list(paths)

    def run(self) -> None:
        try:
            books = self._backend.analyse(
                self._paths, progress=self._report, cancelled=lambda: self._cancelled
            )
        except Exception as exc:  # noqa: BLE001 — a broken analysis is a message
            # The alternative is a dead thread and a window that never leaves
            # the progress screen.
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(books)


class RebuildJob(_Job):
    """Rebuild the chosen books, reporting each one as it lands."""

    book_finished = Signal(int, object)  # index, BookItem
    finished = Signal(object)  # BatchOutcome

    def __init__(self, backend, plan, books, resolver=None) -> None:
        super().__init__()
        self._backend = backend
        self._plan = plan
        # A copy: the page keeps drawing its own list while this one is worked
        # on, and the results arrive as new objects rather than as mutations
        # somebody else's paint event might catch half-done.
        self._books = copy.deepcopy(list(books))
        self._resolver = resolver

    def run(self) -> None:
        try:
            outcome = self._backend.rebuild(
                self._plan,
                self._books,
                progress=self._report,
                cancelled=lambda: self._cancelled,
                book_done=lambda index, book: self.book_finished.emit(index, copy.deepcopy(book)),
                resolver=self._resolver,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the window
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(outcome)


class Runner(QObject):
    """Owns one job and the thread it runs on.

    A `QObject` living in the window's thread, and that is not a detail. A job
    signal connected to a plain function is delivered **directly**, in the
    worker's thread — so the first version of this built widgets and waited on
    the thread from inside the thread itself ("QThread::wait: Thread tried to
    wait on itself", and half the layout parented across a thread boundary).
    Everything a job reports is connected to a bound method of a `QObject`
    with an explicit queued connection, which is what puts it back on the
    window's thread where Qt requires it.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.job: _Job | None = None
        self._on_done = None

    @property
    def busy(self) -> bool:
        return self.thread is not None

    def start(self, job: _Job, *, on_done=None) -> None:
        thread = QThread()
        job.moveToThread(thread)
        thread.started.connect(job.run)
        self.thread, self.job, self._on_done = thread, job, on_done
        for signal in (getattr(job, "finished", None), getattr(job, "failed", None)):
            if signal is not None:
                signal.connect(self._finished, Qt.QueuedConnection)
        thread.start()

    def _finished(self, *_args) -> None:
        self.stop()
        if self._on_done is not None:
            done, self._on_done = self._on_done, None
            done()

    def cancel(self) -> None:
        if self.job is not None:
            self.job.cancel()

    def stop(self) -> None:
        """Bring the thread down and forget it. Safe to call twice."""
        thread, self.thread, self.job = self.thread, None, None
        if thread is not None:
            thread.quit()
            thread.wait(5000)
