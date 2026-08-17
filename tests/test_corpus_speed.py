"""What the corpus run may skip, and what it may never skip.

Ninety-three books across three modes is two hundred and seventy-nine JVM
starts, and four fifths of the wall time is EPUBCheck. Measured on an
eight-core desktop the run sat at **6% CPU**: one validation at a time, the
other fifteen threads idle, an hour to learn that nothing had changed.

Two things were done about it, and only one of them is dangerous. Measuring
books side by side cannot change an answer. Reusing a recorded verdict can, so
the conditions under which it is reused are pinned here rather than trusted.

EPUBCheck is a pure function of the jar and the bytes it reads. Both are
compared; either one moving means it runs again. The second is the one worth
testing, because an EPUBCheck upgrade is exactly when the answer is expected to
change and exactly when nobody would think to look.
"""

from __future__ import annotations


import pytest

from epubforge import corpus
from epubforge.corpus import (
    MODES,
    _reusable_verdict,
    checker_identity,
    compare,
    workers_for,
)
from tests.public_corpus import (
    declared_entities,
    epub2_ncx_only,
    legacy_markup,
    nav_in_spine,
    right_to_left,
    watermarked,
)

#: Five books that differ from each other. Copying one file five times would
#: give five names and one identifier — a signature is keyed by the book's
#: bytes — and a test of parallelism that measures the same book five times is
#: measuring one book.
BUILDERS = (epub2_ncx_only, nav_in_spine, right_to_left, legacy_markup, watermarked)

#: `codes` present and empty is what a clean book records — "asked, none".
#: Absent means the verdict predates the identifiers and has to be taken again.
VERDICT = {"errors": 0, "warnings": 0, "fatal": 0, "codes": {}}


@pytest.fixture
def shelf(tmp_path):
    """Two small books and an empty signature folder."""
    books = tmp_path / "books"
    books.mkdir()
    epub2_ncx_only(books / "a.epub")
    nav_in_spine(books / "b.epub")
    return books, tmp_path / "expected"


@pytest.fixture
def quick(monkeypatch):
    """The same run with no EPUBCheck.

    Everything about the pool — ordering, scratch isolation, worker counts — is
    independent of the validator, and each validation is five and a half seconds
    of JVM. Testing them through it would put four minutes on every suite run to
    re-measure something the tests below already pin.
    """
    monkeypatch.setattr(corpus, "find_epubcheck", lambda: None)


class TestEveryModeIsMeasured:
    def test_minimal_is_among_them(self):
        """The roadmap justifies a whole corpus family — fixed layout and
        comics — as "a test of whether minimal mode engages", and the corpus
        ran that mode on nothing at all. The family was filled for a purpose
        nothing measured."""
        assert "minimal" in MODES
        assert set(MODES) == {"minimal", "preserve", "strict"}

    def test_a_signature_carries_a_block_for_each(self, shelf, quick):
        books, expected = shelf
        compare(books, expected, record=True)
        import json

        for path in expected.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for mode in MODES:
                assert mode in record, f"{path.name} has no {mode}"


class TestAVerdictIsReusedOnlyWhenItCannotHaveChanged:
    def test_same_bytes_same_checker_is_reused(self):
        previous = {"output": "sha256:abc", "checker": checker_identity(), "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:abc") == VERDICT

    def test_different_output_is_not_reused(self):
        """The whole point of the signature: different bytes, different book,
        and nothing recorded about the old ones applies."""
        previous = {"output": "sha256:abc", "checker": checker_identity(), "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:zzz") is None

    def test_a_different_checker_is_not_reused(self):
        """An EPUBCheck upgrade is when the answer is expected to change."""
        previous = {"output": "sha256:abc", "checker": "0000000000000000", "epubcheck": VERDICT}
        assert _reusable_verdict(previous, "sha256:abc") is None

    def test_a_signature_with_no_verdict_is_not_reused(self):
        previous = {"output": "sha256:abc", "checker": checker_identity()}
        assert _reusable_verdict(previous, "sha256:abc") is None

    def test_nothing_recorded_is_not_reused(self):
        assert _reusable_verdict(None, "sha256:abc") is None
        assert _reusable_verdict({}, "sha256:abc") is None

    def test_the_checker_identity_is_stable_within_a_process(self):
        assert checker_identity() == checker_identity()


