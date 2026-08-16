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
    patch.setattr(
        render_fidelity,
        "compare",
        lambda source, candidate, sample=0, browser=None: render_fidelity.RenderFidelity(
            available=True, engine="podstawiona przeglądarka", pages=[]
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
