"""D-028: the unreachable-rule sweep, extended into `<style>` blocks — carefully.

The sheet sweep has removed dead rules since the roadmap's point [4]. Extending
it into `<style>` elements was measured before it was decided: 66 186
unreachable rules across the owner's 160 books, against the sheets' 6 303 — and
a first, accidental version of the extension shipped inside the EF-059 fix and
was withdrawn the same day, because a change of that size does not enter as a
side effect (the standing rule about removal, D-026's boundary).

What entered instead is narrower than the sheet sweep, and the narrowing is the
whole design:

* **generator-named** rules (`sgc-`, `calibre`, `mso`, `kix`…) and rules in a
  block **stamped verbatim into ≥3 documents** are code errors — removed, with
  a report line and a ledger entry;
* a dead name **one edit away from a name the book uses** may be a human's
  typo — it becomes a question (keep / drop / correct), and nothing happens
  without an answer;
* everything else dead is **kept and counted**, which is what makes the
  generator-prefix list safe to be incomplete.

First shipped off by default per the fifth audit's condition; **on by default
in both modes since D-029**, the owner's second decision of 2026-08-19, made
after the whole measurement programme ran clean: the preserve promise is about
the book's look, and a rule no selector can reach draws nothing anywhere —
"tryb preserve nie ma na celu zachować syfu, tylko zachować układ". The tick
(and `--keep-style-junk`) is the opt-out S-02 requires of every removal.
"""

from __future__ import annotations

import re
import zipfile

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><meta charset="utf-8"/>'
    "<title>R</title><style>{css}</style></head>"
    '<body><p class="rozdzial">Tekst rozdziału numer {n}.</p></body></html>'
)

#: One of each bucket, plus a live rule that must survive everything:
#: `sgc-1` is Sigil's counter, `rozdzia` is one letter from the used `rozdzial`,
#: `balonik` resembles nothing, and `rozdzial` is in use.
CSS = (
    "p.sgc-1 { color: red; } "
    "p.rozdzia { text-align: center; } "
    "p.balonik { color: blue; } "
    "p.rozdzial { margin-top: 1em; }"
)


def shelf(tmp_path, *, css: str = CSS, copies: int = 1) -> str:
    documents = {
        f"c{n}.xhtml": PAGE.format(css=css, n=n) for n in range(copies)
    }
    return make_book(tmp_path / "in.epub", documents)


def forge(source, tmp_path, *, sweep: bool, resolver=None, mode="strict"):
    policy = Policy.preset(mode)
    policy.sweep_style_blocks = sweep
    return rebuild(source, str(tmp_path / "out.epub"), policy, resolver=resolver)


def style_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if not name.endswith(".xhtml"):
                continue
            markup = archive.read(name).decode("utf-8")
            found = re.search(r"<style[^>]*>(.*?)</style>", markup, re.S)
            if found and "rozdzial" in found.group(1):
                return found.group(1)
    raise AssertionError("no swept <style> block in the rebuild")


class TestTheSwitchIsOnByDefaultAndTickable:
    def test_both_presets_sweep_by_default(self):
        """D-029. Preserve too, and that is the owner's argument verbatim:
        preserve keeps the book's layout, not the converter's litter."""
        for name in ("strict", "preserve"):
            assert Policy.preset(name).sweep_style_blocks is True

    def test_unticking_keeps_everything(self, tmp_path):
        """The opt-out S-02 requires: with the tick off, nothing is removed
        and nothing is asked — the report is the only trace."""
        result = forge(shelf(tmp_path), tmp_path, sweep=False)
        assert result.status.wrote_a_file, result.report.to_text()
        css = style_of(result)
        for selector in ("p.sgc-1", "p.rozdzia ", "p.balonik", "p.rozdzial"):
            assert selector in css, css
        assert "css.style-junk-removed" not in rules_of(result)


class TestTheThreeBuckets:
    def test_a_generator_rule_goes_and_says_so(self, tmp_path):
        result = forge(shelf(tmp_path), tmp_path, sweep=True)
        assert result.status.wrote_a_file, result.report.to_text()
        css = style_of(result)
        assert "sgc-1" not in css
        assert "css.style-junk-removed" in rules_of(result)

    def test_a_stamped_block_goes_even_without_generator_names(self, tmp_path):
        """The Word shape: the same block pasted into every chapter. No
        `sgc-` anywhere, but three identical copies are a converter's stamp."""
        stamped = "p.szablonowa { color: green; } p.rozdzial { margin: 0; }"
        result = forge(shelf(tmp_path, css=stamped, copies=3), tmp_path, sweep=True)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "szablonowa" not in style_of(result)

    def test_a_typo_candidate_is_kept_and_asked_about(self, tmp_path):
        result = forge(shelf(tmp_path), tmp_path, sweep=True)
        css = style_of(result)
        assert "rozdzia" in css  # the suspect rule survived unanswered
        assert "css.style-typo-kept" in rules_of(result)

    def test_an_unmatched_rule_is_kept_and_counted(self, tmp_path):
        result = forge(shelf(tmp_path), tmp_path, sweep=True)
        assert "balonik" in style_of(result)
        assert "css.style-unmatched-kept" in rules_of(result)

    def test_the_live_rule_survives_everything(self, tmp_path):
        result = forge(shelf(tmp_path), tmp_path, sweep=True)
        assert "p.rozdzial { margin-top: 1em; }" in style_of(result)


