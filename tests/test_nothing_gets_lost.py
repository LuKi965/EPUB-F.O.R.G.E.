"""Nadrzędny warunek WP-20, sprawdzany maszynowo zamiast obiecywany.

Właściciel postawił go dosłownie: *„nadrzędny warunek to brak strat
funkcjonalnych, a w przypadku GUI również. Możliwe jest jedynie jego
uporządkowanie, poprawienie i ewentualny upgrade wizualny."*

Sprzątanie, którego nic nie pilnuje, jest jednorazowe — a sprzątanie, które gubi
przełącznik, jest gorsze niż jego brak, bo strata jest cicha. Więc zamiast
zapewnienia, że nic nie zginęło, jest tu test, który to sprawdza przy każdym
uruchomieniu suity:

* każde pole `Policy` jest osiągalne dla człowieka — z okna albo z wiersza
  poleceń — poza trzema wymienionymi niżej z powodem;
* każdy przełącznik, który okno pokazuje, faktycznie trafia do `Policy`;
* każda reguła, na którą kod się powołuje, ma wpis w katalogu komunikatów
  w **obu** językach.

Trzeci punkt jest tu dlatego, że skracanie prozy i katalogów to ta sama robota,
a reguła bez tłumaczenia nie psuje się głośno — po cichu spada na angielski.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

from epubforge.policy import Policy

ROOT = pathlib.Path(__file__).parent.parent

#: Pola, których człowiek nie ustawia i ustawiać nie powinien. Wymienione
#: z powodem, bo lista wyjątków bez powodów rośnie sama.
NOT_FOR_PEOPLE = {
    #: Wybierany presetem (`--strict`, `--minimal`), nie ustawiany wprost.
    "strict",
    #: Układ wewnątrz kontenera. Parametry dla wywołań bibliotecznych; mają
    #: sensowne domyślne i własną walidację ścieżek, a okno, które pozwala je
    #: zmienić, pozwala zbudować książkę, której nie otworzy żaden czytnik.
    "content_dir",
    "package_name",
}


def source(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class TestEveryPolicySwitchIsReachable:
    def test_no_setting_is_hidden_from_both_interfaces(self):
        gui = source("epubforge", "gui", "app.py")
        cli = source("epubforge", "cli.py")
        hidden = [
            f.name for f in dataclasses.fields(Policy)
            if f.name not in NOT_FOR_PEOPLE
            and f"policy.{f.name}" not in gui
            and f"policy.{f.name}" not in cli
        ]
        assert not hidden, f"ustawienia, których nie da się zmienić: {hidden}"

    def test_the_exception_list_does_not_name_things_that_left(self):
        """Wyjątek na pole, którego już nie ma, to wyjątek, który przestał
        cokolwiek chronić i zaczął ukrywać następne."""
        names = {f.name for f in dataclasses.fields(Policy)}
        stale = NOT_FOR_PEOPLE - names
        assert not stale, f"wyjątki na nieistniejące pola: {sorted(stale)}"


class TestTheWindowAndThePolicyAgree:
    def test_every_checkbox_the_window_builds_reaches_the_policy(self):
        """Pole wyboru, które niczego nie ustawia, jest gorsze niż jego brak:
        człowiek je odznacza i wierzy, że coś się stało."""
        gui = source("epubforge", "gui", "app.py")
        built = set(re.findall(r"self\.(\w+_check)\s*=\s*self\._checkbox", gui))
        used = set(re.findall(r"self\.(\w+_check)\.isChecked\(\)", gui))
        idle = sorted(built - used)
        assert not idle, f"pola wyboru, które nic nie ustawiają: {idle}"

    def test_and_nothing_reads_a_checkbox_that_is_never_built(self):
        gui = source("epubforge", "gui", "app.py")
        built = set(re.findall(r"self\.(\w+_check)\s*=\s*self\._checkbox", gui))
        used = set(re.findall(r"self\.(\w+_check)\.isChecked\(\)", gui))
        assert not sorted(used - built), sorted(used - built)


class TestEveryRuleTheCodeRaisesCanBeRead:
    """Reguła bez wpisu w katalogu nie psuje się głośno — raport wypisuje jej
    identyfikator zamiast zdania, a po polsku po cichu spada na angielski."""

    def raised(self) -> set[str]:
        found: set[str] = set()
        for path in (ROOT / "epubforge").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            found |= set(re.findall(r'"((?:[a-z0-9]+\.)[a-z0-9-]+)"', text))
        return found

    def test_every_raised_rule_has_english_and_polish(self):
        from epubforge import rules

        raised = self.raised() & set(rules.CATALOGUE) | (
            self.raised() & set(rules.CATALOGUE_PL)
        )
        missing_pl = sorted(r for r in raised if r not in rules.CATALOGUE_PL)
        missing_en = sorted(r for r in raised if r not in rules.CATALOGUE)
        assert not missing_pl, f"bez polskiego: {missing_pl}"
        assert not missing_en, f"bez angielskiego: {missing_en}"

    def test_the_two_catalogues_carry_the_same_rules(self):
        from epubforge import rules

        only_en = sorted(set(rules.CATALOGUE) - set(rules.CATALOGUE_PL))
        only_pl = sorted(set(rules.CATALOGUE_PL) - set(rules.CATALOGUE))
        assert not only_en, f"tylko po angielsku: {only_en}"
        assert not only_pl, f"tylko po polsku: {only_pl}"