@pytest.mark.skipif(
    corpus.find_epubcheck() is None, reason="no EPUBCheck to reuse a verdict from"
)
class TestTheReuseSurvivesARealRun:
    def test_a_second_run_agrees_with_the_first(self, shelf):
        """The speed-up is worth nothing if it changes an answer."""
        books, expected = shelf
        first = {r.identifier: r.status for r in compare(books, expected, record=True)}
        assert set(first.values()) == {"new"}
        second = compare(books, expected)
        assert {r.status for r in second} == {"unchanged"}

    def test_a_changed_book_is_still_validated(self, shelf, monkeypatch):
        """The reuse must not hide a book that started failing. Replacing one
        book's bytes changes the output digest, and the verdict is taken
        again."""
        books, expected = shelf
        compare(books, expected, record=True)

        calls = []
        real = corpus.validate

        def counted(path, *args, **kwargs):
            calls.append(path)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(corpus, "validate", counted)
        # Nothing moved: no JVM starts at all.
        compare(books, expected)
        assert calls == []

        # One book replaced by a genuinely different one — not a copy of the
        # other, which would carry the same bytes, the same identifier and the
        # same signature, and would be reused exactly as it should be.
        (books / "a.epub").unlink()
        replacement = declared_entities(books / "a.epub")
        compare(books, expected)
        # Once per mode, plus once for the source itself: container-only mode is
        # judged on what it added, and that needs to know what was already
        # wrong. The source is the one file whose verdict never goes stale, so
        # it is read once and reused for as long as EPUBCheck does not change.
        assert len(calls) == len(MODES) + 1
        assert sum(1 for c in calls if c == str(replacement)) == 1


class TestHowManyBooksAtOnce:
    def test_a_single_book_needs_no_pool(self):
        assert workers_for(1) == 1

    def test_it_never_exceeds_the_shelf(self):
        assert workers_for(2) <= 2

    def test_it_is_capped_so_the_machine_does_not_swap(self):
        """Each JVM wants a few hundred megabytes. A machine that starts
        thirty-two at once spends the difference in swap."""
        assert workers_for(1000) <= 8

    def test_an_explicit_request_wins(self):
        assert workers_for(1000, 3) == 3

    def test_it_is_never_zero(self):
        assert workers_for(0) >= 1
        assert workers_for(1000, 0) >= 1


class TestResultsComeBackInShelfOrder:
    def test_order_does_not_depend_on_which_book_finished_first(self, shelf, quick):
        """A corpus report that shuffles itself between runs is one nobody can
        diff, and with several books in flight the finishing order is whatever
        the machine felt like."""
        books, expected = shelf
        for index, build in enumerate(BUILDERS[2:], start=3):
            build(books / f"{chr(ord('a') + index)}.epub")
        serial = [r.book for r in compare(books, expected, workers=1)]
        parallel = [r.book for r in compare(books, expected, workers=4)]
        assert serial == parallel == sorted(serial)


class TestTheScratchIsNotShared:
    def test_two_books_do_not_write_the_same_file(self, shelf, quick):
        """Every book used to build into `scratch/preserve.epub`. Measured side
        by side, two threads would each be checking a file the other had just
        overwritten — a race that produces a plausible wrong answer rather than
        a crash, which is the worst kind."""
        books, expected = shelf
        for index, build in enumerate(BUILDERS[2:], start=3):
            build(books / f"{chr(ord('a') + index)}.epub")
        one = compare(books, expected, record=True, workers=1)
        assert len({r.identifier for r in one}) == 5, "the five books are not distinct"
        many = compare(books, expected, workers=4)
        # Measured side by side, every one still matches what it recorded alone.
        assert {r.status for r in many} == {"unchanged"}, [
            (r.book, r.status, r.differences) for r in many if r.status != "unchanged"
        ]