class _Chooser:
    """A resolver that answers every style question one way."""

    def __init__(self, option: str):
        self.option = option
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.option)


class TestTheQuestionHasTeeth:
    def test_drop_removes_the_suspect(self, tmp_path):
        chooser = _Chooser("drop")
        result = forge(shelf(tmp_path), tmp_path, sweep=True, resolver=chooser)
        assert chooser.asked, "no question reached the resolver"
        assert "p.rozdzia " not in style_of(result)

    def test_rename_makes_the_rule_apply(self, tmp_path):
        chooser = _Chooser("rename")
        result = forge(shelf(tmp_path), tmp_path, sweep=True, resolver=chooser)
        css = style_of(result)
        assert "p.rozdzial { text-align: center; }" in css

    def test_the_question_carries_both_names(self, tmp_path):
        chooser = _Chooser("keep")
        forge(shelf(tmp_path), tmp_path, sweep=True, resolver=chooser)
        question = next(q for q in chooser.asked if q.kind == "style")
        assert "rozdzia" in question.summary and "rozdzial" in question.summary
        assert {o.id for o in question.options} == {"keep", "drop", "rename"}
        assert question.recommended == "keep"


class TestPreserveSweepsTheJunkToo:
    def test_preserve_removes_generator_leftovers(self, tmp_path):
        """D-029's substance. `remove_dead` still divides preserve from strict
        over deviations a reader can see; a rule no selector reaches is
        visible nowhere, so it is not that kind of deviation."""
        result = forge(shelf(tmp_path), tmp_path, sweep=True, mode="preserve")
        assert result.status.wrote_a_file, result.report.to_text()
        css = style_of(result)
        assert "sgc-1" not in css
        assert "p.rozdzial { margin-top: 1em; }" in css
        assert "css.style-junk-removed" in rules_of(result)


