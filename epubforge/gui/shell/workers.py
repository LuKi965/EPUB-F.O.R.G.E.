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
    """Shared plumbing: a cancel flag and the two signals every job has.

    **Every signal names its session first.** A job that was cancelled, or one
    whose last word was queued to the window a moment before the person started
    something else, still arrives — and arrives at a page that has moved on. It
    used to be written into whatever list was there by then (F05); now the page
    can see whose result it is holding and drop the ones that are not its own.
    """

    progress = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, session: str = "") -> None:
        super().__init__()
        self._cancelled = False
        self.session = session

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _report(self, step) -> None:
        self.progress.emit(self.session, step)


class AnalysisJob(_Job):
    """Read the chosen files and say what they are. Nothing is written."""

    finished = Signal(str, object)  # session, list[BookItem]

    def __init__(self, backend, paths, session: str = "") -> None:
        super().__init__(session)
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
            self.failed.emit(self.session, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self.session, books)


class RebuildJob(_Job):
    """Rebuild the chosen books, reporting each one as it lands."""

    book_finished = Signal(str, int, object)  # session, index, BookItem
    finished = Signal(str, object)  # session, BatchOutcome

    def __init__(self, backend, plan, books, resolver=None) -> None:
        # The plan already says whose it is, and the outcome carries it back:
        # one token from the page's request to the engine's answer.
        super().__init__(getattr(plan, "session_id", ""))
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
                book_done=lambda index, book: self.book_finished.emit(
                    self.session, index, copy.deepcopy(book)
                ),
                resolver=self._resolver,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the window
            self.failed.emit(self.session, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self.session, outcome)


class ToolJob(_Job):
    """One specialist tool, run off the window's thread.

    The work itself is a function in `gui.toolwork` — no Qt, no widgets — and
    this only carries it across the thread boundary and reports what it says on
    the way. Both windows run the same functions; only this side differs.
    """

    finished = Signal(str, object)  # session, ToolAnswer

    def __init__(self, work, session: str = "") -> None:
        super().__init__(session)
        self._work = work

    def run(self) -> None:
        from .models import Progress

        def tick(done: int, total: int, name: str) -> None:
            self.progress.emit(self.session, Progress(done, total, name, "tool"))

        try:
            answer = self._work(tick)
        except Exception as exc:  # noqa: BLE001 — a tool that fails says so
            # These read whole shelves of somebody else's books. A broken one is
            # a message in the result area, not a window that closes.
            self.failed.emit(self.session, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self.session, answer)