class TestTheJvmIsToldItDoesNotOwnTheMachine:
    """A JVM sizes its garbage collector and its compilers from the core count.

    That is right for a server running for a week and wrong for a process that
    validates one book and exits — and catastrophic eight at a time, where an
    eight-core desktop ends up with over a hundred GC and JIT threads fighting
    for eight cores. Making the corpus parallel without this made it *slower*
    while pushing the machine to 95%, which is the signature of a computer
    working hard at coordinating itself.

    Measured, four validations at a time: 17.4s with nothing, 7.0s with these.
    The largest single contributor helps a lone validation too, so this is not
    only about the corpus.
    """

    def test_the_options_are_inserted_into_a_java_invocation(self):
        from epubforge.validate import TUNING, _tuned, accepted_tuning

        command = _tuned(["/usr/bin/java", "-jar", "/opt/epubcheck.jar"])
        assert command[0] == "/usr/bin/java"
        assert command[-2:] == ["-jar", "/opt/epubcheck.jar"]
        # Either every option or none: a partially applied set is a set nobody
        # measured, and the probe answers for the whole group.
        assert tuple(command[1:-2]) in (TUNING, ())
        assert tuple(command[1:-2]) == accepted_tuning("/usr/bin/java")

    def test_no_heap_cap_is_imposed(self):
        """`-Xmx512m` was measured and made no difference at all. A cap that
        buys nothing can still make a large book fail to validate, and a false
        error is worse than a slow answer."""
        from epubforge.validate import TUNING

        assert not any(option.startswith("-Xm") for option in TUNING)

    def test_a_command_that_is_not_java_is_left_alone(self):
        """A system `epubcheck` wrapper takes no JVM options."""
        from epubforge.validate import _tuned

        assert _tuned(["/usr/bin/epubcheck"]) == ["/usr/bin/epubcheck"]
        assert _tuned(None) is None

    def test_a_runtime_that_refuses_the_options_gets_none_of_them(self):
        """HotSpot *fails to start* on an `-XX:` option it does not know, so a
        flag wrong for somebody's Java would not make validation slow, it would
        make it impossible. Other runtimes exist."""
        from epubforge.validate import accepted_tuning

        assert accepted_tuning("/definitely/not/a/java/binary") == ()

    def test_the_options_do_not_change_which_checker_this_is(self):
        """`checker_identity` decides whether a recorded verdict may be reused.
        JIT and GC settings cannot change a verdict, so they must not look like
        a different validator — that would throw away every cached answer."""
        from epubforge.validate import find_epubcheck

        command = find_epubcheck()
        if command is None:
            pytest.skip("no EPUBCheck here")
        assert not any(part.startswith("-XX:") for part in command if part.endswith(".jar"))
        assert checker_identity() == checker_identity()


