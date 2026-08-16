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
