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
#:
#: It may fall when a rule is deliberately *withdrawn* — a behaviour we were
#: wrong about, deleted along with the finding that reported it. What it may
#: never do is fall because a `note()` lost its identifier, and every call site
#: carrying one is what the two tests below actually check.
TAGGED_TODAY = 326

def report_calls():
    """Every `note(...)` / `add(...)` in the package, as parsed syntax.

    Parsed rather than grepped. A regular expression over `rule="…"` used to be
    enough, and it silently stopped being enough the moment the identifier
    became the third positional argument — it also once matched an id that had
    been spliced into the middle of a string concatenation, which meant a
    finding was reported under an identifier like `compat.appliedapple, kindle`
    and the ratchet said everything was fine.
    """
    import ast

    for path in sorted(SOURCE.rglob("*.py")):
        if path.name in ("rules.py", "report.py", "base.py"):
            continue
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", getattr(node.func, "id", None)) not in ("note", "add"):
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            rule_node = node.args[2] if len(node.args) > 2 else keywords.get("rule")
            yield path, text, node, rule_node, keywords


def tagged_sites() -> dict[str, list[str]]:
    """rule id → the files that report it."""
    import ast

    found: dict[str, list[str]] = {}
    for path, _text, _node, rule_node, _keywords in report_calls():
        if isinstance(rule_node, ast.Constant) and isinstance(rule_node.value, str):
            found.setdefault(rule_node.value, []).append(path.name)
    return found


def test_no_call_site_computes_its_identifier():
    """An id built at runtime is an id nothing can check, and it has happened:
    a tagging pass spliced one into a string concatenation and the finding went
    out under `compat.appliedapple, kindle` for two releases."""
    import ast

    computed = [
        f"{path.name}:{node.lineno}"
        for path, _text, node, rule_node, _keywords in report_calls()
        if rule_node is not None and not isinstance(rule_node, ast.Constant)
    ]
    assert not computed, f"identifier is not a literal at: {computed}"


