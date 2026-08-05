"""The catalogue of findings, and the ratchet that finishes it.

EF-018: the identity of a finding used to be its English sentence, which is why
`survey.py` strips numbers and quotes with regular expressions before it can
count anything, why rewording a message once broke a test that was not about
the wording, and why the report cannot be translated.

`epubforge/rules.py` gives each finding a name that does not change. Converting
the call sites is not a single change — there are more than a hundred — so this
file holds the conversion to a ratchet: the number of tagged sites may go up
and may not go down, and the catalogue may not drift in either direction. A
half-finished migration nobody can see is how migrations die.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from epubforge import rules

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "epubforge"

#: How many call sites carry a rule today. Raise it as more are converted;
#: lowering it means a finding lost its identity, which is the thing this whole
#: module exists to prevent.
TAGGED_TODAY = 67

#: Every `rule="…"` written anywhere in the package.
_RULE_ARGUMENT = re.compile(r'rule\s*=\s*"([a-z0-9.\-]+)"')


def tagged_sites() -> dict[str, list[str]]:
    """rule id → the files that report it."""
    found: dict[str, list[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if path.name == "rules.py":
            continue
        for rule in _RULE_ARGUMENT.findall(path.read_text(encoding="utf-8")):
            found.setdefault(rule, []).append(path.name)
    return found


class TestTheCatalogueAndTheCodeAgree:
    def test_every_rule_reported_is_in_the_catalogue(self):
        """An id that is not catalogued cannot be described or translated, and
        will not be noticed missing."""
        unknown = sorted(r for r in tagged_sites() if not rules.known(r))
        assert not unknown, f"reported but not catalogued: {unknown}"

    def test_every_catalogued_rule_is_reported_by_something(self):
        """The other direction. A catalogue that lists findings nothing raises
        gets consulted and believed."""
        reported = set(tagged_sites())
        # Entries for call sites not yet converted are legitimate — they are the
        # plan. What is not legitimate is an entry for something that no longer
        # exists at all, and those are the ones with no plausible owner.
        orphaned = sorted(
            rule
            for rule in rules.CATALOGUE
            if rule not in reported and rule.split(".")[0] not in _AREAS_STILL_BEING_CONVERTED
        )
        assert not orphaned, f"catalogued but nothing raises it: {orphaned}"

    def test_every_entry_says_what_it_means(self):
        empty = [rule for rule, text in rules.CATALOGUE.items() if not text.strip()]
        assert not empty, empty

    @pytest.mark.parametrize("rule", sorted(rules.CATALOGUE))
    def test_ids_follow_the_shape(self, rule):
        assert re.fullmatch(r"[a-z0-9]+\.[a-z0-9-]+", rule), rule


#: Areas whose call sites are still being converted, so a catalogue entry with
#: no caller is a plan rather than a mistake. Shrinks as the work lands; when it
#: is empty this list goes away with it.
_AREAS_STILL_BEING_CONVERTED = {"epubcheck", "package"}


class TestTheMigrationCannotStall:
    def test_the_number_of_tagged_sites_has_not_gone_down(self):
        count = sum(len(files) for files in tagged_sites().values())
        assert count >= TAGGED_TODAY, (
            f"{count} call sites carry a rule, down from {TAGGED_TODAY}. "
            "A finding that lost its identity is the defect this file exists for."
        )

    def test_the_recorded_number_is_honest(self):
        """If the count has risen, the constant is stale and should be raised —
        otherwise the ratchet stops ratcheting."""
        count = sum(len(files) for files in tagged_sites().values())
        assert count == TAGGED_TODAY, (
            f"{count} call sites now carry a rule; set TAGGED_TODAY to {count}."
        )


class TestTheFindingCarriesIt:
    def test_a_report_keeps_the_rule(self):
        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.FIX, "coś zrobiono", rule="nav.repointed")
        assert report.findings[0].rule == "nav.repointed"

    def test_the_json_carries_it_too(self):
        """Anything reading `--report` output gets the stable name, not only the
        sentence — which is the whole point."""
        import json

        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.FIX, "coś zrobiono", rule="nav.repointed")
        payload = json.loads(report.to_json())
        assert payload["findings"][0]["rule"] == "nav.repointed"

    def test_an_untagged_finding_still_works(self):
        """Until the migration finishes, most findings have no id and the
        program must not care."""
        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.INFO, "jeszcze bez identyfikatora")
        assert report.findings[0].rule is None
        assert report.to_json()

    def test_a_real_rebuild_produces_tagged_findings(self, tmp_path):
        """The mechanism has to survive an actual run, not only a unit test."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        tagged = [f for f in result.report.findings if f.rule]
        assert tagged, [f.message for f in result.report.findings]
        for finding in tagged:
            assert rules.known(finding.rule), finding.rule


class TestDescribing:
    def test_a_known_rule_is_described(self):
        assert rules.describe("nav.repointed").startswith("references")

    def test_an_unknown_rule_returns_itself(self):
        """A missing dictionary entry must not stop a report from printing."""
        assert rules.describe("nie.ma-takiej") == "nie.ma-takiej"
