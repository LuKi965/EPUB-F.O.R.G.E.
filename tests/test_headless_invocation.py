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

from epubforge import render, render_fidelity

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

    def test_the_order_is_named_first_then_ours_then_the_machine(
        self, monkeypatch, tmp_path
    ):
        """Asserted on `_candidates`, which is where the order lives, rather
        than on `find_renderer` — `conftest` stubs the latter for the whole
        session so that two thousand rebuilds do not start a browser.

        The order carries two decisions. Somebody who sets the variable has said
        which engine they mean and outranks what we shipped. What we shipped
        outranks whatever is installed, because otherwise the numbers in a report
        would be about somebody else's Edge.
        """
        from epubforge import resources

        mine = tmp_path / "moja-przegladarka"
        carried = tmp_path / "chrome-headless-shell"
        for path in (mine, carried):
            path.write_text("", encoding="utf-8")
            path.chmod(0o755)
        monkeypatch.setenv(render.ENV_BROWSER, str(mine))
        monkeypatch.setattr(resources, "bundled_renderer", lambda: carried)

        order = render._candidates()
        assert order[0] == mine
        assert carried in order
        assert order.index(carried) < len(order), order

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
