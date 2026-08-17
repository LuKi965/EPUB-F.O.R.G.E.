"""Interpunkcja, którą konwersja zamieniła w kody bez kształtu — EF-050.

Windows-1252 trzyma cudzysłowy, myślniki i wielokropek na pozycjach `0x80`–`0x9f`.
Unikod trzyma tam kody sterujące. Konwerter czytający tekst z Windowsa jak
Latin-1 zamienia każdy z tych znaków w kod, którego żadna czcionka nie rysuje —
i zapisuje go w pliku na trwałe.

**Że to nie jest błąd naszego odczytu**, warto powiedzieć raz i tutaj: pliki,
na których to znaleziono, deklarują UTF-8 i **są** poprawnym UTF-8. Uszkodzenie
jest w treści.

Zmierzone na obu półkach właściciela: **dwie książki na sto sześćdziesiąt**,
jedna z 18 545 takimi znakami, druga z trzema. Rzadkie, a kiedy wystąpi —
masowe.

Do 0.2.28 znaki te były **usuwane**, więc brama K1 słusznie odmawiała takiej
książki i nie dało się jej przebudować wcale. Dziś są tłumaczone, ale wyłącznie
po pytaniu: to jest zmiana znaków tekstu, a S-02 nie ma wyjątku dla zmian
oczywiście słusznych.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge import decisions, mojibake
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import make_modern_epub, write_zip

#: „ ” ’ — jako bajty cp1252, czyli tak, jak siedzą w uszkodzonym pliku.
ZEPSUTE = "\u0093Ala\u0094 ma\u0097kota\u0092"
NAPRAWIONE = "\u201cAla\u201d ma\u2014kota\u2019"


class Odpowiada:
    """Człowiek, który odpowiada zawsze tak samo."""

    def __init__(self, option: str) -> None:
        self.option = option
        self.questions: list = []

    def ask(self, question):
        self.questions.append(question)
        if question.kind != decisions.ENCODING:
            return decisions.Answer(option=decisions.KEEP)
        return decisions.Answer(option=self.option)


class TestTheTable:
    """Zbudowana przez kodek, nie przepisana ręcznie — więc test sprawdza, że
    kodek daje to, czego się po nim spodziewamy, a nie że przepisałem dobrze."""

    def test_it_has_the_twenty_seven_defined_positions(self):
        assert len(mojibake.TRANSLATION) == 27

    @pytest.mark.parametrize(
        "position,character",
        [(0x91, "‘"), (0x92, "’"), (0x93, "“"),
         (0x94, "”"), (0x97, "—"), (0x85, "…"), (0x80, "€")],
    )
    def test_the_punctuation_maps_where_it_should(self, position, character):
        assert mojibake.TRANSLATION[position] == character

    @pytest.mark.parametrize("position", [0x81, 0x8D, 0x8F, 0x90, 0x9D])
    def test_the_undefined_positions_are_absent(self, position):
        """Za nimi nie stoi żaden znak w żadnym kodowaniu. To one — i tylko one
        z tego bloku — są usuwane jako niebędące tekstem."""
        assert position not in mojibake.TRANSLATION

    def test_a_letter_is_never_touched(self):
        assert mojibake.repaired("zażółć gęślą jaźń") == "zażółć gęślą jaźń"
        assert mojibake.repairable("zażółć gęślą jaźń") == 0


class TestTheInvariantSeesThemAsTheSameText:
    """Bez tego brama K1 zablokowałaby własną naprawę: podmiana `0x93` na „
    wyglądałaby jak zniknięcie jednego znaku i pojawienie się innego."""

    def test_the_repaired_text_folds_to_the_same_form(self):
        from epubforge import typography

        assert typography.canonical(ZEPSUTE) == typography.canonical(NAPRAWIONE)

    def test_but_a_different_letter_still_does_not(self):
        from epubforge import typography

        assert typography.canonical("kot") != typography.canonical("kod")


class TestOnARealRebuild:
    def book(self, tmp_path, name: str = "zepsuta.epub") -> str:
        source = make_modern_epub(str(tmp_path / (name + ".clean")))
        entries: dict[str, bytes] = {}
        with zipfile.ZipFile(source) as archive:
            for entry in archive.namelist():
                if entry == "mimetype":
                    continue
                entries[entry] = archive.read(entry)
        chapter = next(
            entry for entry in entries
            if entry.endswith(".xhtml") and b"<p>" in entries[entry]
        )
        entries[chapter] = entries[chapter].replace(
            b"<p>", "<p>{}".format(ZEPSUTE).encode("utf-8"), 1
        )
        return write_zip(str(tmp_path / name), entries)

    def rebuilt(self, tmp_path, asker=None, **policy):
        source = self.book(tmp_path)
        return rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off", **policy),
            asker=asker,
        )

    def text_of(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return b"".join(
                archive.read(name)
                for name in archive.namelist()
                if name.endswith(".xhtml")
            ).decode("utf-8")

    def test_nobody_asked_means_nothing_changes(self, tmp_path):
        """Najważniejszy test w tym pliku. Przebieg bez człowieka — korpus,
        wsad, biblioteka — ma zostawić książkę dokładnie taką, jaka była."""
        result = self.rebuilt(tmp_path)
        assert result.status.wrote_a_file, result.report.to_text()
        assert "\u0093" in self.text_of(result)
        assert "“" not in self.text_of(result)

    def test_and_it_says_so(self, tmp_path):
        result = self.rebuilt(tmp_path)
        rules = {finding.rule for finding in result.report.findings}
        assert "xhtml.mojibake-found" in rules, sorted(rules)

    def test_answering_repair_puts_the_punctuation_back(self, tmp_path):
        asker = Odpowiada("repair")
        result = self.rebuilt(tmp_path, asker=asker)
        assert result.status.wrote_a_file, result.report.to_text()
        text = self.text_of(result)
        assert "“" in text and "—" in text
        assert "\u0093" not in text

    def test_the_question_shows_what_it_found(self, tmp_path):
        """Osoba ma zobaczyć znaki i liczby, nie bajty. „616 × ’" jest
        odpowiadalne, „616 × 0x92" nie."""
        asker = Odpowiada("keep")
        self.rebuilt(tmp_path, asker=asker)
        asked = [q for q in asker.questions if q.kind == decisions.ENCODING]
        assert asked, "nie zapytano wcale"
        question = asked[0]
        assert "”" in question.detail or "“" in question.detail
        assert question.option(decisions.KEEP) is not None
        assert question.recommended == "repair"
        assert not question.reversible

    def test_answering_keep_keeps(self, tmp_path):
        asker = Odpowiada("keep")
        result = self.rebuilt(tmp_path, asker=asker)
        assert "\u0093" in self.text_of(result)

    def test_the_standing_answer_repairs_without_asking(self, tmp_path):
        """Przełącznik dla całej kolejki. Nie jest piątym sposobem na zmianę
        tekstu bez pytania — jest odpowiedzią udzieloną z góry."""
        asker = Odpowiada("keep")
        result = self.rebuilt(tmp_path, asker=asker, repair_encoding=True)
        assert "“" in self.text_of(result)
        assert not [q for q in asker.questions if q.kind == decisions.ENCODING]

    def test_the_repair_is_in_the_ledger(self, tmp_path):
        """Zmiana znaków tekstu bez wpisu w bilansie jest dokładnie tym, czego
        BA-2026-003 zabrania."""
        result = self.rebuilt(tmp_path, repair_encoding=True)
        changes = [
            change for change in result.report.changes
            if change.rule == "xhtml.mojibake-translated"
        ]
        assert changes, [change.rule for change in result.report.changes]
        assert not changes[0].reversible

    def test_a_clean_book_is_asked_nothing(self, tmp_path):
        asker = Odpowiada("repair")
        source = make_modern_epub(str(tmp_path / "czysta.epub"))
        rebuild(
            source,
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", validate_before_publish="off"),
            asker=asker,
        )
        assert not [q for q in asker.questions if q.kind == decisions.ENCODING]
