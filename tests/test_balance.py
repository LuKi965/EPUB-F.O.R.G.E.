"""BA-2026-003's remaining criterion: the input→output balance closes.

The change ledger answers *what did this rebuild do*. It cannot answer *did
anything go missing*, because reading it for that means trusting every removal
to have written itself down — which is trusting the thing under suspicion.

The balance runs the other way. It counts the source, counts what is about to be
written, and requires every shrinking category to be explained by an entry in
the ledger. A resource that vanishes with nothing accounting for it stops being
a quiet omission and becomes a failed reconciliation, reported as an error.

Every test here goes through `rebuild`. The one that matters is
`test_a_loss_nothing_explains_is_an_error`, which injects a stage that drops a
document without writing a ledger entry — because a balance that has never been
shown failing is a balance nobody should believe.
"""

from __future__ import annotations

import pytest

from epubforge import balance
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Action, Risk
from epubforge.stages import DEFAULT_STAGES
from epubforge.stages.base import Stage
from tests.factory import make_legacy_epub, make_modern_epub


def rules_of(result) -> set:
    return {finding.rule for finding in result.report.findings if finding.rule}


class TestAnOrdinaryRebuildReconciles:
    def test_a_clean_book_closes(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert result.report.balance is not None
        assert result.report.balance.closes, str(result.report.balance)
        assert "package.balance-unexplained" not in rules_of(result)

    def test_a_legacy_book_closes_in_every_mode(self, tmp_path, legacy_epub):
        for mode in ("minimal", "preserve", "strict"):
            result = rebuild(
                legacy_epub,
                str(tmp_path / f"{mode}.epub"),
                Policy.preset(mode, validate_before_publish="off"),
            )
            if not result.status.wrote_a_file:
                continue
            assert result.report.balance.closes, (
                f"{mode}: {result.report.balance}"
            )

    def test_both_sides_are_counted_and_reported(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        recorded = result.report.balance.as_dict()
        assert recorded["before"]["documents"] >= 1
        assert recorded["after"]["documents"] >= 1
        assert recorded["closes"] is True

    def test_it_travels_in_the_json(self, tmp_path):
        """A balance a machine cannot read is a sentence, and the finding this
        answers is specifically about sentences."""
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        payload = result.report.to_dict()
        assert payload["schema"] >= 4
        assert payload["balance"]["closes"] is True
        assert "documents" in payload["balance"]["before"]


class TestALossHasToBeAccountedFor:
    """The tests that would have caught a silent removal.

    Both use a stage that drops a document — one that writes a ledger entry for
    it and one that does not — because the balance's whole claim is that it can
    tell those two apart.
    """

    @staticmethod
    def _dropping_stage(with_a_ledger_entry: bool):
        """Drops an **image**, deliberately, and that choice is the point.

        A dropped document is already caught, by K1: the text invariant sees the
        characters go and blocks the rebuild before it reaches a writer. An
        image carries no characters, so K1 has nothing to say about it — and a
        cover quietly missing from somebody's book is exactly the kind of loss
        the owner has ruled on twice ("losing an ornament is damage to the book
        too"). The balance is what covers the gap between them.
        """

        class DropsAnImage(Stage):
            name = "test-drop"
            mutates = True

            def run(self, ctx):
                victim = next(
                    (
                        resource
                        for path, resource in ctx.book.resources.items()
                        if path.endswith("orphan.png")
                    ),
                    None,
                )
                if victim is None:
                    return
                ctx.book.resources.pop(victim.path, None)
                if with_a_ledger_entry:
                    self.changed(
                        ctx,
                        Action.REMOVED,
                        "images",
                        before=victim.path,
                        after="",
                        risk=Risk.APPEARANCE,
                        reversible=False,
                        rule="structure.orphan-removed",
                    )

        return DropsAnImage

    def _rebuild_with(self, tmp_path, stage, name: str):
        """The book carries one image nothing points at, and that is deliberate.

        Removing a *referenced* image is caught before the balance ever runs —
        the invariant gate sees a document pointing at a file that is no longer
        there and blocks. An unreferenced one trips nothing: no text goes, no
        reference dangles, and the book validates. It is the quietest possible
        loss, which makes it the right one to hold the balance to.
        """
        import zipfile

        from tests.factory import png_bytes

        source = make_legacy_epub(str(tmp_path / f"{name}-in.epub"))
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for entry in archive.namelist():
                entries[entry] = archive.read(entry)
        opf_name = next(name for name in entries if name.endswith(".opf"))
        opf = entries[opf_name].decode()
        entries[opf_name] = opf.replace(
            "</manifest>",
            '<item id="orphan" href="orphan.png" media-type="image/png"/></manifest>',
        ).encode()
        entries[opf_name.rpartition("/")[0] + "/orphan.png"] = png_bytes()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry, data in entries.items():
                archive.writestr(entry, data)
        return rebuild(
            source,
            str(tmp_path / f"{name}-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
            stages=(*DEFAULT_STAGES, stage),
        )

    def test_a_loss_nothing_explains_is_an_error(self, tmp_path):
        result = self._rebuild_with(
            tmp_path, self._dropping_stage(False), "silent"
        )
        assert not result.report.balance.closes, result.report.balance.as_dict()
        assert "package.balance-unexplained" in rules_of(result)

    def test_the_same_loss_with_a_ledger_entry_reconciles(self, tmp_path):
        """The other half, and the one that keeps this from being a rule against
        removing anything: a removal that says so is accounted for."""
        result = self._rebuild_with(
            tmp_path, self._dropping_stage(True), "declared"
        )
        assert result.report.balance.closes, result.report.balance.as_dict()
        assert "package.balance-unexplained" not in rules_of(result)

    def test_the_message_says_what_went_missing_and_how_much(self, tmp_path):
        result = self._rebuild_with(
            tmp_path, self._dropping_stage(False), "named"
        )
        said = result.report.to_text()
        assert "images" in said or "obraz" in said


class TestTheMetadataCountIsTheWholeOfTheMetadata:
    """A check that reads a field which does not exist is a check that passes.

    `_metadata_entries` asked for `metadata.extra`. The model has no such
    attribute — it spells that vocabulary `extra_meta`, `extra_properties`,
    `extra_refinements` and `dublin_core_extra` — and the `getattr` default
    turned the mistake into a quiet zero. So the balance's metadata arm was
    counting titles, creators, identifiers and the language, and nothing else,
    while its docstring claimed it existed to catch F-011: *a whole vocabulary
    vanishing while the title stayed put*. That is precisely the loss it could
    not have seen.
    """

    def test_every_field_of_the_model_is_counted_or_named_as_bookkeeping(self):
        """The invariant, so this cannot rot again as the model grows.

        A field added to `Metadata` and forgotten here is a class of statement
        the balance stops watching, silently and with every test still green.
        """
        import dataclasses

        from epubforge.model import Metadata

        known = set(balance._METADATA_LISTS) | set(balance._METADATA_SINGLES)
        known |= set(balance._METADATA_BOOKKEEPING)
        missing = [
            entry.name
            for entry in dataclasses.fields(Metadata)
            if entry.name not in known
        ]
        assert not missing, (
            "these say something about the book and the balance does not count "
            f"them: {missing}"
        )

    def test_the_names_it_counts_are_names_the_model_has(self):
        """The other direction, and the one that actually shipped: a name that
        is not a field counts zero for ever."""
        import dataclasses

        from epubforge.model import Metadata

        fields = {entry.name for entry in dataclasses.fields(Metadata)}
        for name in (*balance._METADATA_LISTS, *balance._METADATA_SINGLES):
            assert name in fields, f"{name} is not a field of Metadata"

    def test_a_vendor_property_counts(self):
        """`ibooks:specified-fonts` is the one that exposed the model's gap.
        Here it is standing in for the whole class: dropped, the balance has to
        see the number go down."""
        from epubforge.model import Book, Metadata

        book = Book(metadata=Metadata(titles=["T"], language="pl"))
        bare = balance.Side.of(book).metadata_entries
        book.metadata.extra_properties.append(("ibooks:specified-fonts", "true", {}))
        assert balance.Side.of(book).metadata_entries == bare + 1

    def test_a_subtitle_counts_as_much_as_a_title(self):
        from epubforge.model import Book, Metadata

        two = Book(metadata=Metadata(titles=["A", "B"], language="pl"))
        moved = Book(metadata=Metadata(titles=["A"], subtitle="B", language="pl"))
        assert (
            balance.Side.of(two).metadata_entries
            == balance.Side.of(moved).metadata_entries
        )


class TestWhatItCountsAndWhatItDoesNot:
    def test_a_resource_lands_in_the_bucket_its_type_says(self):
        assert balance.kind_of("a/b.xhtml", "application/xhtml+xml") == "documents"
        assert balance.kind_of("a/b.png", "image/png") == "images"
        assert balance.kind_of("a/b.otf", "font/otf") == "fonts"
        assert balance.kind_of("a/b.css", "text/css") == "stylesheets"
        assert balance.kind_of("a/b.bin", "application/octet-stream") == "other"

    def test_the_name_answers_when_the_type_does_not(self):
        """A book that declares `application/octet-stream` for its chapters is
        somebody's export bug, not a reason to count a document as debris."""
        assert balance.kind_of("text/chapter.xhtml", "") == "documents"
        assert balance.kind_of("images/cover.jpg", "") == "images"

    def test_growing_is_not_something_to_explain(self):
        """A rebuild generates a navigation document and sometimes a cover page.
        Those are additions, they have their own ledger entries, and a balance
        that complained about them would fire on every book."""
        before = balance.Side()
        before.counts["documents"] = 2
        after = balance.Side()
        after.counts["documents"] = 4
        assert balance.reconcile(before, after, []).closes

    def test_only_removal_and_reconstruction_can_excuse_a_loss(self):
        """`MOVED` keeps the file and `REPLACED` keeps the thing it names, so
        neither can account for something that is simply not there any more."""
        before = balance.Side()
        before.counts["images"] = 3
        after = balance.Side()
        after.counts["images"] = 2

        class Entry:
            def __init__(self, action):
                self.action = action
                self.subject = "images"

        assert not balance.reconcile(before, after, [Entry(Action.MOVED)]).closes
        assert balance.reconcile(before, after, [Entry(Action.REMOVED)]).closes


class TestABalanceMayNotCryWolf:
    """The owner's first batch on 0.2.25: both books refused, and the balance
    was wrong, not the books.

    With *omit the legacy NCX* ticked — a setting he chose — the source's
    `toc.ncx` left the book, the balance saw one resource fewer in `other` with
    nothing accounting for it, and reported an error about a removal he had
    asked for.

    A false alarm from a check like this is worse than no check. It teaches the
    person reading the report to skip past the one message that means something,
    and this program's whole claim is that its messages mean something.
    """

    @staticmethod
    def _with_an_ncx(path) -> str:
        return make_legacy_epub(str(path))

    def test_dropping_the_ncx_on_request_is_not_an_unexplained_loss(self, tmp_path):
        result = rebuild(
            self._with_an_ncx(tmp_path / "in.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off", write_ncx=False),
        )
        assert result.report.balance.closes, result.report.balance.as_dict()
        assert "package.balance-unexplained" not in rules_of(result)
        assert result.status is not None

    def test_and_it_is_still_recorded_as_a_removal(self, tmp_path):
        """Not silenced — accounted for. The file really is gone, he really did
        ask, and a machine can now read both halves of that."""
        result = rebuild(
            self._with_an_ncx(tmp_path / "in.epub"),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off", write_ncx=False),
        )
        removals = [
            change for change in result.report.changes
            if change.rule == "nav.ncx-dropped"
        ]
        assert len(removals) == 1, [c.rule for c in result.report.changes]
        assert removals[0].action is Action.REMOVED

    def test_a_second_title_is_not_a_lost_title(self, tmp_path):
        """The 0.2.26 corpus run: 21 books of 93 reported a metadata entry lost.

        Every one of them was an EPUB 2 whose package carries two `<dc:title>`
        elements. The reader keeps the first as the title and moves the second
        into `subtitle`, the writer emits both with their `title-type`
        refinements, and EPUBCheck accepts the result — the statement is in the
        output, in the file, where anybody can read it.

        The balance counted `titles` and not `subtitle`, saw two become one, and
        reported a loss. Nothing was lost. A quarter of his library was told
        otherwise, which is the failure mode this class exists to prevent and
        the second time it has happened.
        """
        import zipfile

        source = make_legacy_epub(str(tmp_path / "two-titles.epub"))
        entries = {}
        with zipfile.ZipFile(source) as archive:
            for entry in archive.namelist():
                entries[entry] = archive.read(entry)
        opf_name = next(name for name in entries if name.endswith(".opf"))
        opf = entries[opf_name].decode()
        entries[opf_name] = opf.replace(
            "</dc:title>", "</dc:title><dc:title>Podtytuł tej książki</dc:title>", 1
        ).encode()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry, data in entries.items():
                archive.writestr(entry, data)

        result = rebuild(
            source,
            str(tmp_path / "two-titles-out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
        )
        assert result.report.balance.closes, result.report.balance.as_dict()
        assert "package.balance-unexplained" not in rules_of(result)

        with zipfile.ZipFile(result.output_path) as archive:
            written = next(n for n in archive.namelist() if n.endswith(".opf"))
            package = archive.read(written).decode()
        assert "Podtytuł tej książki" in package, "and it really is still there"

    def test_keeping_the_ncx_still_balances(self, tmp_path):
        """The other half: rewriting it under a new name moves a file rather
        than losing one.

        Asserted on the ledger rather than on the count, and the first draft of
        this test got that wrong — it required `other` to come out unchanged,
        and this fixture also carries a `.DS_Store` that the junk sweep removes
        and accounts for. The count is allowed to move; what may not happen is a
        move being recorded as a loss.
        """
        result = rebuild(
            self._with_an_ncx(tmp_path / "in.epub"),
            str(tmp_path / "out2.epub"),
            Policy.preset("preserve", validate_before_publish="off", write_ncx=True),
        )
        assert result.report.balance.closes, result.report.balance.as_dict()
        assert not [
            change for change in result.report.changes
            if change.rule == "nav.ncx-dropped"
        ], "the NCX was kept, so nothing may record it as removed"