class TestAModeIsJudgedOnWhatItPromised:
    """Container-only mode promises *not* to fix things, and was marked down.

    The first run that measured `minimal` over a real library reported **44
    EPUBCheck errors across 31 books** and called itself unclean. `preserve` and
    `strict` came out at zero on the same shelf. All 44 were defects the sources
    already had, carried through faithfully by the one mode that exists to
    promise it will not touch content.

    Left alone that made the alpha condition unreachable: "green across three
    consecutive releases" could never happen again, because the corpus was
    counting a promise kept as a failure.
    """

    def entry(self, tmp_path, *, source, minimal, preserve=0, strict=0):
        """One book's signature, written where the ledger will look for it."""
        import json

        from epubforge.corpus import Comparison, _log_run

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True, exist_ok=True)
        identifier = "a" * 16
        (signatures / f"{identifier}.json").write_text(
            json.dumps(
                {
                    "source": "sha256:x",
                    "source_epubcheck": {"errors": source, "warnings": 0, "fatal": 0},
                    **{
                        mode: {
                            "written": True,
                            "text_invariant": True,
                            "epubcheck": {"errors": count, "warnings": 0, "fatal": 0},
                        }
                        for mode, count in (
                            ("minimal", minimal),
                            ("preserve", preserve),
                            ("strict", strict),
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        _log_run(signatures, [Comparison("a.epub", identifier, "unchanged")])
        return json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))[-1]

    def test_errors_the_source_already_had_do_not_make_a_run_unclean(self, tmp_path):
        entry = self.entry(tmp_path, source=3, minimal=3)
        assert entry["carried"] == 3
        assert entry["introduced"] == 0
        assert entry["clean"] is True

    def test_an_error_it_added_does(self, tmp_path):
        """The check still has teeth: container-only mode may carry a defect,
        never create one."""
        entry = self.entry(tmp_path, source=3, minimal=5)
        assert entry["carried"] == 3
        assert entry["introduced"] == 2
        assert entry["clean"] is False

    def test_fixing_more_than_the_source_had_is_not_negative(self, tmp_path):
        entry = self.entry(tmp_path, source=5, minimal=1)
        assert entry["introduced"] == 0
        assert entry["carried"] == 1
        assert entry["clean"] is True

    def test_a_mode_that_rewrites_content_gets_no_such_allowance(self, tmp_path):
        """`preserve` and `strict` open every document. A source defect they
        left behind is one they failed to fix, and the number says so."""
        entry = self.entry(tmp_path, source=9, minimal=9, preserve=1)
        assert entry["errors"] == 1
        assert entry["clean"] is False

    def test_only_the_container_only_mode_gets_the_allowance(self):
        from epubforge.corpus import CARRIES_SOURCE_DEFECTS

        assert CARRIES_SOURCE_DEFECTS == {"minimal"}
        assert CARRIES_SOURCE_DEFECTS < set(MODES)

    def test_the_summary_says_whose_errors_they_were(self, tmp_path):
        """A bare "44 errors" reads as failure and was not one."""
        from epubforge.corpus import Comparison, summarise

        self.entry(tmp_path, source=3, minimal=3)
        text = summarise(
            [Comparison("a.epub", "a" * 16, "unchanged")], tmp_path / "expected"
        )
        assert "carried through by container-only mode" in text
        assert "3 source error(s)" in text
        assert "introduced" not in text


class TestARunSaysWhichRuleBroke:
    """A count is a smoke alarm with no address.

    0.2.12 reported *14 errors introduced across 13 books* in container-only
    mode. Every one of those books is on the owner's disk and on no machine of
    mine, and the signature — by design — holds nothing that would identify
    one. So there was no next question to ask: not which rule, not which kind
    of book, nothing but a number that had gone down from 20 and was still not
    zero.

    EPUBCheck stamps every message with an identifier from its own fixed
    vocabulary — `RSC-005`, `OPF-014`, `HTM-004`. That identifier is the one
    part of a message that is neither the book's text nor a path inside it, so
    recording it keeps the promise this corpus was built on and still answers
    *what broke*.
    """

    def payload(self, messages):
        return {"messages": messages}

    def message(self, identifier, severity="ERROR", path="EPUB/ch1.xhtml"):
        return {
            "ID": identifier,
            "severity": severity,
            "message": "something the book does wrong",
            "locations": [{"path": path}],
        }

    def read(self, tmp_path, payload):
        """Run `validate` against a canned EPUBCheck run."""
        import json

        from epubforge import validate as module

        written = tmp_path / "report.json"
        written.write_text(json.dumps(payload), encoding="utf-8")

        def fake_run(command, **kwargs):
            import shutil

            shutil.copyfile(written, command[command.index("--json") + 1])

            class Completed:
                returncode = 0

            return Completed()

        original_find, original_run = module.find_epubcheck, module.subprocess.run
        module.find_epubcheck = lambda: ["epubcheck"]
        module.subprocess.run = fake_run
        try:
            return module.validate(str(tmp_path / "book.epub"))
        finally:
            module.find_epubcheck, module.subprocess.run = original_find, original_run

    def test_the_identifiers_are_counted_not_just_listed(self, tmp_path):
        """Two of the same rule is a different fact from one of it."""
        result = self.read(
            tmp_path,
            self.payload(
                [
                    self.message("RSC-005"),
                    self.message("RSC-005", path="EPUB/ch2.xhtml"),
                    self.message("OPF-014"),
                ]
            ),
        )
        assert result.errors == 3
        assert result.codes == {"OPF-014": 1, "RSC-005": 2}

    def test_a_clean_book_records_an_empty_set_and_not_a_missing_one(self, tmp_path):
        """The distinction the verdict cache turns on. `{}` means "asked, and
        the answer was none"; absent means "recorded before identifiers
        existed", and that one has to be measured again."""
        result = self.read(tmp_path, self.payload([]))
        assert result.codes == {}

    def test_warnings_do_not_appear(self, tmp_path):
        """These exist to explain a failure. A book that validates clean would
        otherwise carry a list of identifiers nobody is going to read."""
        result = self.read(
            tmp_path,
            self.payload([self.message("ACC-007", severity="WARNING")]),
        )
        assert result.warnings == 1
        assert result.codes == {}

    def test_a_verdict_without_identifiers_is_not_reused(self):
        """Otherwise a private corpus keeps the old counts for ever: the books
        do not change and neither does the jar, so the reuse test passes every
        time and the identifiers never get recorded."""
        from epubforge.corpus import _reusable_verdict, checker_identity

        stored = {
            "output": "sha256:abc",
            "checker": checker_identity(),
            "epubcheck": {"errors": 1, "warnings": 0, "fatal": 0},
        }
        assert _reusable_verdict(stored, "sha256:abc") is None

        # `codes` alone is no longer enough for a verdict that found something.
        # `RSC-005` turned out to be EPUBCheck's catch-all — eleven books each
        # gained exactly one and it said only "a file does not match the
        # schema" — so a verdict with errors has to carry the sentence too.
        stored["epubcheck"]["codes"] = {"RSC-005": 1}
        assert _reusable_verdict(stored, "sha256:abc") is None

        stored["epubcheck"]["shapes"] = {"RSC-005: attribute \"width\" is invalid": 1}
        assert _reusable_verdict(stored, "sha256:abc") == stored["epubcheck"]

    def test_a_clean_verdict_needs_no_explanation(self):
        """Nothing to explain, nothing to record: a book that validates clean is
        reused on its counts, and does not carry an empty dictionary of
        sentences in ninety-three signatures to say nothing ninety-three times."""
        from epubforge.corpus import _reusable_verdict, checker_identity

        stored = {
            "output": "sha256:abc",
            "checker": checker_identity(),
            "epubcheck": {"errors": 0, "warnings": 0, "fatal": 0, "codes": {}},
        }
        assert _reusable_verdict(stored, "sha256:abc") == stored["epubcheck"]

    def test_only_the_rules_the_rebuild_broke_are_blamed(self):
        """Counted, not set-differenced. A source with one `RSC-005` and an
        output with three has gained two, and calling that "nothing new" is how
        a regression hides behind a defect the source already had."""
        from epubforge.corpus import _new_codes

        source = {"codes": {"RSC-005": 1, "HTM-004": 2}}
        produced = {"codes": {"RSC-005": 3, "OPF-014": 1}}
        assert dict(_new_codes(source, produced)) == {"RSC-005": 2, "OPF-014": 1}

    def test_the_summary_names_them(self, tmp_path):
        """What the owner reads after a run, and what he could not read before:
        not that thirteen books broke, but what they broke."""
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("a" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 0, "codes": {}},
                    "minimal": {
                        "written": True,
                        "text_invariant": True,
                        "epubcheck": {"errors": 1, "codes": {"OPF-014": 1}},
                    },
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("a.epub", "a" * 16, "unchanged")], signatures)
        # EF-048: named under the branch that produced it. The old single
        # heading covered both branches at once, so a rule the source already
        # had could stand under a sentence about what the rebuild added.
        assert "Rules the container-only mode added: OPF-014." in text

    def test_a_swap_is_not_a_clean_run(self, tmp_path):
        """EF-052, i to jest najciekawsza pułapka w tym pliku.

        `introduced` jest **różnicą dwóch liczb**. Książka, w której przebudowa
        naprawi jeden błąd źródła i dołoży inny, ma tę różnicę równą zeru — a
        dołożony błąd jest w niej tak samo, jak gdyby liczba wzrosła. Zmierzone
        na kolekcji właściciela: trzy książki, w każdej znikało `NCX-001`
        i pojawiało się `RSC-005`, a dziennik pisał `introduced: 0`.

        Wymiana błędu na inny błąd nie jest brakiem błędu.
        """
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("b" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 1, "codes": {"NCX-001": 1}},
                    "minimal": {
                        "written": True,
                        "text_invariant": True,
                        "epubcheck": {"errors": 1, "codes": {"RSC-005": 1}},
                    },
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("b.epub", "b" * 16, "unchanged")], signatures)
        assert "0 introduced" not in text
        assert "Rules the container-only mode added: RSC-005." in text, text

    def test_one_named_construct_does_not_excuse_the_error_beside_it(self, tmp_path):
        """EF-054, i **trzeci raz ten sam kształt pomyłki w dwa dni**.

        Poprzednie dwa: brama K1 usprawiedliwiana przez regułę, która nic nie
        usuwała, oraz jedno pole `codes` odpowiadające na dwa pytania. Wzór jest
        za każdym razem ten sam — obecność czegoś **gdziekolwiek** w raporcie
        usprawiedliwia coś zupełnie innego **gdzie indziej**.

        Tutaj: dopóki pytanie brzmiało „czy w regułach jest
        `xhtml.epub2-only-markup`", książka z jedną procentową szerokością
        obrazka dostawała rozgrzeszenie na wszystko, co jeszcze w niej doszło.
        Zmierzone na kolekcji: jedna książka poszła z 22 błędów na 26 i dziennik
        nazwał wszystkie cztery nieosiągalnymi, na podstawie reguły mówiącej
        o `<img width="50%">`.

        Ten fixture niesie **jedno i drugie naraz**: kształt, którego tryb
        kontenerowy faktycznie nie umie dosięgnąć, i kształt, którego dosięga.
        Pierwszy ma iść do `inherent`, drugi do `introduced`.
        """
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("c" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 0, "codes": {}, "shapes": {}},
                    "minimal": {
                        "written": True,
                        "text_invariant": True,
                        "rules": {"xhtml.epub2-only-markup": 1},
                        "epubcheck": {
                            "errors": 2,
                            "codes": {"RSC-005": 2},
                            "shapes": {
                                'RSC-005: value of attribute "width" is invalid; '
                                "must be an integer": 1,
                                "RSC-005: Error while parsing file: something "
                                "this mode really did do": 1,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("c.epub", "c" * 16, "unchanged")], signatures)
        assert "1 introduced by it" in text, text
        assert "1 it cannot reach" in text, text

    def test_and_a_shape_it_cannot_reach_is_still_forgiven(self, tmp_path):
        """Kontrola przeciwna: uściślenie miało zawęzić rozgrzeszenie, a nie je
        odebrać. Książka z samą procentową szerokością nadal nie jest niczyją
        winą."""
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("d" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 0, "codes": {}, "shapes": {}},
                    "minimal": {
                        "written": True,
                        "text_invariant": True,
                        "rules": {"xhtml.epub2-only-markup": 1},
                        "epubcheck": {
                            "errors": 1,
                            "codes": {"RSC-005": 1},
                            "shapes": {
                                'RSC-005: value of attribute "width" is invalid; '
                                "must be an integer": 1
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("d.epub", "d" * 16, "unchanged")], signatures)
        assert "introduced by it" not in text, text
        assert "1 it cannot reach" in text, text


class TestTheSummaryDoesNotBlameTheBooksOnUs:
    """A shelf of 67 books came back with `introduced: 3` in its ledger and six
    rule names printed under a heading that said "Ours". The heading was a lie
    and it worked: it sent me looking for defects in this tool that belonged to
    the books. The modes that rewrite content had their whole error list
    blamed, with no subtraction of what the source already had."""

    def test_an_error_the_source_already_had_is_not_ours(self, tmp_path):
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("b" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 2, "codes": {"CSS-008": 1, "RSC-011": 1}},
                    "minimal": {"written": True, "text_invariant": True,
                                "epubcheck": {"errors": 2,
                                              "codes": {"CSS-008": 1, "RSC-011": 1}}},
                    "preserve": {"written": True, "text_invariant": True,
                                 "epubcheck": {"errors": 2,
                                               "codes": {"CSS-008": 1, "RSC-011": 1}}},
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("b.epub", "b" * 16, "unchanged")], signatures)
        assert "CSS-008" not in text
        assert "RSC-011" not in text

    def test_an_error_only_the_rebuild_has_is_still_named(self, tmp_path):
        import json

        from epubforge.corpus import Comparison, summarise

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True)
        (signatures / ("c" * 16 + ".json")).write_text(
            json.dumps(
                {
                    "source_epubcheck": {"errors": 0, "codes": {}},
                    "preserve": {"written": True, "text_invariant": True,
                                 "epubcheck": {"errors": 1, "codes": {"RSC-005": 1}}},
                }
            ),
            encoding="utf-8",
        )
        text = summarise([Comparison("c.epub", "c" * 16, "unchanged")], signatures)
        assert "RSC-005" in text


