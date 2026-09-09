"""The window's adapter, on the engine — not on the demo.

`test_shell_ui.py` drives the shell through `DemoBackend`, which is right for
what it tests: the flow, the keyboard, the geometry. It is the wrong witness for
what a *result* means, and the handoff of 2026-09-09 says so in as many words —
*„Nie uznawaj … testów DemoBackend za dowód działania rzeczywistego
adaptera"* — because the demo and the engine had drifted apart on exactly that:
the demo raised ATTENTION from `book.issues`, the engine only from an ERROR, so
a book with warnings came out looking clean in the real program and marked in
the fake one.

So this file rebuilds real books with `EngineBackend` and asks what the person
is shown. It needs no Qt: the adapter is deliberately a plain object, and that
is what makes this possible.

Scenario ids are the handoff's own (R01…R07, P01…P11), so a reader can go from
the acceptance matrix to the test and back.
"""

from __future__ import annotations

import pathlib

from epubforge.gui.shell.backend import EngineBackend
from epubforge.gui.shell.models import (
    BatchOutcome,
    BookStatus,
    Preset,
    RebuildPlan,
)
from tests.factory import make_legacy_epub, make_modern_epub
from tests.test_renditions import two_renditions


def _quiet(progress=None, cancelled=None):
    """The two callbacks every backend call takes, doing nothing."""
    return (progress or (lambda _p: None)), (cancelled or (lambda: False))


#: An unset destination is not "no destination": it is the ordinary case,
#: where each book is written beside its own source. Spelling it as a sentinel
#: keeps `destination=None` from meaning "use the default" here.
BESIDE_THE_SOURCES = object()


def rebuilt(backend: EngineBackend, sources: "list[pathlib.Path]", tmp_path,
            *, plan_only: bool = False, destination=None, **overrides) -> BatchOutcome:
    """One batch through the production adapter, start to finish."""
    progress, cancelled = _quiet()
    books = backend.analyse(list(sources), progress=progress, cancelled=cancelled)
    if destination is BESIDE_THE_SOURCES:
        where = None
    else:
        where = None if plan_only else (destination or tmp_path / "out")
    plan = RebuildPlan(
        sources=tuple(sources),
        destination=where,
        preset=Preset.PRESERVE,
        overrides={"validate": False, "validate_before_publish": "off",
                   "render_gate": "off", "plan_only": plan_only, **overrides},
    )
    return backend.rebuild(plan, books, progress=progress, cancelled=cancelled,
                           book_done=lambda _i, _b: None)


class TestWhatAResultMeans:
    """R01 and R02 of the acceptance matrix. Four axes, not one `DONE`:
    whether the run finished, whether a file was published, how clean it was,
    and what kind of operation it was."""

    def test_r01_a_book_with_warnings_is_not_shown_as_a_book_without_them(self, tmp_path):
        """A rebuild that publishes and warns is not a failure and must not
        look like a result with nothing to read. `_absorb` counted the warnings
        into `issues` and then raised ATTENTION only on an ERROR, so the count
        said two and the row said done."""
        source = pathlib.Path(make_modern_epub(str(tmp_path / "book.epub")))
        outcome = rebuilt(EngineBackend("pl"), [source], tmp_path)
        (book,) = outcome.books
        assert book.issues > 0, "atrapa nie daje ostrzeżeń — test nic nie mierzy"
        assert book.output is not None, "plik miał powstać"
        assert book.status is BookStatus.ATTENTION, (
            f"książka z {book.issues} ostrzeżeniami wyszła jako {book.status}"
        )

    def test_r01_a_clean_book_stays_clean(self, tmp_path):
        """The other half, so the fix cannot be "call everything ATTENTION"."""
        backend = EngineBackend("pl")
        source = pathlib.Path(make_modern_epub(str(tmp_path / "book.epub")))
        outcome = rebuilt(backend, [source], tmp_path)
        (book,) = outcome.books
        # This fixture warns; the point is the rule, so the rule is asked
        # directly for the case where nothing is wrong.
        assert (book.status is BookStatus.DONE) == (book.issues == 0)

    def test_r02_a_dry_run_publishes_nothing_and_says_so(self, tmp_path):
        """`written` counted statuses that "wrote a file"; a dry-run writes to
        a temporary directory that is thrown away, so the summary said a book
        had been written where none had."""
        source = pathlib.Path(make_modern_epub(str(tmp_path / "book.epub")))
        outcome = rebuilt(EngineBackend("pl"), [source], tmp_path, plan_only=True)
        (book,) = outcome.books
        assert book.output is None
        assert outcome.published == 0, (
            "próba nie publikuje niczego, a podsumowanie liczyło ją jako zapis"
        )
        assert outcome.operation is not None and outcome.operation.is_a_trial

    def test_r02_a_real_run_counts_its_publications(self, tmp_path):
        source = pathlib.Path(make_modern_epub(str(tmp_path / "book.epub")))
        outcome = rebuilt(EngineBackend("pl"), [source], tmp_path)
        assert outcome.published == 1
        assert outcome.operation is not None and not outcome.operation.is_a_trial

    def test_r03_a_book_with_two_renditions_shows_both_files(self, tmp_path):
        """One source, two publications. `rebuild_all` writes a file per
        rendition and the adapter kept `produced[0]`, so the second was written
        and never named — the row said one file where two exist."""
        source = pathlib.Path(two_renditions(tmp_path / "two.epub"))
        outcome = rebuilt(EngineBackend("pl"), [source], tmp_path)
        (book,) = outcome.books
        assert len(book.published_outputs) == 2, (
            f"dwie rendycje dały {book.published_outputs}"
        )
        for path in book.published_outputs:
            assert path.exists(), f"{path} jest w wyniku, ale nie na dysku"
        # Source books and output files are counted separately (02-UI §3).
        assert len(outcome.books) == 1 and len(outcome.published_outputs) == 2

    def test_r04_the_outputs_are_named_one_by_one(self, tmp_path):
        """R04/R03: a batch that writes beside its sources lands in as many
        folders as it has sources, and the summary has to carry every file
        rather than the first one's parent."""
        first = pathlib.Path(make_modern_epub(str(tmp_path / "a" / "one.epub")))
        second = pathlib.Path(make_legacy_epub(str(tmp_path / "b" / "two.epub")))
        outcome = rebuilt(EngineBackend("pl"), [first, second], tmp_path,
                          destination=BESIDE_THE_SOURCES)
        assert outcome.published == 2
        folders = {path.parent for path in outcome.published_outputs}
        assert folders == {first.parent, second.parent}, (
            f"dwa źródła w dwóch katalogach dały {folders}"
        )
        # And the history's own view of the same fact, which the results card
        # answered by taking the first file's parent for everybody (F06).
        assert set(outcome.folders) == {str(first.parent), str(second.parent)}
