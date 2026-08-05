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
TAGGED_TODAY = 79

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


#: Every area is converted, so a catalogued id that nothing raises is a mistake
#: rather than a plan. The exemption list is empty and stays here as the place
#: to name an area if one is ever added ahead of its call sites.
_AREAS_STILL_BEING_CONVERTED: set[str] = set()


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


class TestTheCorpusRecordsWhichRulesFired:
    """A signature that moves has to say *what* moved.

    Before this, a corpus diff read "report.fix: 5 → 6" — a number went up, and
    finding out which behaviour changed meant rebuilding the book by hand. With
    identifiers the same diff reads "+a11y.missing-alt ×3, −nav.entry-dropped",
    which is a sentence about the program rather than about a counter.
    """

    def test_a_signature_carries_the_distribution(self, tmp_path):
        from epubforge.corpus import signature

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "book.epub"))
        recorded = signature(pathlib.Path(source), tmp_path)
        rules_fired = recorded["preserve"]["rules"]
        assert rules_fired, recorded["preserve"]
        for rule in rules_fired:
            assert rules.known(rule), rule

    def test_a_new_rule_reads_as_an_arrival(self):
        from epubforge.corpus import differences

        moved = differences(
            {"preserve": {"rules": {"structure.relaid-out": 1}}},
            {"preserve": {"rules": {"structure.relaid-out": 1, "a11y.missing-alt": 3}}},
        )
        assert moved == ["preserve.rules: +a11y.missing-alt ×3"]

    def test_a_rule_that_stopped_reads_as_a_departure(self):
        from epubforge.corpus import differences

        moved = differences(
            {"preserve": {"rules": {"nav.entry-dropped": 2}}},
            {"preserve": {"rules": {}}},
        )
        assert moved == ["preserve.rules: −nav.entry-dropped"]

    def test_a_count_that_changed_says_both_numbers(self):
        from epubforge.corpus import differences

        moved = differences(
            {"preserve": {"rules": {"a11y.missing-alt": 1}}},
            {"preserve": {"rules": {"a11y.missing-alt": 4}}},
        )
        assert moved == ["preserve.rules: a11y.missing-alt 1→4"]

    def test_an_unchanged_distribution_says_nothing(self):
        """The opposite failure: a diff that fires on every run is a diff nobody
        reads, and the whole corpus stops being believed."""
        from epubforge.corpus import differences

        same = {"preserve": {"rules": {"structure.relaid-out": 1}}}
        assert differences(same, same) == []


class TestTheReportSpeaksPolish:
    """The second of the two unmet alpha conditions.

    The interface has been bilingual for a while and the report has not, for a
    structural reason rather than a lack of effort: a sentence that *is* the
    identity of a finding cannot be swapped for its Polish equivalent without
    changing what it identifies. The catalogue is what made this possible, and
    it is what a translation replaces.
    """

    def test_both_catalogues_describe_the_same_findings(self):
        """A half-translated catalogue falls back to English silently and looks
        like a finished translation, which is worse than an obvious gap."""
        assert set(rules.CATALOGUE) == set(rules.CATALOGUE_PL)

    def test_no_polish_entry_is_left_in_english(self):
        """A copied English line is the shape a stalled translation takes."""
        identical = [
            rule
            for rule in rules.CATALOGUE
            if rules.CATALOGUE[rule] == rules.CATALOGUE_PL[rule]
        ]
        assert not identical, identical

    def test_every_polish_entry_says_something(self):
        empty = [rule for rule, text in rules.CATALOGUE_PL.items() if not text.strip()]
        assert not empty, empty

    def test_a_language_nobody_wrote_falls_back_rather_than_failing(self):
        """A report in the wrong language is still a report; one that refuses to
        print is not."""
        assert rules.describe("nav.repointed", "de") == rules.describe("nav.repointed")

    def test_the_report_renders_in_polish(self, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        text = result.report.to_text("pl")

        assert text.startswith("Raport EPUB F.O.R.G.E.")
        tagged = [f for f in result.report.findings if f.rule]
        assert tagged
        for finding in tagged:
            assert rules.describe(finding.rule, "pl") in text

    def test_the_specifics_are_not_traded_for_the_language(self, tmp_path):
        """Thirty-seven messages still interpolate their values directly, so the
        original line stays underneath the translated one. Dropping it would buy
        Polish with information — how many entries, which file — and that is the
        wrong trade."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        text = result.report.to_text("pl")
        for finding in result.report.findings:
            if finding.rule:
                assert finding.message in text

    def test_english_is_unchanged(self, tmp_path):
        """Nothing about the existing report moves. A translation that alters the
        original is a rewrite wearing a translation's name."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        text = result.report.to_text()
        assert text.startswith("EPUB-Forge report")
        assert "obrazy nie mają" not in text
