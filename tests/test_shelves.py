"""Every recorded shelf, held to the same rules — not just the first one.

The ledger tests named one path for a long time, because there was one shelf.
The second shelf found two defects within a minute of arriving, both invisible
on the first, and neither would have been caught by a test that only knew about
`tests/corpus`.
"""

from __future__ import annotations

import re

import pytest

from epubforge.corpus import MODES, green_streak, widenings

from tests.shelves import DESCRIBED, ledger, shelves, signatures


def names(request=None):
    return [shelf.name for shelf in shelves()]


def test_there_is_more_than_one_shelf():
    """A regression net made of one kind of book catches one kind of
    regression. The Polish shelf has no book carrying the HTML 3.2 `<body>`
    palette, so it could not see the defect that produced 42 errors on the
    second one."""
    assert len(shelves()) >= 2


@pytest.mark.parametrize("name", names())
def test_every_shelf_says_what_it_is_for(name):
    """An unexplained pile of signatures is a pile nobody will dare change."""
    assert name in DESCRIBED, f"add {name} to tests/shelves.DESCRIBED"
    assert DESCRIBED[name].strip()


@pytest.mark.parametrize("name", names())
def test_a_shelf_has_signatures_to_compare_against(name):
    shelf = next(s for s in shelves() if s.name == name)
    assert signatures(shelf), f"{name} has a ledger and nothing to compare"


@pytest.mark.parametrize("name", names())
def test_every_ledger_entry_records_its_scope(name):
    """The streak rule counts only across runs of the same scope, so an entry
    that does not say which modes it measured cannot be compared with anything
    and silently ends a streak."""
    shelf = next(s for s in shelves() if s.name == name)
    for entry in ledger(shelf):
        assert "books" in entry, entry.get("version")
        assert set(entry.get("modes") or []) <= set(MODES), entry.get("version")


@pytest.mark.parametrize("name", names())
def test_the_streak_rule_reads_every_shelf_without_raising(name):
    """Not an assertion about the number — each shelf earns its own, and
    pinning them here would make this file need editing on every release. What
    is asserted is that the rule can read the ledger at all."""
    shelf = next(s for s in shelves() if s.name == name)
    history = ledger(shelf)
    assert isinstance(green_streak(history), list)
    assert isinstance(widenings(history), list)


@pytest.mark.parametrize("name", names())
def test_a_signature_carries_no_word_of_anybody_book(name):
    """The reason these may live in a public repository at all. A signature is
    hashes and counts; the file name is the hash of the book rather than its
    title, because a listing of titles in a public place says more about a
    shelf than about a tool."""
    shelf = next(s for s in shelves() if s.name == name)
    for path in signatures(shelf)[:20]:
        assert path.stem.isalnum() and len(path.stem) == 16, path.name
        text = path.read_text(encoding="utf-8")
        # `\b` because `xhtml.epub2-only-markup` is a rule name, not a
        # filename, and a bare substring test called it a leak.
        assert not re.search(r"\.epub\b", text), path.name


class TestTheSecondShelfIsRecorded:
    """It is here because of what it saw, and the note says so."""

    def test_it_carries_the_run_that_found_the_body_palette(self):
        shelf = next(s for s in shelves() if s.name == "corpus_mixed")
        history = ledger(shelf)
        assert history, "the mixed shelf has no recorded run"
        assert history[-1]["books"] == 67

    def test_four_books_share_a_signature_with_another(self):
        """67 books, 63 signatures. A signature is named after the hash of the
        book, so two identical files are one signature — a collection pulled off
        the internet at random has duplicates in it, and that is a fact about
        the collection rather than a gap in the record. Asserted so that a
        future gap does not hide behind it."""
        shelf = next(s for s in shelves() if s.name == "corpus_mixed")
        assert len(signatures(shelf)) == 63
        assert ledger(shelf)[-1]["books"] == 67

    def test_the_text_loss_is_recorded_rather_than_rounded_away(self):
        """One book lost 32 characters of spine text in container-only mode at
        0.2.17. A ledger that quietly dropped that would be a ledger nobody
        could use to find out when it started — and one that quietly dropped
        the run where it went back to zero would be worse, because the fix is
        the part somebody will want to date. Both entries stay pinned."""
        shelf = next(s for s in shelves() if s.name == "corpus_mixed")
        history = ledger(shelf)
        found = {entry["version"]: entry["text_lost"] for entry in history}
        assert found["0.2.17"] == 1
        assert found["0.2.18"] == 0
        assert history[-1]["text_lost"] == 0
