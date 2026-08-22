from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.reader import IDPF_OBFUSCATION
from epubforge.stages.fonts import IDPF_PREFIX_LENGTH, deobfuscate, idpf_key

from .factory import ENCRYPTION_XML, fake_ttf, make_legacy_epub

#: Captured at import, before anything is patched, so the tests that are about
#: drawing can be handed the genuine functions back.
from epubforge import render as _render
from epubforge import render_fidelity as _render_fidelity

_REAL_FIND_RENDERER = _render.find_renderer
_REAL_COMPARE = _render_fidelity.compare
#: `Policy.preset` before WP-12 wraps it. A classmethod, so the underlying
#: function is what gets stored and re-bound.
_REAL_PRESET = Policy.preset.__func__

FIXTURE_IDENTIFIER = "urn:uuid:8f2c1b44-9c1e-4f0a-9c2b-3f6b1a7d5e21"


@pytest.fixture
def legacy_epub(tmp_path):
    """An EPUB 2 carrying an obfuscated font and assorted structural damage."""
    obfuscated = deobfuscate(fake_ttf(), idpf_key(FIXTURE_IDENTIFIER), IDPF_PREFIX_LENGTH)
    return make_legacy_epub(
        str(tmp_path / "source.epub"),
        font=obfuscated,
        encryption=ENCRYPTION_XML.format(algorithm=IDPF_OBFUSCATION),
    )


@pytest.fixture
def rebuilt(legacy_epub, tmp_path):
    result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    assert result.output_path, result.report.to_text()
    return result


@pytest.fixture
def rebuilt_strict(legacy_epub, tmp_path):
    result = rebuild(legacy_epub, str(tmp_path / "strict.epub"), Policy.preset("strict"))
    assert result.output_path, result.report.to_text()
    return result


@pytest.fixture
def archive(rebuilt):
    with zipfile.ZipFile(rebuilt.output_path) as handle:
        yield handle


@pytest.fixture(scope="session", autouse=True)
def no_browser_anywhere():
    """The same emulation, for the whole session rather than per test.

    The function-scoped version below could not reach a fixture built at module
    or session scope — `test_semantic_roundtrip.py` rebuilds its book in a
    `scope="module"` fixture — so those rebuilds ran with the real policy and
    the real browser discovery. On this machine that passed, because Chromium is
    installed here. On the Windows runner, which has none, 48 fixtures came back
    `BLOCKED` and the release build failed.

    That is the host-dependence class BA-2026-004 is about, introduced by me
    while closing it elsewhere: a suite whose answer depends on what the machine
    happens to have installed. The patch is applied once, before anything is
    collected, and the function-scoped fixture below hands the real functions
    *back* to the tests that are about rendering.
    """
    from epubforge import render, render_fidelity

    patch = pytest.MonkeyPatch()
    patch.setattr(render, "find_renderer", lambda: "/nie/ma/mnie")
    # `describe` is the line the window and the console print. Left alone it
    # would report whatever engine this machine has, which is the same
    # host-dependence one line up. `chosen` underneath it is deliberately *not*
    # patched: it is what `test_headless_invocation.py` is about, and a stub
    # over the thing under test is how the last two of these went unnoticed.
    patch.setattr(render, "describe", lambda: "silnik rysujący: podstawiony")
    patch.setattr(
        render_fidelity,
        "compare",
        lambda source, candidate, sample=0, browser=None, renames=None: (
            render_fidelity.RenderFidelity(
                available=True, engine="podstawiona przeglądarka", pages=[]
            )
        ),
    )
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def without_the_renderer(request, monkeypatch):
    """No test draws a page unless it is a test about drawing pages.

    F-028's gate defaults to `stop`, which is the owner's choice and the right
    one for somebody's library — and it means every rebuild renders. Measured
    the moment it became the default: the suite stopped finishing inside ten
    minutes, because two thousand tests that rebuild a book were each paying for
    a browser.

    The same reasoning as `test_corpus_signatures.py` turning EPUBCheck off: a
    suite nobody waits for is a suite nobody runs. What is deliberately *not*
    done here is changing the gate — `Policy().render_gate` is still `stop` and
    `test_render_gate.py` asserts it. Only the discovery of a browser is
    suppressed, which is exactly the state of a machine that has none, and the
    files that are about rendering opt back in.

    **What is emulated changed with DELTA-2026-08-15-001, and for the better.**
    The first version of this suppressed the browser and nothing else, because
    "no browser" then meant "publish with a warning" — so every test in the
    suite ran as a machine that could not check its work, and every report
    carried a warning saying so. That stopped being true when `stop` started
    meaning stop, and the choice of what to emulate instead had to be made
    rather than defaulted into.

    It emulates **a working browser and a book that draws the same** — the
    ordinary case, the one nearly every test is actually about — by answering
    the comparison instead of performing it. No browser is started, the gate
    runs its real code path, and a rebuild that would have been refused for
    losing content still is, because `_judge` is the thing being stood in for
    and not `_render_gate`.

    The files that are about rendering, and the tests marked `renders`, get
    neither substitution and exercise the whole thing for real.
    """
    from epubforge import render, render_fidelity

    if request.node.get_closest_marker("renders") or "render" in str(
        getattr(request.node, "fspath", "")
    ):
        # These are the tests about drawing, so they get the real thing back —
        # and they are the only ones whose answer is allowed to depend on
        # whether this machine has a browser. They skip on their own when it
        # does not.
        monkeypatch.setattr(render, "find_renderer", _REAL_FIND_RENDERER)
        monkeypatch.setattr(render_fidelity, "compare", _REAL_COMPARE)

