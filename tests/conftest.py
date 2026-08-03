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
