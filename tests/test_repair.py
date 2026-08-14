"""The two things worth doing about a damaged file, since rebuilding is not one.

`allow_incomplete` is gone: a source this program could not read in full stops
the rebuild, with no setting past it. That decision is right and it is not help,
and these are the half that helps.

**Health** answers "is this file whole" by decompressing every entry, because a
ZIP's table of contents lives at the end of the file and an interrupted download
can leave it perfectly intact. The archive's own claims about itself are exactly
what a truncated copy still gets right.

**Merge** takes two copies damaged in different places and produces one that is
whole — the only operation in this program that recovers anything rather than
lowering a standard. Every entry is copied byte for byte from an archive that
gave it up cleanly; nothing is reconstructed, nothing is averaged, and two
intact copies that disagree stop the merge rather than being resolved by a
coin toss.

The damage in these tests is real damage: the compressed bytes of one entry are
flipped in place, so `zlib` fails to inflate them the way it fails on a book
that came down a bad connection. Truncating the file or removing the entry would
test a different thing — the central directory would disagree with the data, and
that is the case a reader notices immediately.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from epubforge import repair
from epubforge.pipeline import Status, rebuild
from epubforge.policy import Policy
from tests.factory import make_modern_epub


def corrupt(source: str, destination: str, victim: str) -> str:
    """Copy *source*, mangling the compressed bytes of one entry.

    The local header is skipped and the deflate stream itself is flipped, so the
    central directory still describes an entry that is simply no longer there —
    which is what bit rot and a half-finished download both leave behind.
    """
    raw = bytearray(Path(source).read_bytes())
    with zipfile.ZipFile(source) as archive:
        info = archive.getinfo(victim)
        start = info.header_offset + 30 + len(info.filename) + len(info.extra)
    for offset in range(start + 4, start + 14):
        raw[offset] ^= 0xFF
    Path(destination).write_bytes(bytes(raw))
    return destination


@pytest.fixture
def whole(tmp_path) -> str:
    return make_modern_epub(str(tmp_path / "cala.epub"))


@pytest.fixture
def documents(whole) -> list[str]:
    with zipfile.ZipFile(whole) as archive:
        return [name for name in archive.namelist() if name.endswith(".xhtml")]


@pytest.fixture
def pair(tmp_path, whole, documents) -> tuple[str, str]:
    """Two copies of one book, each missing what the other has."""
    first = corrupt(whole, str(tmp_path / "kopia-a.epub"), documents[0])
    second = corrupt(whole, str(tmp_path / "kopia-b.epub"), documents[1])
    return first, second


class TestHealthReadsRatherThanAsks:
    def test_a_whole_book_is_whole(self, whole):
        health = repair.inspect(whole)
        assert health.healthy
        assert health.entries
        assert not health.damaged

    def test_a_damaged_entry_is_found(self, pair, documents):
        health = repair.inspect(pair[0])
        assert not health.healthy
        assert [entry.name for entry in health.damaged] == [documents[0]]

    def test_and_the_reason_is_carried(self, pair):
        """"One entry is damaged" sends somebody to look; the reason is what
        tells them it is the file rather than this program."""
        assert repair.inspect(pair[0]).damaged[0].reason

    def test_the_rest_of_the_book_still_reads(self, pair):
        """The property that makes a merge possible at all: damage is per
        entry, and the entries around it are untouched."""
        health = repair.inspect(pair[0])
        assert len(health.damaged) == 1
        assert len(health.entries) > 1

    def test_something_that_is_not_an_archive_says_so_rather_than_raising(self, tmp_path):
        path = tmp_path / "nie-archiwum.epub"
        path.write_bytes(b"to nie jest zip" * 20)
        health = repair.inspect(str(path))
        assert health.unreadable
        assert not health.healthy

    def test_the_archive_own_claims_are_not_taken_for_an_answer(self, pair, documents):
        """The whole reason this decompresses rather than reading the listing:
        the central directory of a damaged copy still describes the entry
        perfectly."""
        with zipfile.ZipFile(pair[0]) as archive:
            listed = archive.getinfo(documents[0])
        assert listed.file_size > 0, "the listing still claims a size for the lost entry"
        assert not repair.inspect(pair[0]).healthy


class TestMergingTwoCopiesIntoOneWholeBook:
    def test_the_plan_takes_the_missing_entry_from_the_other_copy(self, pair, documents):
        plan = repair.plan_merge(list(pair))
        assert plan.usable
        assert plan.take[documents[0]] == pair[1]
        assert plan.repairs == 1

    def test_and_everything_else_comes_from_the_first(self, pair, documents):
        """The first copy is the book being repaired; a donor supplies only what
        the first one lost. Otherwise a "merge" is a coin toss with extra steps."""
        plan = repair.plan_merge(list(pair))
        from_donor = [name for name, source in plan.take.items() if source != plan.first]
        assert from_donor == [documents[0]]

    def test_the_merged_book_is_whole(self, tmp_path, pair):
        destination = str(tmp_path / "scalona.epub")
        result = repair.merge(list(pair), destination)
        assert result.output_path == destination
        assert repair.inspect(destination).healthy

    def test_and_it_rebuilds_where_neither_copy_would(self, tmp_path, pair):
        """End to end, and the reason any of this exists. Each copy is refused
        by the rebuild — that is F-001 working — and the merged one is not."""
        for copy in pair:
            refused = rebuild(copy, str(tmp_path / "nie.epub"), Policy.preset("preserve"))
            assert refused.status is Status.BLOCKED
            assert not (tmp_path / "nie.epub").exists()

        merged = str(tmp_path / "scalona.epub")
        repair.merge(list(pair), merged)
        result = rebuild(merged, str(tmp_path / "tak.epub"), Policy.preset("preserve"))
        assert result.status is Status.SUCCEEDED, result.report.to_text()

    def test_mimetype_comes_first_and_uncompressed(self, tmp_path, pair):
        """OCF's one layout rule. A merged archive that breaks it is not an
        EPUB, however complete its contents are."""
        destination = str(tmp_path / "scalona.epub")
        repair.merge(list(pair), destination)
        with zipfile.ZipFile(destination) as archive:
            first = archive.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED

    def test_entries_come_across_byte_for_byte(self, tmp_path, whole, pair):
        """Copied, not re-encoded. The contents of the merged book must be the
        contents of the copies, or this is a rebuild wearing a repair's name."""
        destination = str(tmp_path / "scalona.epub")
        repair.merge(list(pair), destination)
        with zipfile.ZipFile(whole) as original, zipfile.ZipFile(destination) as merged:
            for name in original.namelist():
                assert original.read(name) == merged.read(name), name


