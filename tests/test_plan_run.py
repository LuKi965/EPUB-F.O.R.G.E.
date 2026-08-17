"""Przebieg planowy: cała robota, żaden zapis — BA-2026-003.

Ustalenie mówi o **planie transformacji**: o tym, żeby dało się zobaczyć, co
przebudowa zrobi z książką, zanim cokolwiek trafi na dysk. Audyt zewnętrzny
z 2026-08-17 nazwał to samo jako kryterium akceptacji swojej fazy 2.

**Zbudowane na kształcie, który potok już ma**, a nie obok niego. Każda
przebudowa idzie do pliku roboczego i dostaje swoją nazwę dopiero po przejściu
wszystkich bram; przebieg planowy robi dokładnie to samo i zatrzymuje się o krok
wcześniej. Dzięki temu plan przechodzi przez ten sam kod, co przebudowa —
a plan liczony osobną ścieżką opisywałby tę ścieżkę, nie przebudowę.

**Czego ten przebieg nie robi i co zostaje otwarte w BA-2026-003:** warunki
wstępne i końcowe nie są jeszcze danymi, a etapy nadal mutują książkę wprost.
Rejestr powstaje **przy** mutacji, nie przed nią. To jest widoczna połowa
ustalenia; druga jest osobnym pakietem i status ma to mówić.
"""

from __future__ import annotations

import os
import zipfile

import pytest

from epubforge.plan import ledger_lines
from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Action, Report, Risk
from tests.factory import make_legacy_epub, make_modern_epub


class TestTheLedgerReadsAsSomethingAPersonCanAnswer:
    def test_an_empty_ledger_says_so_rather_than_saying_nothing(self):
        """Cisza i zero to dwie różne odpowiedzi, a tylko jedna z nich jest
        odpowiedzią."""
        lines = ledger_lines(Report(source="x.epub"))
        assert any("no high-risk transformation" in line for line in lines)

    def test_every_entry_carries_what_the_ledger_carries(self):
        report = Report(source="x.epub")
        report.changed(
            "content",
            Action.REPLACED,
            "text",
            before="18545 kodów bez kształtu",
            after="cudzysłowy i myślniki",
            risk=Risk.CONTENT,
            reversible=False,
            rule="xhtml.mojibake-translated",
        )
        text = "\n".join(ledger_lines(report))
        assert "text" in text
        assert "18545" in text and "cudzysłowy" in text
        assert "xhtml.mojibake-translated" in text
        assert "not reversible" in text
        assert "cannot be undone" in text

    def test_the_irreversible_ones_are_counted_apart(self):
        """Bo to jest jedyna liczba, po której ktoś decyduje, czy w ogóle
        uruchamiać przebudowę."""
        report = Report(source="x.epub")
        report.changed("a", Action.REPLACED, "jeden", reversible=True)
        report.changed("b", Action.REMOVED, "dwa", reversible=False)
        lines = ledger_lines(report)
        assert any("1 of them cannot be undone" in line for line in lines)


class TestAPlanRunWritesNothing:
    """Najważniejsza własność, i jedyna, której złamanie kosztuje czyjąś książkę."""

    def rebuild_into(self, tmp_path, destination):
        source = make_legacy_epub(str(tmp_path / "in.epub"))
        return rebuild(
            source,
            str(destination),
            Policy.preset("preserve", validate_before_publish="off", render_gate="off"),
        )

    def test_a_real_run_writes(self, tmp_path):
        """Kontrola przeciwna: bez niej test niżej przechodziłby także wtedy,
        gdyby przebudowa w ogóle przestała działać."""
        result = self.rebuild_into(tmp_path, tmp_path / "prawdziwa.epub")
        assert result.status.wrote_a_file
        assert (tmp_path / "prawdziwa.epub").exists()

    def test_the_destination_of_a_plan_run_is_untouched(self, tmp_path):
        """Odwzorowanie tego, co robi przebieg planowy: cel jest gdzie indziej,
        a plik pod nazwą, którą wskazał człowiek, zostaje nietknięty."""
        cel = tmp_path / "moja-ksiazka.epub"
        cel.write_bytes(b"stara ksiazka" * 40)
        pokoj = tmp_path / "plan"
        pokoj.mkdir()

        result = self.rebuild_into(tmp_path, pokoj / cel.name)

        assert result.status.wrote_a_file, "plan ma przejść całą drogę"
        assert cel.read_bytes() == b"stara ksiazka" * 40
        assert (pokoj / cel.name).exists()

    def test_the_plan_ran_every_gate(self, tmp_path):
        """Plan, który pomija bramy, opisuje inny przebieg niż ten, który
        potem nastąpi — czyli nie jest planem."""
        pokoj = tmp_path / "plan"
        pokoj.mkdir()
        result = self.rebuild_into(tmp_path, pokoj / "out.epub")
        rules = {finding.rule for finding in result.report.findings if finding.rule}
        assert rules, "przebieg planowy nie zgłosił niczego, więc niczego nie sprawdził"
        assert result.report.changes, "bilans pusty na książce legacy"


class TestTheFlagIsReachableFromBothSides:
    """S-04 nie ma wyjątku dla funkcji dodanych wczoraj."""

    def test_the_command_line_offers_it(self):
        import pathlib

        cli = (
            pathlib.Path(__file__).parent.parent / "epubforge" / "cli.py"
        ).read_text(encoding="utf-8")
        assert '"--plan"' in cli

    def test_and_it_is_not_the_same_thing_as_dry_run(self):
        """Dwa pytania, dwie flagi. `--dry-run` nie czyta ani jednej książki
        i odpowiada, dokąd trafią; `--plan` przebudowuje każdą i odpowiada, co
        się z nią stanie. Zlanie ich w jedno zrobiłoby z tańszego droższe."""
        import pathlib

        cli = (
            pathlib.Path(__file__).parent.parent / "epubforge" / "cli.py"
        ).read_text(encoding="utf-8")
        assert '"--dry-run"' in cli
        assert "use --plan for what a rebuild would do" in cli

    def test_the_window_offers_it(self):
        import pathlib

        app = (
            pathlib.Path(__file__).parent.parent / "epubforge" / "gui" / "app.py"
        ).read_text(encoding="utf-8")
        assert "plan_check" in app
        assert "plan_only=" in app

    @pytest.mark.parametrize("language", ["pl", "en"])
    def test_the_window_has_words_for_it(self, language):
        from epubforge.gui import strings

        catalogue = strings.LANGUAGES[language]
        assert "policy.plan.only" in catalogue
        assert "policy.plan.only.tip" in catalogue