class TestAScriptedBookIsLeftAlone:
    def test_nothing_is_removed_when_a_script_could_add_the_class(self, tmp_path):
        documents = {
            "c0.xhtml": PAGE.format(css=CSS, n=0),
            "s.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                '<meta charset="utf-8"/><title>S</title></head>'
                "<body><p>Strona ze skryptem.</p>"
                '<script type="text/javascript">document.body.className = "sgc-1";</script>'
                "</body></html>"
            ),
        }
        result = forge(
            make_book(tmp_path / "in.epub", documents), tmp_path, sweep=True
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert "sgc-1" in style_of(result)
        assert "css.style-junk-removed" not in rules_of(result)
        assert "css.unreachable-rules-scripted" in rules_of(result)


class TestTheCensusSurvivesSerialisation:
    def test_a_word_comment_wrapped_block_counts_as_stamped(self, tmp_path):
        """The shelf's shape that broke the first census: Word opens every
        stylesheet with `<!--`, which an XML writer escapes in the stored bytes
        while the element's text keeps it literal. The two spellings of one
        block must land on one census key — on the shelf they did not, every
        stamped Word block missed its bucket, and 52 121 machine counters were
        mistaken for typo candidates."""
        # The shelf's exact shape: Word-made XHTML wraps the stylesheet in
        # CDATA, inside which the old-browser comment markers are *text*. An
        # XML writer then escapes the `<` — the stored bytes say `&lt;!--`
        # while the element's text says `<!--`, and a census that compares
        # the two spellings raw never matches.
        word = (
            "/*<![CDATA[*/\n<!--\n"
            "p.szablonowa { color: green; } p.rozdzial { margin: 0; }\n"
            "-->\n/*]]>*/"
        )
        result = forge(shelf(tmp_path, css=word, copies=3), tmp_path, sweep=True)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "szablonowa" not in style_of(result)


class TestAMachineCounterIsNotATypo:
    def test_numbered_names_are_never_asked_about(self, tmp_path):
        """`font0` beside a used `font1` is a generator incrementing, not a
        person slipping — and there were 52 121 of these on the shelf, which
        as questions would bury every real one."""
        counters = (
            "span.font0 { color: red; } "
            'p.rozdzial { margin: 0; } '
            "span.font1 { color: blue; }"
        )
        page = PAGE.replace('class="rozdzial"', 'class="rozdzial font1"')
        documents = {"c0.xhtml": page.format(css=counters, n=0)}
        chooser = _Chooser("drop")
        result = forge(
            make_book(tmp_path / "in.epub", documents), tmp_path,
            sweep=True, resolver=chooser,
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert not [q for q in chooser.asked if q.kind == "style"], [
            q.summary for q in chooser.asked
        ]
        assert "css.style-unmatched-kept" in rules_of(result)

    def test_a_digit_edit_is_an_increment_not_a_typo(self, tmp_path):
        """`Hoofdtekst2` beside a used `Hoofdtekst9a` — the shelf's shape the
        day the typo question moved in front of the stamp bucket. The
        skeletons differ, the edit distance fits the cap, and the edit changes
        a digit: a converter counting its style variants, 30 224 rules across
        three books. A typo candidate must carry the same digits as the name
        it resembles — only letters may err (`sgc-1` beside `sgd-1` still
        asks) — so this one is swept with its stamped block, unasked."""
        word = (
            "p.Hoofdtekst2 { color: green; } "
            "p.Hoofdtekst9a { margin: 0; } "
            "p.rozdzial { margin: 0; }"
        )
        page = PAGE.replace('class="rozdzial"', 'class="rozdzial Hoofdtekst9a"')
        documents = {
            f"c{n}.xhtml": page.format(css=word, n=n) for n in range(3)
        }
        chooser = _Chooser("keep")
        result = forge(
            make_book(tmp_path / "in.epub", documents), tmp_path,
            sweep=True, resolver=chooser,
        )
        assert result.status.wrote_a_file, result.report.to_text()
        assert not [q for q in chooser.asked if q.kind == "style"], [
            q.summary for q in chooser.asked
        ]
        swept = style_of(result)
        assert "Hoofdtekst2" not in swept
        assert "Hoofdtekst9a" in swept


class TestTheProgramsOwnBlockIsSafeByConstruction:
    def test_the_cover_block_survives_the_sweep(self, tmp_path):
        """The fifth audit's fifth measurement: a block this program inserts
        (the cover repair) must be exempt from the sweep by *construction*,
        not by luck. It is — `COVER_STYLE_ADDED` styles only bare elements
        (`html`, `body`, `img`), and a bare-element selector is never called
        dead. This test pins the dependency, because the first block with a
        class that this program ever inserts will change the situation."""
        import re as _re

        from epubforge import covers
        from tests.factory import png_bytes

        assert not _re.search(r"[.#]", _re.sub(r"/\*.*?\*/", "", covers.COVER_STYLE_ADDED, flags=_re.S)), (
            "COVER_STYLE_ADDED gained a class or id selector; the sweep "
            "exemption below is no longer by construction"
        )
        documents = {
            "cover.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                '<meta charset="utf-8"/><title>Okładka</title></head>'
                '<body><div style="text-align:center">'
                '<img src="cover.png" alt="Okładka"/></div></body></html>'
            ),
            "c0.xhtml": PAGE.format(css=CSS, n=0),
        }
        result = forge(
            make_book(
                tmp_path / "in.epub",
                documents,
                extra_items='<item id="cov" href="cover.png" media-type="image/png" properties="cover-image"/>',
                extra_files={"OEBPS/cover.png": png_bytes(size=(200, 700))},
            ),
            tmp_path,
            sweep=True,
        )
        assert result.status.wrote_a_file, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            cover = next(
                archive.read(n).decode("utf-8")
                for n in archive.namelist()
                if n.endswith(".xhtml") and "<img" in archive.read(n).decode("utf-8")
            )
        assert "object-fit: contain" in cover
        assert "max-height: 100vh" in cover


class TestTheStampDoesNotSilenceTheQuestion:
    def test_a_typo_in_a_stamped_block_is_still_asked_about(self, tmp_path):
        """The sixth audit measured the first ordering: the same human typo was
        asked about in a block copied twice and silently removed in a block
        copied three times. A stamp is a fact about the block; the question is
        about one rule inside it, and copies do not answer it."""
        stamped = (
            "p.rozdzia { text-align: center; } "
            "p.szablonowa { color: green; } "
            "p.rozdzial { margin: 0; }"
        )
        chooser = _Chooser("keep")
        result = forge(
            shelf(tmp_path, css=stamped, copies=3), tmp_path,
            sweep=True, resolver=chooser,
        )
        assert result.status.wrote_a_file, result.report.to_text()
        asked = [q for q in chooser.asked if q.kind == "style"]
        assert asked, "three copies silenced the typo question"
        css = style_of(result)
        assert "p.rozdzia " in css        # kept, as answered
        assert "szablonowa" not in css    # the stamp still sweeps the rest


class TestTheUntickedBoxStillCounts:
    def test_keep_style_junk_reports_what_it_kept(self, tmp_path):
        """`--keep-style-junk` promises in its help text that the report still
        counts what a sweep would have removed — and the sixth audit measured
        the promise unkept: with the switch off, no `css.*` line at all. The
        unticked box now emits the same found-not-removed line the sheet sweep
        uses."""
        result = forge(shelf(tmp_path), tmp_path, sweep=False)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "css.unreachable-rules-found" in rules_of(result)
        assert "css.style-junk-removed" not in rules_of(result)