def test_no_call_site_writes_its_own_sentence():
    """The sentence lives in the catalogue. Passing one here would put it in two
    places, which is one place too many and exactly where they drift apart."""
    import ast

    literal = [
        f"{path.name}:{node.lineno}"
        for path, _text, node, _rule, keywords in report_calls()
        if "message" in keywords
        or (len(node.args) > 2 and isinstance(node.args[2], ast.Constant)
            and " " in str(node.args[2].value))
    ]
    assert not literal, f"a message was written at: {literal}"


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
#: sentence underneath it. Same ratchet as the tagging: may rise, may not fall
#: *while the catalogue holds the same rules*. Deleting a rule lowers it, and
#: that is not the translation going backwards — `package.input-incomplete-allowed`
#: went when the behaviour it described stopped being possible. A number that
#: could only ever rise would make deleting a dead rule look like a regression,
#: which is how dead rules survive.
TEMPLATED_TODAY = 229


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
        report.add("stage", Level.FIX, "nav.repointed", values={"count": 3})
        assert report.findings[0].rule == "nav.repointed"

    def test_the_sentence_comes_from_the_catalogue(self):
        """The call site no longer writes one, so this is where it comes from."""
        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.FIX, "nav.repointed", values={"count": 3})
        assert report.findings[0].message == rules.describe("nav.repointed", "en", {"count": 3})
        assert "3" in report.findings[0].message

    def test_the_paragraph_comes_from_the_catalogue_too(self):
        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.FIX, "nav.generated", values={"count": 7})
        assert report.findings[0].detail == rules.DETAILS["nav.generated"]

    def test_a_caller_may_still_supply_a_paragraph_that_is_data(self):
        """Eight findings have a paragraph that is a list of names or a
        generated identifier. There is nothing to catalogue, so it is passed."""
        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.INFO, "metadata.identifier-minted", detail="urn:uuid:1234")
        assert report.findings[0].detail == "urn:uuid:1234"

    def test_the_json_carries_it_too(self):
        """Anything reading `--report` output gets the stable name, not only the
        sentence — which is the whole point."""
        import json

        from epubforge.report import Level, Report

        report = Report()
        report.add("stage", Level.FIX, "nav.repointed", values={"count": 3})
        payload = json.loads(report.to_json())
        assert payload["findings"][0]["rule"] == "nav.repointed"

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
        English one stays underneath; what may not happen is that they vanish.

        A value this program translates *on purpose* counts as surviving in its
        translated form. `VOCABULARY_PL` exists for values that are our own
        fixed phrases rather than the book's data — a paragraph paradigm, a
        reason a name was rejected — and reading `wcięciem` in a Polish sentence
        is the point of it. Requiring the English word would have made the
        vocabulary and this test contradict each other, and one of them would
        have had to go.
        """
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
                    translated = rules.VOCABULARY_PL.get(str(value))
                    present = str(value) in text or (
                        translated is not None and translated in text
                    )
                    assert present, (finding.rule, value)
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


class TestTheLanguageIsASettingNotAReplacement:
    """The window has had both languages for a while; everything it writes did
    not. The saved JSON and the console were English whatever the setting said,
    which is not "bilingual" — it is Polish in one place and English in three.

    English never moves: `message` is what a script grepping the report has
    always matched, and swapping it for Polish would be a broken interface
    wearing a feature's name. The reader's language is an addition.
    """

    @staticmethod
    def _report(tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        return rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve")).report

    def test_the_json_carries_both(self, tmp_path):
        import json

        report = self._report(tmp_path)
        english = json.loads(report.to_json("en"))
        polish = json.loads(report.to_json("pl"))
        assert english["language"] == "en" and polish["language"] == "pl"

        by_rule = {f["rule"]: f for f in polish["findings"] if f.get("rule")}
        assert by_rule
        for rule, finding in by_rule.items():
            assert finding["description"] == rules.describe(rule, "pl", finding["values"])

        # The English text is identical in both documents, field for field.
        assert [f["message"] for f in english["findings"]] == [
            f["message"] for f in polish["findings"]
        ]

    def test_english_output_gains_a_description_too(self, tmp_path):
        """Not a Polish feature: an English reader gets the same field, in
        English, so a consumer never has to special-case a language."""
        import json

        english = json.loads(self._report(tmp_path).to_json("en"))
        tagged = [f for f in english["findings"] if f.get("rule")]
        assert tagged
        for finding in tagged:
            assert finding["description"] == rules.describe(finding["rule"], "en", finding["values"])

    def test_a_batch_document_carries_the_language_through(self, tmp_path):
        import json

        from epubforge.report import batch_to_json

        report = self._report(tmp_path)
        batch = json.loads(batch_to_json([report], "pl"))
        assert batch["language"] == "pl"
        assert batch["reports"][0]["language"] == "pl"
        assert any(f.get("description") for f in batch["reports"][0]["findings"])

    def test_one_renderer_serves_the_window_the_console_and_the_file(self, tmp_path):
        """The console was English-only because it built its own line from
        `finding.message` instead of asking the report."""
        report = self._report(tmp_path)
        text = report.to_text("pl")
        for finding in report.findings:
            headline = report.headline(finding, "pl").partition("\n")[0]
            assert headline in text, finding.rule

    def test_asking_for_a_language_nobody_wrote_gives_english(self, tmp_path):
        import json

        payload = json.loads(self._report(tmp_path).to_json("de"))
        tagged = [f for f in payload["findings"] if f.get("rule")]
        assert tagged
        for finding in tagged:
            assert finding["description"] == rules.describe(finding["rule"], "en", finding["values"])


#: Call sites whose detail is data rather than prose: a list of names, a byte
#: count, an example the reader reads verbatim, or a message EPUBCheck wrote.
#: There is nothing in them to translate, and a Polish entry would be a copy of
#: the English one — which is what a stalled translation looks like.
DETAILS_THAT_ARE_DATA = {
    "a11y.heading-jump",                      # the locations themselves
    "a11y.metadata-added",                    # schema.org property values
    "css.reader-property-removed",            # the property names
    "metadata.identifier-minted",             # the generated UUID
    "metadata.override-applied",              # the caller's own value
    "reader.name-rewritten",                  # old name → new name
    "css.classes-renamed",                    # the old → new map itself
    "xhtml.presentational-markup-converted",  # the tag names
    "epubcheck.reported",                     # EPUBCheck's own output
    "profile.made-by",                        # the traces themselves, verbatim
}


class TestTheDetailIsTranslatedToo:
    """The headline was translated and the paragraph under it was not.

    On a real book that paragraph was **a third of the report's text**, so
    calling the report translated was premature. This holds the rest of it: the
    number of translated details may rise and may not fall, and a detail that
    is genuinely data has to be named here rather than quietly skipped.
    """

    @staticmethod
    def _rules_with_a_detail() -> dict[str, str]:
        """Every rule that has a paragraph, wherever that paragraph lives.

        Most are in the catalogue now. The handful whose paragraph is data
        rather than prose still pass it at the call site, and both count.
        """
        import ast

        found: dict[str, str] = {rule: text for rule, text in rules.DETAILS.items()}
        for _path, text, _node, rule_node, keywords in report_calls():
            if "detail" not in keywords or not isinstance(rule_node, ast.Constant):
                continue
            found[rule_node.value] = ast.get_source_segment(text, keywords["detail"])
        return found

    def test_every_detail_is_translated_or_named_as_data(self):
        untranslated = sorted(
            rule
            for rule in self._rules_with_a_detail()
            if rule not in rules.DETAILS_PL and rule not in DETAILS_THAT_ARE_DATA
        )
        assert not untranslated, (
            f"details with no Polish and no reason recorded: {untranslated}. "
            "Translate it, or name it in DETAILS_THAT_ARE_DATA saying why not."
        )

    def test_the_data_list_does_not_grow_by_neglect(self):
        """Every entry there must be a rule that really does pass its paragraph
        at the call site — the list is an explanation, not a place to put
        things. A rule that has since been catalogued does not belong."""
        import ast

        passed_at_call_site = {
            rule_node.value
            for _path, _text, _node, rule_node, keywords in report_calls()
            if "detail" in keywords and isinstance(rule_node, ast.Constant)
        }
        stale = sorted(DETAILS_THAT_ARE_DATA - passed_at_call_site)
        assert not stale, f"named as data but no longer passing one: {stale}"

    def test_nothing_passes_a_paragraph_the_catalogue_already_has(self):
        """Two homes for one fact is one home too many."""
        import ast

        both = sorted(
            rule_node.value
            for _path, _text, _node, rule_node, keywords in report_calls()
            if "detail" in keywords
            and isinstance(rule_node, ast.Constant)
            and rule_node.value in rules.DETAILS
        )
        assert not both, f"paragraph written at the call site and catalogued: {both}"

    def test_a_translated_detail_is_not_a_copy_of_the_english_one(self):
        """The shape a stalled translation takes, and it looks finished."""
        for rule, english in self._rules_with_a_detail().items():
            polish = rules.DETAILS_PL.get(rule)
            if polish and english.startswith('"'):
                assert polish.strip('"') != english.strip('"'), rule

    def test_the_report_uses_the_translation(self, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        report = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve")).report
        text = report.to_text("pl")
        translated = [
            f for f in report.findings
            if f.detail and report.detail_for(f, "pl") != f.detail
        ]
        assert translated, "no detail reached the report translated"
        for finding in translated:
            assert report.detail_for(finding, "pl") in text
            assert finding.detail not in text, finding.rule

    def test_english_still_gets_the_original(self, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        from .factory import make_legacy_epub

        source = make_legacy_epub(str(tmp_path / "src.epub"))
        report = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve")).report
        for finding in report.findings:
            assert report.detail_for(finding, "en") == finding.detail


class TestOurOwnPhrasesTravelIntoFindings:
    """`reader.name-dropped` says "…: {reason}", and the reason is one of a
    handful of sentences this program writes in `ocf.py`. Left alone it produced
    a Polish sentence with an English clause inside it."""

    def test_a_known_phrase_is_translated_inside_a_polish_sentence(self):
        rendered = rules.describe(
            "reader.name-dropped", "pl",
            {"reason": "the name climbs out of the container with '..'"},
        )
        assert "nazwa wychodzi poza kontener" in rendered
        assert "climbs out" not in rendered

    def test_english_is_untouched_by_the_vocabulary(self):
        rendered = rules.describe(
            "reader.name-dropped", "en",
            {"reason": "the name is empty once normalised"},
        )
        assert rendered.endswith("the name is empty once normalised")

    def test_a_value_that_is_not_one_of_our_phrases_passes_through(self):
        """File names, counts and media types are data, not words."""
        assert rules.translate_values({"path": "OEBPS/case.xhtml", "count": 3}, "pl") == {
            "path": "OEBPS/case.xhtml",
            "count": 3,
        }

    def test_every_phrase_in_the_vocabulary_is_one_the_program_writes(self):
        """A vocabulary that drifts translates sentences nobody says."""
        import pathlib

        source = pathlib.Path(rules.__file__).parent
        written = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(source.rglob("*.py"))
            if path.name != "rules.py"
        )
        missing = [phrase for phrase in rules.VOCABULARY_PL if phrase not in written]
        assert not missing, f"translated but nothing says it: {missing}"


class TestARuleIdNamesTheStageThatReportsIt:
    """The prefix is not decoration: it is how a report is grouped and filtered.

    `css.remote-import-removed` was emitted by the content stage, whose findings
    carry `stage: "xhtml"` — one entry out of 135 where the two disagreed, and
    it shipped. What caught it was a survey over ninety-one real books, which is
    both the slowest possible feedback and available only to the one person with
    the library. This is the same check, in the source, in a tenth of a second.

    Stage `name` and rule prefix are not spelled identically everywhere — the
    accessibility stage reports `a11y.`, navigation reports `nav.` — so the
    aliases are written down rather than guessed at.
    """

    ALIASES = {
        "accessibility": "a11y",
        "navigation": "nav",
        "images": "image",
        "fonts": "font",
    }

    def stages(self):
        """Every Stage subclass in the package, with its declared `name`."""
        import ast
        import pathlib

        found = []
        for path in sorted(pathlib.Path("epubforge/stages").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                for item in cls.body:
                    if (
                        isinstance(item, ast.Assign)
                        and any(
                            isinstance(t, ast.Name) and t.id == "name"
                            for t in item.targets
                        )
                        and isinstance(item.value, ast.Constant)
                    ):
                        found.append((path, cls, item.value.value))
        return found

    def test_every_stage_was_found(self):
        """A parser that silently matches nothing would pass the next test."""
        assert len({name for _, _, name in self.stages()}) >= 8

    def test_no_stage_reports_under_another_stages_prefix(self):
        import ast

        wrong = []
        for path, cls, stage in self.stages():
            want = self.ALIASES.get(stage, stage)
            for call in (n for n in ast.walk(cls) if isinstance(n, ast.Call)):
                function = call.func
                if not (
                    isinstance(function, ast.Attribute) and function.attr == "note"
                ):
                    continue
                for argument in call.args:
                    if (
                        isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                        and "." in argument.value
                        and argument.value.split(".")[0] != want
                    ):
                        wrong.append(
                            f"{path.name}:{call.lineno} {cls.name} "
                            f"(stage {stage!r}, expects {want!r}.) -> {argument.value!r}"
                        )
        assert not wrong, "rule ids reported under the wrong stage:\n" + "\n".join(wrong)

    def test_both_halves_of_the_remote_import_pair_exist(self):
        """One repair, two places to find it, two ids. Deleting either would
        put the survivor back in the position the test above forbids."""
        for rule in ("css.remote-import-removed", "xhtml.remote-import-removed"):
            assert rule in rules.CATALOGUE, rule
            assert rule in rules.CATALOGUE_PL, rule
