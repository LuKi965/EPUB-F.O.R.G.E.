"""BA-2026-003: what the rebuild did, in a shape something can add up.

The baseline's argument is that the report says a great deal about *why* and
almost nothing about *what*. "4 of 10 rules removed — 17% of this stylesheet" is
a good sentence and it is a sentence: nothing can ask it how many removals this
rebuild made in total, how many of them cannot be put back, or how many were a
judgement rather than a derivation. Those are the questions somebody asks before
letting a batch overwrite a shelf.

So a change is now a record beside the finding that explains it, with a closed
vocabulary — `Action`, `Automation`, `Risk`, and whether the output alone
carries enough to undo it.

**Deliberately not every change.** A ledger of every edit is a log, and the
findings are already that. What goes in here is the set the audit names —
removal, reconstruction, relocation — because those are where being wrong costs
a reader something. A test below holds that line from the other side: an
ordinary rebuild of a clean book must not fill the ledger with noise.
"""

from __future__ import annotations

import json

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Action, Automation, Change, Report, Risk
from tests.factory import make_legacy_epub, make_modern_epub


@pytest.fixture
def legacy(tmp_path) -> str:
    return make_legacy_epub(str(tmp_path / "stara.epub"))


@pytest.fixture
def rebuilt(tmp_path, legacy):
    return rebuild(
        legacy,
        str(tmp_path / "out.epub"),
        Policy.preset("strict", validate_before_publish="off"),
    )


class TestTheLedgerAnswersWhatRatherThanWhy:
    def test_a_rebuild_that_moves_files_records_the_moves(self, rebuilt):
        moves = [c for c in rebuilt.report.changes if c.action is Action.MOVED]
        assert moves, "the whole layout was rewritten and the balance sheet is empty"

    def test_each_move_names_both_ends(self, rebuilt):
        """A count cannot answer "where did `okładka.jpg` go", which is the only
        question anybody actually asks about a relayout."""
        for change in rebuilt.report.changes:
            if change.action is Action.MOVED:
                assert change.before and change.after
                assert change.before != change.after

    def test_a_deletion_is_marked_as_one_that_cannot_be_undone(self, rebuilt):
        removals = [c for c in rebuilt.report.changes if c.action is Action.REMOVED]
        assert removals
        assert all(not c.reversible for c in removals)

    def test_and_a_move_is_marked_as_one_that_can(self, rebuilt):
        """Reversible because the report holds both names — which is what F-003
        and F-016 put there, and this is the field that makes that fact usable
        by something other than a person reading prose."""
        moves = [c for c in rebuilt.report.changes if c.action is Action.MOVED]
        assert all(c.reversible for c in moves)

    def test_every_change_points_at_the_finding_that_explains_it(self, rebuilt):
        """Two accounts of one event drift apart. This one is anchored."""
        rules = {f.rule for f in rebuilt.report.findings if f.rule}
        for change in rebuilt.report.changes:
            assert change.rule, f"{change.action.value} {change.subject} explains nothing"
            assert change.rule in rules, change.rule

    def test_the_risky_ones_say_what_they_risk(self, rebuilt):
        """`strict` unlinks references to files the book does not contain. The
        text stays and the page changes, and `appearance` is the honest word
        for that."""
        risky = [c for c in rebuilt.report.changes if c.risk is not Risk.NONE]
        assert risky, "strict took markup out of a page and called it risk-free"


class TestItCanBeAddedUp:
    def test_the_summary_counts_what_the_list_holds(self, rebuilt):
        data = rebuilt.report.to_dict()
        assert data["change_summary"]["total"] == len(rebuilt.report.changes)
        assert data["change_summary"]["irreversible"] == len(rebuilt.report.irreversible())

    def test_it_survives_the_trip_through_json(self, rebuilt):
        """The point of machine-readable is that a machine somewhere else reads
        it."""
        data = json.loads(rebuilt.report.to_json())
        assert data["schema"] >= 3
        assert data["changes"]
        for entry in data["changes"]:
            assert entry["action"] in {a.value for a in Action}
            assert entry["automation"] in {a.value for a in Automation}
            assert entry["risk"] in {r.value for r in Risk}
            assert isinstance(entry["reversible"], bool)

    def test_by_action_and_by_risk_agree_with_the_entries(self, rebuilt):
        data = rebuilt.report.to_dict()
        for action, count in data["change_summary"]["by_action"].items():
            assert count == sum(1 for c in rebuilt.report.changes if c.action.value == action)
        for risk, count in data["change_summary"]["by_risk"].items():
            assert count == sum(1 for c in rebuilt.report.changes if c.risk.value == risk)

    def test_the_vocabulary_is_closed(self):
        """An open one would be a free-text field with extra steps, and free
        text is what this replaces."""
        assert {a.value for a in Action} == {
            "removed", "replaced", "moved", "added", "carried", "reconstructed",
        }
        assert {a.value for a in Automation} == {"deterministic", "heuristic", "asked"}
        assert {r.value for r in Risk} == {"none", "appearance", "content"}


class TestItStaysABalanceSheetAndNotALog:
    def test_a_rebuild_that_changes_nothing_risky_records_nothing_risky(self, tmp_path):
        """The line this has to hold. A modern book rebuilt in preserve moves
        nothing, removes nothing and reconstructs nothing — so the ledger is
        empty, and the findings still say everything they said before."""
        source = make_modern_epub(str(tmp_path / "nowa.epub"))
        result = rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", reorganize_files=False),
        )
        assert result.report.findings, "the findings are unaffected by any of this"
        assert not [c for c in result.report.changes if c.risk is not Risk.NONE]

    def test_it_does_not_hold_observations(self, rebuilt):
        """"This book has no author" is a finding about the book, not something
        the rebuild did to it."""
        subjects = {c.subject for c in rebuilt.report.changes}
        assert not any("missing" in subject for subject in subjects)


class TestTheRecordItself:
    def test_a_change_defaults_to_the_cautious_reading(self):
        """Defaults matter in a record type: a caller who forgets a field should
        end up understating what they did, never overstating it."""
        change = Change(stage="s", action=Action.REMOVED, subject="x")
        assert change.automation is Automation.DETERMINISTIC
        assert change.risk is Risk.NONE
        assert change.reversible is True

    def test_irreversible_is_derived_and_not_stored_twice(self):
        report = Report()
        report.changed("s", Action.REMOVED, "a", reversible=False)
        report.changed("s", Action.MOVED, "b", reversible=True)
        assert [c.subject for c in report.irreversible()] == ["a"]

    def test_an_empty_report_has_an_empty_balance(self):
        data = Report().to_dict()
        assert data["changes"] == []
        assert data["change_summary"]["total"] == 0