#: Files whose subject *is* validation. They get the real lookup back, and skip
#: on their own when there is no validator — the same arrangement the render
#: tests have, and for the same reason: a test about a tool is allowed to depend
#: on that tool being present.
#: `commit_gate` is deliberately **not** here. Its subject is the invariant gate
#: in front of the writer, not EPUBCheck — it merely rebuilds in strict mode to
#: get a book, and failing it for want of Java is exactly the confusion this
#: fixture exists to remove.
ABOUT_VALIDATION = ("epubcheck", "publication_gate", "validator")


@pytest.fixture(scope="session", autouse=True)
def no_epubcheck_gate_anywhere():
    """A test may not fail because this machine has no Java.

    WP-12 / EF-030. Measured before the change: with `EPUBCHECK_JAR` pointing at
    nothing and no cached jar, five ordinary test files produced **28 failures
    and 4 errors** — none of them about EPUBCheck. `strict` asks for the `clean`
    gate, the gate answers `BLOCKED: the validator this gate needs is not
    installed`, the rebuild does not publish, and a test that wanted a rebuilt
    book gets none. All correct behaviour, and none of it the test's subject.

    **Why this neutralises rather than emulates, unlike the renderer above.**
    The renderer is stood in for with an *answer* — the two pages draw the same
    — because that is the ordinary case and nearly every test is about
    something else. There is no equivalent ordinary answer here. "EPUBCheck says
    this book is valid" is not a default, it is the verdict the gate exists to
    obtain; asserting it on a machine that never asked would make every
    publication test pass for a reason that has nothing to do with the book. So
    the gate is switched **off** for tests that are not about it, which is
    honest — nobody validated anything — and the files that are about validation
    get the real thing back below.

    Session-scoped for the reason `no_browser_anywhere` is: the first draft of
    this was function-scoped and left eighteen errors behind, all of them in
    module-scoped fixtures that build their book before any function fixture
    runs. That is the same mistake as BA-2026-004 and it took the same shape
    twice, which is why it is worth saying out loud rather than just fixing.

    A test that names the setting explicitly keeps what it named, whatever it
    named: a test writing `validate_before_publish="clean"` is asking for the
    gate on purpose.
    """
    from epubforge.policy import Policy
    from epubforge.validate import find_epubcheck

    if find_epubcheck() is not None:
        yield
        return

    patch = pytest.MonkeyPatch()

    def stood_down(cls, name, **overrides):
        overrides.setdefault("validate_before_publish", "off")
        return _REAL_PRESET(cls, name, **overrides)

    patch.setattr(Policy, "preset", classmethod(stood_down))
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def validation_tests_get_the_real_gate(request, monkeypatch):
    """The other half: a test about the validator asks for the validator.

    Handed back rather than never taken away, because the patch above has to be
    session-scoped to reach module fixtures and a session-scoped patch cannot
    know which test is running.
    """
    from epubforge.policy import Policy

    where = str(getattr(request.node, "fspath", "")).lower()
    if request.node.get_closest_marker("validates") or any(
        name in where for name in ABOUT_VALIDATION
    ):
        monkeypatch.setattr(Policy, "preset", classmethod(_REAL_PRESET))
