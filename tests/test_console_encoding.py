"""Raport po polsku nie ma prawa zabić programu, który go wypisuje.

Znalezione przez smoke test wydania, na zamrożonym buildzie, przy trzecim
podejściu do wydania 0.2.28 — czyli dokładnie tam, gdzie powinno, i to jest
argument za istnieniem tamtego testu.

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u015b'

`ś` w słowie „na stronie", pozycja 14. Konsola Windows zostawiona na starej
stronie kodowej (cp1252 na polskim systemie) nie potrafi zakodować polskich
znaków, a `rich` podaje swoje wyjście prosto do tego strumienia. Przebudowa
była już skończona, książka zapisana — i cały proces padał na **wypisywaniu
diagnozy**.

To jest przypadek zwyczajny dla tego programu, nie skrajny: właściciel jest
Polakiem, jego raporty są po polsku, a `epubforge.exe` uruchamiany z `cmd.exe`
dostaje cp1252.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from rich.table import Table

from epubforge.cli import readable_output

#: Zdanie z prawdziwego raportu, które wywróciło wydanie. Zawiera `ś`, `ż` i `ó`
#: — czyli dokładnie te znaki, których cp1252 nie ma.
POLISH = "na stronie jest mniej niż w źródle — 0000-chapter.xhtml"


def legacy_console_stream() -> io.TextIOWrapper:
    """Strumień taki, jaki daje konsola Windows na starej stronie kodowej."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def print_a_report(stream) -> None:
    console = Console(file=stream, width=80)
    table = Table(show_header=True, box=None)
    table.add_column("finding")
    table.add_row(POLISH)
    console.print(table)


class TestTheDefectItself:
    def test_a_legacy_console_really_cannot_carry_polish(self):
        """Najpierw dowód, że test testuje coś realnego. Bez tego reszta pliku
        mogłaby przechodzić dlatego, że niczego nie odtwarza."""
        with pytest.raises(UnicodeEncodeError):
            print_a_report(legacy_console_stream())


class TestTheFix:
    def test_after_reconfiguring_the_report_prints(self, monkeypatch):
        stream = legacy_console_stream()
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr("sys.stderr", stream)
        readable_output()
        print_a_report(stream)  # nie rzuca

    def test_and_the_polish_actually_arrives(self, monkeypatch):
        """Nie dość, że nie pada — ma jeszcze wypisać to, co miało."""
        stream = legacy_console_stream()
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr("sys.stderr", stream)
        readable_output()
        print_a_report(stream)
        stream.flush()
        written = stream.buffer.getvalue().decode("utf-8", errors="replace")
        assert "źródle" in written and "niż" in written

    def test_a_stream_that_cannot_be_reconfigured_is_not_an_error(self, monkeypatch):
        """Ktoś podmienił stdout na własny obiekt — przekierowanie do pliku,
        przechwycenie w teście, potok. Brak `reconfigure` nie jest powodem, żeby
        program nie wystartował."""
        class Plain:
            def write(self, text): return len(text)
            def flush(self): pass

        monkeypatch.setattr("sys.stdout", Plain())
        monkeypatch.setattr("sys.stderr", Plain())
        readable_output()  # nie rzuca

    def test_errors_are_replaced_rather_than_raised(self, monkeypatch):
        """Druga połowa naprawy i ważniejsza z dwóch.

        UTF-8 daje znakom reprezentację. `errors="replace"` sprawia, że konsola,
        która **nadal** czegoś nie narysuje, pokazuje znak zastępczy zamiast
        kończyć proces. Raport jest diagnozą, a diagnoza, która potrafi zabić
        program, który diagnozuje, jest gorsza niż jej brak.
        """
        stream = legacy_console_stream()
        monkeypatch.setattr("sys.stdout", stream)
        monkeypatch.setattr("sys.stderr", stream)
        readable_output()
        assert stream.encoding.lower().replace("-", "") == "utf8"
        assert stream.errors == "replace"


class TestItRunsBeforeAnythingPrints:
    def test_main_calls_it_first(self):
        """Kolejność jest całą naprawą: `Console` powstaje dziesięć razy
        w tym module, więc poprawianie ich po kolei byłoby regułą, o której
        trzeba pamiętać przy jedenastym. Strumień jest naprawiany raz, na
        wejściu, zanim cokolwiek go dotknie."""
        import inspect

        from epubforge import cli

        source = inspect.getsource(cli.main)
        body = [line.strip() for line in source.splitlines() if line.strip()]
        first = next(line for line in body if not line.startswith(("def ", '"""')))
        assert first == "readable_output()", body[:4]