class TestWhatTheModeCannotReachIsNotItsFault:
    """The third bucket, and the safeguard that keeps it from being a hiding
    place.

    Four defects survived into 0.2.15's container-only mode across ten books,
    and the message shapes named all four: a non-integer `width` or `height`,
    `valign`, and `value` on a list item outside an ordered list. Every one is
    markup XHTML 1.1 allowed and HTML5 does not, in a document that mode
    promises not to open — and the modes that do open documents translate all
    four into CSS and come out clean.

    Counting those against the release makes the corpus permanently unclean for
    keeping a promise, which is the same mistake `carried` was invented to fix,
    one floor up.

    But the obvious criterion — "the full rebuild was clean, so it must be the
    contract" — would have excused 0.2.11's missing `properties="svg"`: a
    package container-only mode generated and got wrong while `preserve` got it
    right. So the excuse is gated on the tool having **named the construct
    itself**. An error it does not understand is still counted against it.
    """

    def entry(self, tmp_path, *, minimal_errors, named: bool):
        import json

        from epubforge.corpus import Comparison, _log_run

        signatures = tmp_path / "expected"
        signatures.mkdir(parents=True, exist_ok=True)
        identifier = "b" * 16
        rules = {"xhtml.epub2-only-markup": 1} if named else {"xhtml.doctype-modernised": 1}
        (signatures / f"{identifier}.json").write_text(
            json.dumps(
                {
                    "source": "sha256:x",
                    "source_epubcheck": {"errors": 0, "warnings": 0, "fatal": 0, "codes": {}},
                    "minimal": {
                        "written": True,
                        "text_invariant": True,
                        "rules": rules,
                        "epubcheck": {
                            "errors": minimal_errors,
                            "warnings": 0,
                            "fatal": 0,
                            "codes": {"RSC-005": minimal_errors} if minimal_errors else {},
                        },
                    },
                    "preserve": {"written": True, "text_invariant": True,
                                 "epubcheck": {"errors": 0, "warnings": 0, "fatal": 0, "codes": {}}},
                    "strict": {"written": True, "text_invariant": True,
                               "epubcheck": {"errors": 0, "warnings": 0, "fatal": 0, "codes": {}}},
                }
            ),
            encoding="utf-8",
        )
        _log_run(signatures, [Comparison("a.epub", identifier, "unchanged")])
        return json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))[-1]

    def test_named_markup_is_inherent_and_the_run_is_clean(self, tmp_path):
        entry = self.entry(tmp_path, minimal_errors=3, named=True)
        assert entry["inherent"] == 3
        assert entry["introduced"] == 0
        assert entry["clean"] is True

    def test_an_error_it_cannot_name_still_counts(self, tmp_path):
        """0.2.11's defect, in miniature: container-only mode failed, the full
        rebuild did not, and the tool said nothing about why. That is a bug, and
        the ledger has to keep saying so."""
        entry = self.entry(tmp_path, minimal_errors=3, named=False)
        assert entry["inherent"] == 0
        assert entry["introduced"] == 3
        assert entry["clean"] is False

    def test_the_summary_distinguishes_the_two(self, tmp_path):
        from epubforge.corpus import Comparison, summarise

        self.entry(tmp_path, minimal_errors=2, named=True)
        text = summarise([Comparison("a.epub", "b" * 16, "unchanged")], tmp_path / "expected")
        assert "cannot reach without opening a document" in text
        assert "introduced" not in text

    def test_the_gate_names_the_rule_the_stage_actually_reports(self):
        """A constant that drifted from the rule id would silently stop
        excusing anything — or, worse, start excusing everything."""
        from epubforge.corpus import STRANDED_BY_MODE
        from epubforge import rules

        assert STRANDED_BY_MODE in rules.CATALOGUES["en"]
