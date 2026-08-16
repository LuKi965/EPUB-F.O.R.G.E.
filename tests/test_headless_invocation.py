"""How the browser is invoked, and how the tidying up is done.

These need no browser, so unlike `test_render_fidelity.py` they are **not**
behind `EPUBFORGE_RENDER_TESTS`: they must run everywhere, including the release
build, because both defects they pin were shipped to the owner and neither could
have been caught by a test that only runs when somebody opts in.

Both arrived the same way. 0.2.25 fixed browser discovery on Windows, which
switched on a code path that had never once run there — Edge was never found
before — and his first batch hit both defects in it at once.
"""

from __future__ import annotations

import inspect

from epubforge import render

#: `conftest` stubs `render.describe` for the whole session, so that no test's
#: answer depends on which engine this machine happens to have. The two tests
#: below are *about* that line, so they are handed the real one back — the same
#: arrangement the render tests have, and for the same reason.
_REAL_DESCRIBE = render.describe

class TestWhatTheOwnersOwnRunFound:
    """0.2.25 fixed browser discovery, and that switched on a code path which
    had **never once run on Windows** — because Edge was never found. Two
    defects were waiting in it, and his first batch hit both.

    Neither needs a browser to test: one is a flag, the other is how a temporary
    directory is created.
    """

    def test_the_browser_is_asked_for_headless_in_the_spelling_that_works(self):
        """He saw an Edge window open and show nothing. That is what a browser
        does when it does not recognise the flag — it starts normally. Bare
        `--headless` is the deprecated spelling; recent Chrome and Edge want
        `--headless=new`.

        A blank window appearing on somebody's screen is not cosmetic. It looks
        like something that should not be happening, which is a reasonable thing
        to distrust and a bad thing for a program asking to be trusted with a
        library.
        """
        source = inspect.getsource(render.shoot)
        assert '"--headless=new"' in source
        assert '"--headless",' not in source

    def test_tidying_up_cannot_lose_the_book(self):
        """`OSError: [WinError 145] Katalog nie jest pusty`, raised while
        deleting a temporary directory, arrived in his report as *"the rebuilt
        book could not be written"*. Windows will not remove a directory while
        anything still holds a handle inside it — a browser that has just
        exited, an indexer, a virus scanner — and none of those is a reason for
        somebody to lose their book.
        """
        from epubforge import render_fidelity

        for function in (render.shoot, render_fidelity.compare):
            source = inspect.getsource(function)
            if "TemporaryDirectory" not in source:
                continue
            assert "ignore_cleanup_errors=True" in source, function.__name__


class TestTheRendererWeCarry:
    """0.2.26 bundles `chrome-headless-shell`, on the owner's suggestion.

    His argument was better than the one I had been working to. I had been
    treating "no browser" as a situation to handle — ask, consent, refuse — and
    the situation itself was avoidable: the licence permits redistribution, and
    a headless-only build has no window code compiled into it at all, so it
    cannot do the thing he watched Edge do.

    It also closes a defect I had hit three times without naming properly. The
    appearance check compares two renderings; run against whatever browser a
    machine has, it measures the browser. Edge disagreed with Chromium about
    three of the four damage shapes and reported an empty version string.
    """

    def test_ours_comes_before_anything_on_the_machine(self, monkeypatch, tmp_path):
        from epubforge import resources

        carried = tmp_path / "chrome-headless-shell"
        carried.write_text("", encoding="utf-8")
        carried.chmod(0o755)
        monkeypatch.delenv(render.ENV_BROWSER, raising=False)
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)
        assert render._candidates()[0] == carried

    def test_nothing_bundled_is_not_an_error(self, monkeypatch):
        """Running from a checkout — which is how it runs here, in CI, and for
        anybody who installed it with pip."""
        from epubforge import resources

        monkeypatch.setattr(resources, "bundled_renderer", lambda: None)
        render._candidates()  # an answer either way, and never a raise

    def test_the_bundled_name_is_the_headless_only_build(self):
        """`chrome-headless-shell`, not `chrome`. The distinction is the whole
        point: one of them has no interface compiled into it."""
        import inspect

        from epubforge import resources

        source = inspect.getsource(resources.bundled_renderer)
        assert "chrome-headless-shell" in source


