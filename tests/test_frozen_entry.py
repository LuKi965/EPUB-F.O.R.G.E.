"""What the installed program opens, checked in the repository.

0.4.0 shipped a new interface and an installer that did not contain it. The
whole suite exercised `epubforge.gui.shell`; `packaging/entry_gui.py` imported
`epubforge.gui.app.run`, PyInstaller followed *that* import, and both the
installer and the portable build opened the old window. Every test passed.

The defect was not in the window. It was that **the packaged entry point took
a different door into the program than everything that tests it** — so this
file holds the door: one dispatcher, imported by the frozen entry, with the
old window reachable only behind its flag.
"""

from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTRY = ROOT / "packaging" / "entry_gui.py"
SPEC = ROOT / "packaging" / "epubforge.spec"


class TestTheFrozenEntryUsesTheDispatcher:
    def test_it_imports_the_package_and_not_a_window(self):
        source = ENTRY.read_text(encoding="utf-8")
        assert "from epubforge.gui import run" in source, (
            "the frozen GUI entry must come through `epubforge.gui.run`; "
            "importing a window module directly is what shipped the old "
            "interface in 0.4.0"
        )
        assert "from epubforge.gui.app import" not in source
        assert "from epubforge.gui.shell import" not in source

    def test_the_cli_does_the_same(self):
        source = (ROOT / "epubforge" / "cli.py").read_text(encoding="utf-8")
        assert "from .gui import run" in source
        assert "from .gui.app import run" not in source

    @pytest.mark.parametrize(
        "name",
        [
            "epubforge.gui.shell",
            "epubforge.gui.shell.window",
            "epubforge.gui.shell.pages",
            "epubforge.gui.shell.pages.tools",
            "epubforge.gui.shell.pages.tools.library",
            "epubforge.gui.shell.pages.tools.diagnostics",
            "epubforge.gui.shell.pages.tools.corpus",
        ],
    )
    def test_the_build_is_told_to_collect_the_new_window(self, name):
        """`gui.run` imports the shell inside a function, and a spec that does
        not name it can leave it out of the build entirely."""
        assert f'"{name}"' in SPEC.read_text(encoding="utf-8")

    def test_and_the_old_one_too_because_the_flag_has_to_work(self):
        assert '"epubforge.gui.app"' in SPEC.read_text(encoding="utf-8")


class TestTheDispatcherChooses:
    def test_the_new_window_by_default(self, monkeypatch):
        from epubforge import gui

        monkeypatch.delenv(gui.LEGACY_FLAG, raising=False)
        assert gui.which() == "shell"

    @pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
    def test_the_old_one_only_when_asked(self, monkeypatch, value):
        from epubforge import gui

        monkeypatch.setenv(gui.LEGACY_FLAG, value)
        assert gui.which() == "legacy"

    def test_an_empty_flag_is_not_a_request(self, monkeypatch):
        from epubforge import gui

        monkeypatch.setenv(gui.LEGACY_FLAG, "")
        assert gui.which() == "shell"


class TestTheBuildCanProveWhichWindowItOpens:
    """The check that would have caught it, and now runs on every build.

    A windowed executable has no console, so `run()` answers in a file when
    `EPUBFORGE_UI_SELFTEST` names one; `packaging/smoke_test.py` reads it and
    refuses a build whose answer is not the new interface.
    """

    def test_the_selftest_names_the_window_it_built(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        from epubforge import gui

        answer = tmp_path / "which.txt"
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        monkeypatch.setenv(gui.SELFTEST_VARIABLE, str(answer))
        monkeypatch.delenv(gui.LEGACY_FLAG, raising=False)
        assert gui.run() == 0
        said = answer.read_text(encoding="utf-8").strip()
        assert said.startswith("shell epubforge.gui.shell.window"), said
        # And every specialist tool was opened: they are built on demand, so a
        # page missing from a frozen build fails at the tile and nowhere before.
        assert "tools=3" in said, said

    def test_and_says_legacy_when_the_flag_is_set(self, tmp_path, monkeypatch):
        pytest.importorskip("PySide6.QtWidgets")
        from epubforge import gui

        answer = tmp_path / "which.txt"
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        monkeypatch.setenv(gui.SELFTEST_VARIABLE, str(answer))
        monkeypatch.setenv(gui.LEGACY_FLAG, "1")
        assert gui.run() == 0
        assert answer.read_text(encoding="utf-8").startswith("legacy epubforge.gui.app")

    def test_the_smoke_test_actually_asks_the_window(self):
        """A presence check ("the file exists and it is windowed") is what let
        this through; the smoke test has to read the answer and judge it."""
        source = (ROOT / "packaging" / "smoke_test.py").read_text(encoding="utf-8")
        assert "EPUBFORGE_UI_SELFTEST" in source
        assert 'said.startswith("shell ' in source
        assert '"tools=3" not in said' in source
