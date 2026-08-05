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
TAGGED_TODAY = 136

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


#: How many catalogue entries are templates today — entries whose description
#: states the specifics itself, so a translated report does not need the English
#: sentence underneath it. Same ratchet as the tagging: may rise, may not fall.
TEMPLATED_TODAY = 75


class TestTheTranslationCannotStall:
    """The English line under a translated one is the visible edge of this.

    A finding whose description is generic — "images have no usable alt text" —
    cannot say *how many*, so the original sentence has to stay underneath it.
    Turning the description into a template with the value alongside is what
    removes that line, and this holds the count so the work cannot quietly
    stop halfway with nobody able to see it.
    """

    @staticmethod
    def _templated() -> set[str]:
        return {rule for rule in rules.CATALOGUE if rules.placeholders(rule)}

    def test_the_number_of_templates_has_not_gone_down(self):
        count = len(self._templated())
        assert count >= TEMPLATED_TODAY, (
            f"{count} entries are templates, down from {TEMPLATED_TODAY}. "
            "A finding that stopped stating its specifics is a translation "
            "quietly going backwards."
        )

    def test_the_recorded_number_is_honest(self):
        count = len(self._templated())
        assert count == TEMPLATED_TODAY, (
            f"{count} entries are templates now; set TEMPLATED_TODAY to {count}."
        )

    @pytest.mark.parametrize("rule", sorted(r for r in rules.CATALOGUE if rules.placeholders(r)))
    def test_both_languages_expect_the_same_values(self, rule):
        """A placeholder in one language and not the other means one of the two
        reports silently loses the number."""
        assert rules.placeholders(rule, "en") == rules.placeholders(rule, "pl"), rule

    def test_every_template_is_raised_with_the_values_it_expects(self):
        """A template nothing fills is worse than a generic description: it
        prints its own braces at the reader."""
        import ast
        import pathlib

        source = pathlib.Path(rules.__file__).parent
        supplied: dict[str, set[str]] = {}
        for path in sorted(source.rglob("*.py")):
            if path.name == "rules.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "attr", getattr(node.func, "id", None)) not in ("note", "add"):
                    continue
                keywords = {k.arg: k.value for k in node.keywords}
                rule_node = keywords.get("rule")
                if not isinstance(rule_node, ast.Constant):
                    continue
                values = keywords.get("values")
                names = (
                    {k.value for k in values.keys if isinstance(k, ast.Constant)}
                    if isinstance(values, ast.Dict)
                    else set()
                )
                supplied.setdefault(rule_node.value, set()).update(names)

        starved = sorted(
            rule
            for rule in self._templated()
            if rule in supplied and not rules.placeholders(rule) <= supplied[rule]
        )
        assert not starved, f"templates whose call site supplies no value: {starved}"


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
        assert "navigation document" in rules.describe("nav.repointed")

    def test_a_template_is_filled_from_the_values(self):
        filled = rules.describe("nav.repointed", "pl", {"count": 12})
        assert "12" in filled and "{" not in filled

    def test_a_template_given_nothing_keeps_its_braces_rather_than_raising(self):
        """A report that dies over a missing number is worse than one that
        prints a placeholder, and the caller can see which it got."""
        assert "{count}" in rules.describe("nav.repointed", "pl")
        assert not rules.renders_fully("nav.repointed", "pl", {})

    def test_an_entry_that_ignores_a_value_it_was_given_is_not_complete(self):
        """`renders_fully` decides whether the English line is still needed. A
        finding's specifics are exactly what it carries in `values`, so an entry
        that does not state one of them would lose it."""
        assert not rules.placeholders("structure.junk-removed")
        assert not rules.renders_fully("structure.junk-removed", "pl", {"count": 1})

    def test_a_finding_with_no_specifics_needs_no_second_line(self):
        """Nothing to lose means nothing to keep. This is what removed the
        English line from the findings that never interpolated anything."""
        assert rules.renders_fully("structure.junk-removed", "pl", {})
        assert rules.renders_fully("structure.junk-removed", "pl", None)

    def test_a_template_missing_one_of_its_values_is_not_complete(self):
        """The placeholder would print at the reader, braces and all."""
        assert not rules.renders_fully("structure.relaid-out", "pl", {"count": 3})

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
            assert rules.describe(finding.rule, "pl", finding.values) in text

    def test_the_specifics_are_not_traded_for_the_language(self, tmp_path):
        """The specifics — how many entries, which file, which media type — must
        survive translation. Either the Polish line states them itself, or the
        English one stays underneath; what may not happen is that they vanish."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        text = result.report.to_text("pl")
        for finding in result.report.findings:
            if not finding.rule:
                continue
            if rules.renders_fully(finding.rule, "pl", finding.values):
                for value in finding.values.values():
                    assert str(value) in text, (finding.rule, value)
            else:
                assert finding.message in text, finding.rule

    def test_a_translated_finding_that_says_everything_stands_alone(self, tmp_path):
        """The English line underneath is the visible edge of the conversion.
        Where the template states the specifics, it must be gone — otherwise the
        templates bought nothing."""
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        text = result.report.to_text("pl")
        complete = [
            f for f in result.report.findings
            if f.rule and rules.renders_fully(f.rule, "pl", f.values)
        ]
        assert complete, "no finding renders fully; the templates are not reaching the report"
        for finding in complete:
            assert f"      {finding.message}" not in text, finding.rule

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


class TestPolishCounts:
    """English gets away with "(s)". Polish does not.

    Three forms, chosen by the number: one for exactly 1, the *few* form for
    numbers ending 2–4 outside the teens, the *many* form for the rest. "1
    plików" is not clumsy phrasing, it is a mistake, and a translation full of
    them is the kind users switch off.
    """

    @pytest.mark.parametrize(
        "count, expected",
        [
            (1, "1 plik przegrupowano"),
            (2, "2 pliki przegrupowano"),
            (4, "4 pliki przegrupowano"),
            (5, "5 plików przegrupowano"),
            (12, "12 plików przegrupowano"),   # the teens take the many form
            (13, "13 plików przegrupowano"),
            (22, "22 pliki przegrupowano"),
            (25, "25 plików przegrupowano"),
            (112, "112 plików przegrupowano"),
            (0, "0 plików przegrupowano"),
        ],
    )
    def test_the_noun_agrees_with_the_number(self, count, expected):
        rendered = rules.describe(
            "structure.relaid-out", "pl", {"count": count, "directory": "EPUB"}
        )
        assert rendered.startswith(expected), rendered

    def test_a_plural_spec_never_leaves_its_forms_in_the_output(self):
        for rule in rules.CATALOGUE_PL:
            values = {name: 3 for name in rules.placeholders(rule, "pl")}
            rendered = rules.describe(rule, "pl", values)
            assert "|" not in rendered, (rule, rendered)

    def test_a_non_numeric_value_falls_back_rather_than_raising(self):
        """The value is whatever the call site passed. A report that dies
        because a count arrived as a string helps nobody."""
        rendered = rules.describe(
            "structure.relaid-out", "pl", {"count": "kilka", "directory": "EPUB"}
        )
        assert "plików" in rendered
