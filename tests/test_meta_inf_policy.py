"""F-012 — every reserved container file gets a decision, not a skip.

Measured on 0.2.19: an EPUB carrying `META-INF/signatures.xml` and a
`META-INF/custom.xml` came back with neither, and with no finding of any kind.
One `startswith("META-INF/")` skipped the lot, and skipped is not a decision —
it is the absence of one. A book with rights metadata or an organisation's
signature lost them silently, which is a compliance problem dressed as
tidiness.

**On signatures specifically**, because it is the only entry here where the
right answer is to delete something. A signature is computed over exact bytes;
this program rewrites the package document even in the mode that leaves content
byte for byte, so no signature can survive a rebuild and none can be re-made
without the signer's private key. The three options were: keep it, drop it
loudly, refuse to rebuild a signed book. Keeping it is the one genuinely bad
one — a tool that checks the signature reports not "unsigned" but *the
signature does not match*, which is true and reads as an accusation of
tampering where there was a repair. The owner chose "remove, but say so out
loud" on 2026-08-13, after asking what the thing was.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .factory import make_modern_epub

SIGNATURE = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<signatures xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/></signatures>'
)
RIGHTS = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<rights xmlns="http://example.test/rights">wydawca zachowuje prawa</rights>'
)
EXTRA_METADATA = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<metadata xmlns="http://example.test/m">katalog wydawcy 1998</metadata>'
)


def with_meta_inf(tmp_path, extra: dict[str, bytes]) -> str:
    """An ordinary book, plus whatever is put beside its container document."""
    source = make_modern_epub(str(tmp_path / "plain.epub"), title="T")
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries.update(extra)

    path = tmp_path / "in.epub"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        for name, data in entries.items():
            if name != "mimetype":
                archive.writestr(name, data)
    return str(path)


def rebuilt(tmp_path, extra: dict[str, bytes], preset: str = "preserve"):
    return rebuild(with_meta_inf(tmp_path, extra), str(tmp_path / "out.epub"),
                   Policy.preset(preset))


def entries_of(result) -> list[str]:
    with zipfile.ZipFile(result.output_path) as archive:
        return archive.namelist()


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestWhatIsKept:
    @pytest.mark.parametrize(
        ("name", "data"),
        [("META-INF/rights.xml", RIGHTS), ("META-INF/metadata.xml", EXTRA_METADATA)],
    )
    def test_a_reserved_file_this_rebuild_does_not_change_is_carried(self, tmp_path, name, data):
        result = rebuilt(tmp_path, {name: data})
        assert name in entries_of(result)
        assert "reader.meta-inf-carried" in rules_of(result)

    def test_it_is_carried_byte_for_byte(self, tmp_path):
        result = rebuilt(tmp_path, {"META-INF/rights.xml": RIGHTS})
        with zipfile.ZipFile(result.output_path) as archive:
            assert archive.read("META-INF/rights.xml") == RIGHTS

    def test_a_file_nobody_here_recognises_is_carried_rather_than_judged(self, tmp_path):
        """The one thing worse than keeping it is deciding on its behalf that it
        did not matter."""
        result = rebuilt(tmp_path, {"META-INF/com.example.custom.xml": b"<x/>"})
        assert "META-INF/com.example.custom.xml" in entries_of(result)
        assert "reader.meta-inf-unknown-carried" in rules_of(result)

    @pytest.mark.parametrize("preset", ["preserve", "strict", "minimal"])
    def test_every_mode_carries_it(self, tmp_path, preset):
        result = rebuilt(tmp_path, {"META-INF/rights.xml": RIGHTS}, preset)
        assert "META-INF/rights.xml" in entries_of(result)


class TestWhatIsRemovedAndSaidOutLoud:
    def test_a_signature_does_not_survive_the_rebuild(self, tmp_path):
        result = rebuilt(tmp_path, {"META-INF/signatures.xml": SIGNATURE})
        assert "META-INF/signatures.xml" not in entries_of(result)

    def test_and_the_report_says_it_went(self, tmp_path):
        """The whole of the owner's decision is in this assertion. Removing it
        quietly and removing it loudly produce the same archive and are not the
        same act."""
        result = rebuilt(tmp_path, {"META-INF/signatures.xml": SIGNATURE})
        finding = next(
            f for f in result.report.findings if f.rule == "reader.meta-inf-invalidated"
        )
        assert finding.location == "META-INF/signatures.xml"

    def test_a_container_inventory_goes_the_same_way(self, tmp_path):
        """Ours would be wrong the moment anything is renamed, and a stale
        inventory is worse than none."""
        result = rebuilt(tmp_path, {"META-INF/manifest.xml": b"<manifest/>"})
        assert "META-INF/manifest.xml" not in entries_of(result)
        assert "reader.meta-inf-invalidated" in rules_of(result)


class TestTheOnesThisProgramWritesItself:
    def test_the_container_document_is_rebuilt_not_carried(self, tmp_path):
        """`container.xml` names the package document, and the rebuild decides
        where that goes. Carrying the source's would point at the old place."""
        result = rebuilt(tmp_path, {})
        with zipfile.ZipFile(result.output_path) as archive:
            container = archive.read("META-INF/container.xml").decode()
        assert "full-path" in container
        assert "reader.meta-inf-carried" not in rules_of(result)

    def test_an_ordinary_book_gains_no_findings_from_any_of_this(self, tmp_path):
        result = rebuilt(tmp_path, {})
        assert not {r for r in rules_of(result) if r.startswith("reader.meta-inf")}
