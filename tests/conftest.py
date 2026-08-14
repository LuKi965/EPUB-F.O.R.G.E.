from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.reader import IDPF_OBFUSCATION
from epubforge.stages.fonts import IDPF_PREFIX_LENGTH, deobfuscate, idpf_key

from .factory import ENCRYPTION_XML, fake_ttf, make_legacy_epub

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
    done here is changing the default — `Policy().render_gate` is still `stop`
    and `test_render_gate.py` asserts it. Only the discovery of a browser is
    suppressed, which is exactly the state of a machine that has none, and the
    files that are about rendering opt back in.
    """
    if request.node.get_closest_marker("renders"):
        return
    if "render" in str(getattr(request.node, "fspath", "")):
        return
    monkeypatch.setattr("epubforge.render.find_renderer", lambda: None)