class TestItRefusesRatherThanChoosing:
    def test_one_copy_is_not_a_merge(self, whole):
        plan = repair.plan_merge([whole])
        assert plan.refused
        assert not plan.usable

    def test_an_entry_no_copy_has_stops_it(self, tmp_path, whole, documents):
        """Two copies damaged in the *same* place cannot be merged into a whole
        book, and saying so beforehand is the point of a plan."""
        first = corrupt(whole, str(tmp_path / "a.epub"), documents[0])
        second = corrupt(whole, str(tmp_path / "b.epub"), documents[0])
        plan = repair.plan_merge([first, second])
        assert documents[0] in plan.still_missing
        assert not plan.usable

    def test_and_nothing_is_written_for_an_unusable_plan(self, tmp_path, whole, documents):
        first = corrupt(whole, str(tmp_path / "a.epub"), documents[0])
        second = corrupt(whole, str(tmp_path / "b.epub"), documents[0])
        destination = tmp_path / "scalona.epub"
        result = repair.merge([first, second], str(destination))
        assert result.output_path is None
        assert not destination.exists()

    def test_two_intact_copies_that_disagree_are_a_conflict(self, tmp_path, whole, documents):
        """Not resolved here, on purpose. Two different intact answers means
        these are two different books — or one somebody edited — and picking one
        produces a book neither copy was."""
        other = make_modern_epub(str(tmp_path / "inna.epub"), title="Inna książka")
        plan = repair.plan_merge([whole, other])
        assert plan.conflicts, "two different books merged without a murmur"
        assert not plan.usable

    def test_an_existing_destination_is_never_overwritten(self, tmp_path, pair):
        """This operation exists because a file was damaged. One that destroys
        a file on its way to repairing another is the defect it was written
        against."""
        destination = tmp_path / "zajete.epub"
        destination.write_bytes("coś, co tam już leży".encode("utf-8"))
        result = repair.merge(list(pair), str(destination))
        assert result.output_path is None
        assert destination.read_bytes() == "coś, co tam już leży".encode("utf-8")

    def test_no_staging_file_is_left_behind(self, tmp_path, whole, documents):
        first = corrupt(whole, str(tmp_path / "a.epub"), documents[0])
        second = corrupt(whole, str(tmp_path / "b.epub"), documents[0])
        repair.merge([first, second], str(tmp_path / "scalona.epub"))
        assert not [name for name in os.listdir(tmp_path) if name.endswith(".part")]


class TestItIsReachableFromBothFrontEnds:
    """The owner's standing rule: everything this program does is reachable
    from the window, debugging features included."""

    def test_the_command_line_has_both(self):
        from epubforge.cli import build_parser

        actions = build_parser()._subparsers._group_actions[0].choices
        assert "health" in actions
        assert "merge" in actions

    def test_the_window_asks_about_health(self):
        from epubforge.gui.strings import EN, PL

        assert "diagnostics.health" in PL and "diagnostics.health" in EN
        assert len(PL["diagnostics.health.tip"]) > 200

    def test_and_offers_the_merge(self):
        from epubforge.gui.strings import EN, PL

        assert "menu.merge" in PL and "menu.merge" in EN
        for key in ("merge.title", "merge.intro", "merge.write", "merge.plan.conflict"):
            assert key in PL and key in EN, key

    def test_the_dialog_will_not_write_before_it_has_shown_a_plan(self):
        """Read off the source rather than by driving Qt: the property under
        test is that the button starts disabled and is only enabled by the code
        path that computes and displays a plan."""
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parent.parent
            / "epubforge" / "gui" / "merge.py"
        ).read_text(encoding="utf-8")
        assert "self.write_button.setEnabled(False)" in source
        assert "self.write_button.setEnabled(plan.usable" in source