class TestOnlyTheEngineWeCarry:
    """0.2.27 answered the owner's complaint by demoting `EPUBFORGE_CHROME`.
    0.2.28 answers what he actually asked, which was larger and simpler:
    *mamy WBUDOWANE Chromium, na cholerę nam w ogóle „opcjonalny" Edge.*

    He was right and I had half-done it. Demoting the variable left the whole
    apparatus standing — `PATH`, Program Files, Playwright, and an override that
    could put any of them back in front. Every one of those paths existed for a
    single reason, that there was no engine of our own, and that reason ended
    with 0.2.26. What they really bought was an answer that depended on the desk
    the program stood on.
    """

    @staticmethod
    def _two_engines(tmp_path):
        mine = tmp_path / "msedge.exe"
        carried = tmp_path / "chrome-headless-shell"
        for path in (mine, carried):
            path.write_text("", encoding="utf-8")
            path.chmod(0o755)
        return mine, carried

    def test_what_we_carry_is_what_draws(self, monkeypatch, tmp_path):
        from epubforge import resources

        mine, carried = self._two_engines(tmp_path)
        monkeypatch.setenv(render.ENV_BROWSER, str(mine))
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)

        picked = render.chosen()
        assert picked.path == carried
        assert picked.origin == "carried"

    def test_and_there_is_no_way_to_put_anything_in_front_of_it(
        self, monkeypatch, tmp_path
    ):
        """The escape hatch 0.2.27 invented — `EPUBFORGE_CHROME_OVERRIDE` — is
        gone with everything else. It was a way to reintroduce exactly the
        defect the bundle exists to remove, one environment variable at a time.
        """
        assert not hasattr(render, "ENV_BROWSER_WINS")
        from epubforge import resources

        mine, carried = self._two_engines(tmp_path)
        monkeypatch.setenv(render.ENV_BROWSER, str(mine))
        monkeypatch.setenv("EPUBFORGE_CHROME_OVERRIDE", "1")
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)
        assert render.chosen().path == carried

    def test_the_variable_is_the_only_thing_left_and_only_without_a_bundle(
        self, monkeypatch, tmp_path
    ):
        """Kept for one case and no other: a checkout, a `pip` install and this
        project's own render tests carry no engine, and with no way to name one
        the check could never run anywhere but a release."""
        from epubforge import resources

        mine, _ = self._two_engines(tmp_path)
        monkeypatch.setenv(render.ENV_BROWSER, str(mine))
        monkeypatch.setattr(resources, "bundled_renderer", lambda: None)

        picked = render.chosen()
        assert picked.path == mine
        assert picked.origin == "named"

    def test_a_variable_pointing_at_nothing_falls_through_to_ours(
        self, monkeypatch, tmp_path
    ):
        """The commonest state of a stale variable: it names a path that is not
        there any more."""
        from epubforge import resources

        _, carried = self._two_engines(tmp_path)
        monkeypatch.setenv(render.ENV_BROWSER, str(tmp_path / "nie-ma-mnie"))
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)
        assert render.chosen().path == carried

    def test_nothing_hunts_for_a_browser_any_more(self):
        """Named one by one, because each was its own way of asking the machine
        what it happened to have."""
        for name in (
            "windows_installs", "_machine_candidates", "_NAMES",
            "_WINDOWS_PROGRAMS", "_PLAYWRIGHT", "ENV_BROWSER_WINS",
            "_wants_to_win",
        ):
            assert not hasattr(render, name), name

    def test_edge_is_not_mentioned_as_something_to_use(self):
        """It may still be named in the comments — that is where the reasoning
        lives — but not in a string this program shows somebody as an option."""
        assert "Edge" not in render.why_not() or "nie szuka" in render.why_not()

    def test_the_engine_is_named_wherever_a_result_is_shown(self, monkeypatch, tmp_path):
        from epubforge import resources

        _, carried = self._two_engines(tmp_path)
        monkeypatch.delenv(render.ENV_BROWSER, raising=False)
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)
        monkeypatch.setattr(render, "describe", _REAL_DESCRIBE)
        assert "chrome-headless-shell" in render.describe()

    def test_no_engine_is_still_a_sentence(self, monkeypatch):
        from epubforge import resources

        monkeypatch.delenv(render.ENV_BROWSER, raising=False)
        monkeypatch.setattr(resources, "bundled_renderer", lambda: None)
        monkeypatch.setattr(render, "describe", _REAL_DESCRIBE)
        assert render.chosen().path is None
        assert render.describe()

class TestNothingOpensAWindowOnHisScreen:
    """His second complaint about 0.2.26: a black console box flashing roughly
    once a second for as long as a batch ran.

    One per screenshot. A frozen GUI application on Windows has no console of
    its own, so Windows makes one for every child process that does not say no
    — and `render` never said no. `validate` had said no since the day the same
    thing was found there, one window per book, which is exactly why the flags
    now live in one place instead of two.
    """

    def test_the_flags_exist_and_are_windows_only(self, monkeypatch):
        from epubforge import spawn

        monkeypatch.setattr(spawn.os, "name", "posix")
        assert spawn.no_console() == {}

    def test_on_windows_it_asks_for_no_console(self, monkeypatch):
        """Built without a Windows interpreter, so `STARTUPINFO` and the
        `SW_HIDE` constant are stubbed; what is under test is that the code
        takes the branch and puts `creationflags` in, not that Python's own
        constants have the values Microsoft documents."""
        import subprocess

        from epubforge import spawn

        class FakeStartupInfo:
            def __init__(self):
                self.dwFlags = 0
                self.wShowWindow = 0

        monkeypatch.setattr(spawn.os, "name", "nt")
        monkeypatch.setattr(subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
        monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
        monkeypatch.setattr(subprocess, "SW_HIDE", 0, raising=False)

        options = spawn.no_console()
        assert options["creationflags"] == getattr(
            subprocess, "CREATE_NO_WINDOW", 0x08000000
        )
        assert options["startupinfo"].dwFlags & 1

    def test_every_child_process_in_the_package_goes_through_it(self):
        """The invariant, rather than a fix in two files.

        This defect shipped twice — once in the validator, once in the renderer
        — and the second time only because the module that spawns the second
        kind of child was written after the first was fixed and nothing tied
        them together. A grep is what ties them together.
        """
        import pathlib

        package = pathlib.Path(spawn_module().__file__).parent
        offenders = []
        for source in sorted(package.rglob("*.py")):
            if source.name == "spawn.py":
                continue
            text = source.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "subprocess.run(" in stripped or "subprocess.Popen(" in stripped:
                    offenders.append(f"{source.name}:{number}: {stripped}")
        assert not offenders, (
            "these spawn a child process without going through `spawn`, which on "
            "Windows means a console window on somebody's screen: "
            + "; ".join(offenders)
        )


def spawn_module():
    from epubforge import spawn

    return spawn
