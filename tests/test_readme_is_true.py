"""README ma mówić prawdę o kodzie, a nie o kodzie sprzed trzech wydań.

WP-19. Zarzut właściciela brzmiał: tekst jest przestarzały i przeczy logice
plików README. Przy przepisywaniu wyszły trzy rzeczy **wprost nieprawdziwe**,
nie tylko nieaktualne:

* „Znaki wodne i wpisy wydawcy **nie są usuwane**" — WP-17 dołożył przełącznik,
  który je usuwa. README obiecywał czegoś przeciwnego niż program robi.
* „Do bety brakuje już tylko jednej rzeczy: ktoś spoza autora" — ten warunek
  został skreślony decyzją D-011 i zastąpiony przebiegami. README nadal
  powoływał się na skreślony warunek.
* liczba testów sprzed kilku wydań — od 0.2.28 README nie podaje jej wcale.

Każda z nich to zdanie, które **było prawdziwe, kiedy je pisano**, i żadna nie
psuła niczego głośno. Dlatego jest tu test: dokument, którego nikt nie sprawdza
maszynowo, starzeje się dokładnie w tym tempie, w jakim rośnie program.

**Czego ten plik celowo nie sprawdza:** liczby testów ani rozmiaru korpusu.
Pierwsza wersja sprawdzała jedno i drugie, i było to podwójnie złe — liczba
testów w README nie mówi czytelnikowi nic o programie, a test jej pilnujący
**sam ją zmieniał**, bo dopisanie testów podnosiło licznik. README nie jest
kartą wyników.

Sprawdzane są rzeczy, których fałsz kosztuje czytelnika: flaga, której nie ma,
i zdanie sprzeczne z tym, co program robi. Ton i układ testem nie są i być
nie mogą.
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


class TestADocstringIsNotASecondPlaceToDecidePolicy:
    """EF-037, i luka znaleziona przez drugi audyt.

    Ustalenie było takie: docstring `render_fidelity` mówił „opt-in check",
    a domyślna polityka mówiła `stop`. Zdanie poprawiono i na tym stanęło —
    **bez testu**. Czyli naprawiono jedno wystąpienie choroby i zostawiono
    warunki, w których wraca: zmiana domyślnej wartości w `policy.py` nie
    rusza nic w module obok, a rozjazd znowu zobaczy dopiero czytelnik.

    Ten sam docstring kończy się zdaniem *„a docstring is not a second place to
    decide policy"*. Test jest tym zdaniem powiedzianym maszynie.

    Sprawdzane są dwie rzeczy, obie wyprowadzone z `Policy`, żadna wpisana
    z palca: że domyślna wartość **pada w tekście** i że tekst nie twierdzi
    czegoś przeciwnego do tego, co ta wartość znaczy.
    """

    @staticmethod
    def _docstring() -> str:
        from epubforge import render_fidelity

        return (render_fidelity.__doc__ or "").lower()

    @staticmethod
    def _default() -> str:
        from epubforge.policy import Policy

        return Policy().render_gate

    def test_the_default_is_the_one_the_finding_settled_on(self):
        """Kotwica dla dwóch testów niżej. Gdyby D-016 kiedyś odwrócono,
        mają się posypać razem, a nie cicho zmienić przedmiot."""
        assert self._default() == "stop"

    def test_the_docstring_names_the_default(self):
        assert self._default() in self._docstring(), (
            f"domyślne `render_gate` to {self._default()!r}, a moduł, który tę "
            "bramę tłumaczy, tej wartości nie wymienia"
        )

    def test_and_does_not_call_a_refusing_gate_optional(self):
        """Rdzeń ustalenia. `stop` i `report` to nie są dwa odcienie tego
        samego: pierwszy odmawia zapisu, drugi wypisuje uwagę i zapisuje.
        Nazwanie pierwszego „opt-in" jest fałszem o tym, co zrobi program
        komuś, kto niczego nie ustawiał."""
        tekst = self._docstring()
        if self._default() != "stop":
            pytest.skip("brama nie odmawia domyślnie — to zdanie nie kłamie")
        for zdanie in ("it is an opt-in check", "this check is opt-in"):
            assert zdanie not in tekst, (
                f"docstring mówi {zdanie!r} przy domyślnym {self._default()!r}"
            )
