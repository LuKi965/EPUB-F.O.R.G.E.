"""README ma mówić prawdę o kodzie, a nie o kodzie sprzed trzech wydań.

WP-19. Zarzut właściciela brzmiał: tekst jest przestarzały i przeczy logice
plików README. Przy przepisywaniu wyszły trzy rzeczy **wprost nieprawdziwe**,
nie tylko nieaktualne:

* „Znaki wodne i wpisy wydawcy **nie są usuwane**" — WP-17 dołożył przełącznik,
  który je usuwa. README obiecywał czegoś przeciwnego niż program robi.
* „Do bety brakuje już tylko jednej rzeczy: ktoś spoza autora" — ten warunek
  został skreślony decyzją D-011 i zastąpiony przebiegami. README nadal
  powoływał się na skreślony warunek.
* liczba testów sprzed kilku wydań.

Każda z nich to zdanie, które **było prawdziwe, kiedy je pisano**, i żadna nie
psuła niczego głośno. Dlatego jest tu test: dokument, którego nikt nie sprawdza
maszynowo, starzeje się dokładnie w tym tempie, w jakim rośnie program.

Sprawdzane jest to, co da się sprawdzić bez zgadywania — liczby i nazwy. Ton,
układ i to, czy tekst jest dobry, testem nie są i być nie mogą.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
POLISH = (ROOT / "README.md").read_text(encoding="utf-8")
ENGLISH = (ROOT / "README.en.md").read_text(encoding="utf-8")
BOTH = {"README.md": POLISH, "README.en.md": ENGLISH}


class TestTheNumbersAreThisVersionsNumbers:
    def test_the_test_count_is_a_floor_the_suite_still_clears(self):
        """Próg, nie dokładna liczba — i to jest wybór, nie lenistwo.

        Pierwsza wersja tego testu wymagała dokładnej liczby i **sama ją
        zmieniła**: dopisanie dziewiętnastu testów sprawdzających README
        podniosło licznik, którego te testy pilnowały. Dokładna liczba w README
        zmusza do edycji dokumentu przy każdym dopisanym teście, a dokument
        edytowany mechanicznie przestaje być czytany.

        Więc README podaje próg, a test pilnuje obu stron: że próg jest
        prawdziwy i że nie odjechał tak daleko, by przestał cokolwiek znaczyć.
        """
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--collect-only"],
            capture_output=True, text=True, cwd=ROOT,
        ).stdout
        found = re.search(r"(\d+) tests? collected", collected)
        assert found, collected[-400:]
        actual = int(found.group(1))
        for name, text in BOTH.items():
            floor = re.search(r"(\d{4})\*{0,2} (?:testów|tests)", text)
            assert floor, f"{name}: nie podaje liczby testów w ogóle"
            stated = int(floor.group(1))
            assert stated <= actual, f"{name}: obiecuje {stated}, jest {actual}"
            assert actual - stated < 400, (
                f"{name}: próg {stated} przy {actual} testach przestał cokolwiek "
                "znaczyć — podnieś go"
            )

    def test_the_corpus_sizes_match_what_is_on_disk(self):
        synthetic = len(list((ROOT / "tests" / "corpus_public").glob("*.json")))
        gutenberg = len(
            list((ROOT / "tests" / "corpus_gutenberg" / "expected").glob("*.json"))
        )
        assert (synthetic, gutenberg) == (13, 6), (synthetic, gutenberg)
        assert "trzynaście" in POLISH and "sześć" in POLISH
        assert "thirteen" in ENGLISH and "six" in ENGLISH

    def test_the_version_is_the_package_version(self):
        from epubforge import __version__

        for name, text in BOTH.items():
            assert __version__ in text, f"{name}: nie nazywa {__version__}"


class TestEverySwitchTheReadmeAdvertisesExists:
    """Flaga wymieniona w README i nieistniejąca w programie to instrukcja,
    która nie działa — a to gorsze niż jej brak."""

    @pytest.mark.parametrize(
        "flag",
        [
            "--remove-shop-notices",
            "--relative-units",
            "--remove-dead",
            "--strict",
            "--report-language",
            "--compat",
            "--output",
        ],
    )
    def test_the_flag_is_real(self, flag):
        cli = (ROOT / "epubforge" / "cli.py").read_text(encoding="utf-8")
        assert f'"{flag}"' in cli, f"README obiecuje {flag}, a CLI go nie ma"
        for name, text in BOTH.items():
            assert flag in text, f"{name}: nie wymienia {flag}"

    def test_the_engine_variable_is_spelled_the_way_the_code_spells_it(self):
        render = (ROOT / "epubforge" / "render.py").read_text(encoding="utf-8")
        assert 'ENV_BROWSER = "EPUBFORGE_CHROME"' in render
        for text in BOTH.values():
            assert "EPUBFORGE_CHROME" in text

    def test_the_commands_the_readme_shows_are_real_subcommands(self):
        cli = (ROOT / "epubforge" / "cli.py").read_text(encoding="utf-8")
        for command in ("build", "inspect", "compat"):
            assert f'"{command}"' in cli, command


class TestTheTwoReadmesSayTheSameThings:
    """Dwa pliki, jeden program. Rozjechane README to dwie różne obietnice
    złożone dwóm różnym ludziom."""

    def test_they_have_the_same_number_of_sections(self):
        assert len(re.findall(r"^## ", POLISH, re.M)) == len(
            re.findall(r"^## ", ENGLISH, re.M)
        )

    def test_neither_still_claims_watermarks_are_never_removed(self):
        """Zdanie, które WP-17 uczynił nieprawdziwym. Pilnowane wprost, bo było
        prawdziwe przez większość życia tego programu i wróci samo, jeśli ktoś
        będzie pisał z pamięci."""
        assert "**nie są usuwane**" not in POLISH
        assert "are **not removed**" not in ENGLISH

    def test_neither_still_names_the_struck_beta_condition(self):
        """D-011 skreśliło warunek „ktoś spoza autora"."""
        assert "ktoś\nspoza autora" not in POLISH and "spoza autora" not in POLISH
        assert "other than the author" not in ENGLISH


class TestItStillSaysWhatTheProgramWillNotDo:
    """Najważniejsza sekcja dla kogoś, kto trafia tu pierwszy raz, i najłatwiej
    ją zgubić przy przepisywaniu."""

    @pytest.mark.parametrize("promise", ["DRM", "PDF", "MOBI"])
    def test_the_limits_are_still_stated(self, promise):
        for name, text in BOTH.items():
            assert promise in text, f"{name}: nie mówi już o {promise}"

    def test_and_that_nothing_is_removed_without_asking(self):
        assert "do odznaczenia" in POLISH
        assert "optional to untick" in ENGLISH