class Runner(QObject):
    """Owns one job and the thread it runs on, and ends both without waiting.

    A `QObject` living in the window's thread, and that is not a detail. A job
    signal connected to a plain function is delivered **directly**, in the
    worker's thread — so the first version of this built widgets and waited on
    the thread from inside the thread itself ("QThread::wait: Thread tried to
    wait on itself", and half the layout parented across a thread boundary).
    Everything a job reports is connected to a bound method of a `QObject`
    with an explicit queued connection, which is what puts it back on the
    window's thread where Qt requires it.

    **Ending is a state machine, not a wait.** The version this replaces did
    `thread.quit(); thread.wait(5000)` on the window's thread — five seconds
    during which the interface was frozen and, if the job was blocked on a
    question, five seconds that ended with the thread abandoned rather than
    finished. Now the job's end only *asks* the thread to stop, and everything
    else — deleting the job and the thread, clearing the references, saying the
    runner is idle — happens when `QThread.finished` says it really has:

        job.finished/failed → thread.quit()
        thread.finished     → deleteLater, forget, on_done, idle

    so nothing waits and nothing is destroyed while it is still running.
    """

    #: The thread has ended and this runner owns nothing. The window closes on
    #: this rather than on a timer.
    idle = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.job: _Job | None = None
        self._on_done = None
        self._cancelled = False
        self._over = False
        self._pending: tuple | None = None

    @property
    def busy(self) -> bool:
        """A thread of ours exists. It may be running or winding down."""
        return self.thread is not None or self._pending is not None

    @property
    def working(self) -> bool:
        """A job is actually running.

        Not the same as `busy`: between a job saying its last word and its
        thread finishing there is a short stretch where the runner still owns a
        thread and no work is happening. The interface asks *this* — refusing
        the next run for those few milliseconds would be a button that ignores
        a click for no reason a person could see.
        """
        return self.job is not None and not self._over

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def start(self, job: _Job, *, on_done=None) -> None:
        """Run *job*. If the last thread is still winding down, run it next.

        Queued rather than refused: the wind-down is invisible and lasts a few
        milliseconds, so "the button did nothing" is the only way a person
        could ever experience a refusal here.
        """
        if self.busy:
            self._pending = (job, on_done)
            return
        thread = QThread()
        job.moveToThread(thread)
        thread.started.connect(job.run)
        # Qt's own idiom, and the reason it is Qt's own idiom: `deleteLater`
        # posts a deferred-delete event **to the object's thread**, and this
        # object lives on `thread`. Connected here, the call happens while that
        # thread is still winding down and Qt delivers the event as part of its
        # teardown. Called later from the window's thread — which is what
        # `_thread_ended` used to do — the event is posted to a thread whose
        # loop has already ended, and nothing ever delivers it: the job simply
        # stayed alive (F10).
        thread.finished.connect(job.deleteLater)
        thread.finished.connect(self._thread_ended, Qt.QueuedConnection)
        for signal in (getattr(job, "finished", None), getattr(job, "failed", None)):
            if signal is not None:
                signal.connect(self._work_over, Qt.QueuedConnection)
        self.thread, self.job, self._on_done = thread, job, on_done
        # A job queued while the last thread was ending may already have been
        # cancelled — by the window closing, say — and starting it must not
        # forget that. It is the job that carries the flag; this only reports.
        self._cancelled = job.cancelled
        self._over = False
        thread.start()

    def _work_over(self, *_args) -> None:
        """The job has said its last word. Ask the thread to leave its loop.

        Nothing is cleared here: the page's own handler for the same signal may
        still be running, and the thread has not finished yet.
        """
        self._over = True
        if self.thread is not None:
            self.thread.quit()

    def _thread_ended(self) -> None:
        """The thread really has stopped. Now everything can go.

        The job is already gone by here — `thread.finished` deleted it on its
        own thread, where a deferred delete can still be delivered. This drops
        the runner's references and the thread, which lives on this one.
        """
        thread = self.thread
        self.thread = self.job = None
        if thread is not None:
            thread.deleteLater()
        done, self._on_done = self._on_done, None
        if done is not None:
            done()
        waiting, self._pending = self._pending, None
        if waiting is not None:
            self.start(waiting[0], on_done=waiting[1])
            return
        self.idle.emit()

    def cancel(self) -> None:
        """Ask the work to stop. Idempotent, and safe when nothing is running."""
        self._cancelled = True
        if self._pending is not None:
            # Cancelled before it started, and still started: the job checks
            # its own flag, reports that it stopped, and the page gets the
            # signal it is waiting for. Dropping it here would leave the flow
            # on a progress screen that nothing will ever finish.
            self._pending[0].cancel()
        if self.job is not None:
            self.job.cancel()

    def stop(self) -> None:
        """Cancel and ask the thread to end. Returns at once; see `idle`."""
        self.cancel()
        if self.thread is not None:
            self.thread.quit()

    def wait_for_idle(self, milliseconds: int = 5000) -> bool:
        """Block until the thread has ended. **Tests and teardown only.**

        Never call this from the interface: it is the wait this class exists to
        get rid of. It is here because a test that ends while a thread is still
        running takes the next test down with it.
        """
        from PySide6.QtCore import QCoreApplication, QDeadlineTimer

        deadline = QDeadlineTimer(milliseconds)
        while self.busy and not deadline.hasExpired():
            thread = self.thread
            if thread is not None:
                thread.wait(20)
            QCoreApplication.processEvents()
        return not self.busy
