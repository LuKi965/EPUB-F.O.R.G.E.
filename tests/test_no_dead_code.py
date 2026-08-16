"""Nieużywany import i nieistniejąca nazwa to nie jest kwestia gustu.

WP-20. Sprzątanie, którego nic nie pilnuje, jest jednorazowe — więc zamiast
posprzątać i obiecać, że będzie czysto, jest tu bramka.

Powód, dla którego to nie jest kosmetyka, jest jeden i konkretny: wśród
dwudziestu jeden zgłoszeń, które `pyflakes` miał na pakiecie przed tym plikiem,
siedziało **wywołanie nieistniejącej klasy w oknie**:

    return lines + Diagnostics._render_pages(book)

Klasa nazywa się `DiagnosticsPanel`. Ta linia rzucała `NameError` za każdym
razem, gdy ktoś kliknął rysowanie stron w zakładce diagnostyki — a ponieważ
`from __future__ import annotations` sprawia, że wiele takich rzeczy nigdy się
nie wykonuje, żaden test tego nie dotknął. Narzędzie, które czyta kod zamiast go
uruchamiać, znalazło to w sekundę.

Dwa zgłoszenia były też **dwoma różnymi objaśnieniami pod jednym kluczem**
w katalogu komunikatów — czyli raport mówiący o tej samej regule dwie różne
rzeczy, z których jedna po cichu wygrywała.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def pyflakes(target: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", target],
        capture_output=True, text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


needs_pyflakes = pytest.mark.skipif(
    subprocess.run(
        [sys.executable, "-c", "import pyflakes"], capture_output=True
    ).returncode != 0,
    reason="pyflakes nie jest zainstalowany w tym środowisku",
)


@needs_pyflakes
class TestThePackageHasNoDeadNames:
    def test_no_unused_imports_and_no_undefined_names(self):
        """Zero, nie „mało". Próg powyżej zera zawsze zostaje wypełniony."""
        problems = pyflakes("epubforge")
        assert not problems, "\n".join(problems)

    def test_the_author_tools_too(self):
        problems = pyflakes("tools") + pyflakes("packaging")
        assert not problems, "\n".join(problems)


class TestTheClassTheWindowCallsExists:
    """Regresja dla znaleziska powyżej. Napisana przez sprawdzenie nazw, a nie
    przez uruchomienie okna, bo uruchomienie okna wymaga ekranu."""

    def test_the_diagnostics_panel_calls_itself_by_its_own_name(self):
        import pathlib
        import re

        source = (
            pathlib.Path(__file__).parent.parent / "epubforge" / "gui" / "tabs.py"
        ).read_text(encoding="utf-8")
        classes = set(re.findall(r"^class (\w+)", source, re.M))
        called = set(re.findall(r"\b([A-Z]\w+)\._", source))
        unknown = {name for name in called if name not in classes}
        assert not unknown, f"okno woła nazwy, których nie ma: {sorted(unknown)}"


class TestTheMessageCatalogueSaysOneThingPerRule:
    """Dwa objaśnienia pod jednym kluczem to raport mówiący dwie różne rzeczy
    o tej samej regule, z których jedna po cichu wygrywa."""

    def test_no_rule_is_explained_twice(self):
        import ast
        import pathlib

        for name in ("epubforge/rules.py", "epubforge/gui/strings.py"):
            path = pathlib.Path(__file__).parent.parent / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                keys = [
                    k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                ]
                twice = {k for k in keys if keys.count(k) > 1}
                assert not twice, f"{name}: {sorted(twice)}"
