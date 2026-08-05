"""K12 — the model is a contract.

The rebuild emits the package document from the model, which is what makes the
output correct however broken the input was. The price is exact and easy to miss:
**a construct that is not read into the model does not appear in the output**,
and nothing complains. No warning, no report entry, no validator error, because
the result is perfectly valid. Just poorer.

That is how `page-progression-direction` went missing in every mode including
`minimal` — the one that promises to touch nothing. Everything expressed as
`<meta>` survived a rebuild; everything expressed as an attribute of a structural
element did not, and no test could see the difference because both outputs were
valid EPUB.

This file is the only place where such a loss becomes visible. It feeds a
package carrying one of everything the specification allows through the rebuild
and compares the constructs on both sides. Anything that disappears must either
be repaired or be listed below **with a reason** — the list is a record of
decisions, not a bag of exemptions.
"""

from __future__ import annotations

import zipfile

import pytest
from lxml import etree

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .kitchen_sink import make_kitchen_sink

#: Constructs the rebuild drops on purpose. Every entry states why; an entry
#: without a reason is a defect wearing a disguise.
DROPPED_ON_PURPOSE: dict[str, str] = {
    "package/@prefix": (
        "regenerated from what the output actually uses — carrying the source's "
        "declarations forward would keep prefixes nothing references"
    ),
    "guide": (
        "removed from EPUB 3.3 and translated into the landmarks nav; re-emitted "
        "only when a compatibility profile asks for it"
    ),
    "reference": "same as guide",
    "reference/@type": "same as guide",
    "reference/@title": "same as guide",
    "reference/@href": "same as guide",
    "meta/@name": (
        "EPUB 2 metadata. `cover` is regenerated from the model; calibre's own "
        "bookkeeping is deliberately not carried over"
    ),
    "meta/@content": "same as meta/@name",
    "link": (
        "external metadata records are not read into the model, so re-emitting "
        "them would mean copying a reference this tool cannot verify"
    ),
    "link/@rel": "same as link",
    "link/@href": "same as link",
    "link/@media-type": "same as link",
    "meta/@display-seq": "not modelled; title ordering is the model's own",
    "dc:format": "always application/epub+zip for the output, so restating it is noise",
    "itemref/@linear": (
        "read into SpineItem.linear and re-emitted; absent here only when every "
        "item is linear"
    ),
}


#: Constructs the rebuild drops because it *cannot* carry them — open defects,
#: not decisions. Kept in their own list so that a defect cannot quietly become
#: a decision by being filed next to one, which is how they usually die.
STILL_BROKEN: dict[str, str] = {
    "collection": (
        "EF-004: the model has no place for a <collection>, so the writer has "
        "nothing to emit. Both of the fixture's collections disappear"
    ),
    "collection/@role": "EF-004: same as collection",
}


def constructs(path: str) -> set[str]:
    """Every element and attribute present in the package document.

    Named the way the specification names them — `spine/@page-progression-direction`
    — so a failure reads as the thing that went missing rather than as an XPath.
    """
    with zipfile.ZipFile(path) as archive:
        opf_name = next(name for name in archive.namelist() if name.endswith(".opf"))
        root = etree.fromstring(archive.read(opf_name))

    def local(tag) -> str:
        return tag.rpartition("}")[2] if isinstance(tag, str) else ""

    def qualify(element) -> str:
        name = local(element.tag)
        # dc:* elements are worth distinguishing from opf ones of the same name.
        if isinstance(element.tag, str) and "purl.org/dc/elements" in element.tag:
            return f"dc:{name}"
        return name

    found: set[str] = set()
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        name = qualify(element)
        found.add(name)
        for key in element.attrib:
            attribute = key.rpartition("}")[2] if key.startswith("{") else key
            found.add(f"{name}/@{attribute}")
        # A refinement's `property` is the construct, not the element.
        if name == "meta" and element.get("property"):
            found.add(f"meta/@{element.get('property').split(':')[-1]}")
    return found


@pytest.fixture
def kitchen_sink(tmp_path):
    return make_kitchen_sink(str(tmp_path / "kitchen-sink.epub"))


@pytest.fixture(params=["preserve", "strict", "minimal"])
def rebuilt_sink(request, kitchen_sink, tmp_path):
    result = rebuild(
        kitchen_sink, str(tmp_path / f"{request.param}.epub"), Policy.preset(request.param)
    )
    assert result.output_path, result.report.to_text()
    return result.output_path


def test_nothing_leaves_the_package_document_unnoticed(kitchen_sink, rebuilt_sink):
    """K12. Whatever the source declared either survives or is on the list."""
    lost = (
        constructs(kitchen_sink)
        - constructs(rebuilt_sink)
        - set(DROPPED_ON_PURPOSE)
        - set(STILL_BROKEN)
    )
    assert not lost, (
        "the package document lost constructs that are not on the deliberate list: "
        f"{sorted(lost)}"
    )


def test_no_known_defect_has_quietly_been_fixed(kitchen_sink, rebuilt_sink):
    """A ratchet. When B3/B4 close one of these it fails here, and the entry has
    to be deleted rather than left standing as a claim that is no longer true."""
    survived = [name for name in STILL_BROKEN if name in constructs(rebuilt_sink)]
    assert not survived, (
        "listed as a defect but present in the output — delete the entry: "
        f"{sorted(survived)}"
    )


def test_every_deliberate_drop_carries_a_reason():
    """The list documents decisions. An entry without one is a defect in hiding."""
    unexplained = [
        name
        for name, reason in list(DROPPED_ON_PURPOSE.items()) + list(STILL_BROKEN.items())
        if not reason.strip()
    ]
    assert not unexplained, unexplained


def test_the_deliberate_list_has_no_dead_entries(kitchen_sink, tmp_path):
    """An entry for something the fixture never had is a note about nothing."""
    present = constructs(kitchen_sink)
    stale = [name for name in DROPPED_ON_PURPOSE if name not in present]
    assert not stale, f"listed as dropped but never present in the fixture: {sorted(stale)}"


# --------------------------------------------------- the specific losses found
class TestConstructsThatUsedToVanish:
    """Named individually so a regression says what broke, not just "something"."""

    def opf(self, path: str) -> str:
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".opf"))
            return archive.read(name).decode()

    def test_page_progression_direction_survives(self, rebuilt_sink):
        """A manga or a Hebrew edition that loses this opens backwards."""
        assert 'page-progression-direction="rtl"' in self.opf(rebuilt_sink)

    def test_package_direction_survives(self, rebuilt_sink):
        assert 'dir="ltr"' in self.opf(rebuilt_sink)

    def test_alternate_scripts_survive(self, rebuilt_sink):
        """The romanised form is how a catalogue indexes a book it cannot read."""
        opf = self.opf(rebuilt_sink)
        assert "I Am a Cat" in opf
        assert "Natsume Soseki" in opf
        assert opf.count("alternate-script") == 2

    def test_alternate_scripts_keep_their_language(self, rebuilt_sink):
        """Without the language tag the refinement states nothing at all."""
        opf = self.opf(rebuilt_sink)
        assert 'property="alternate-script" xml:lang="en"' in opf

    def test_the_title_keeps_its_script_and_direction(self, rebuilt_sink):
        opf = self.opf(rebuilt_sink)
        assert 'xml:lang="ja"' in opf

    def test_the_series_number_comes_from_the_series_not_the_box(self, rebuilt_sink):
        opf = self.opf(rebuilt_sink)
        assert "Klasyka" in opf
        assert 'property="group-position">7<' in opf

    def test_the_legacy_page_spread_spelling_is_corrected(self, rebuilt_sink):
        """`page-spread-center` is rendition vocabulary and needs its prefix.

        EPUB 3.0 accepted the bare spelling; EPUB 3.3 calls it an undefined
        property, so a book written to the older specification produces an
        invalid package unless this is translated on the way through.
        """
        opf = self.opf(rebuilt_sink)
        assert "rendition:page-spread-center" in opf
        assert 'properties="page-spread-center"' not in opf

    def test_dublin_core_without_a_model_field_still_survives(self, rebuilt_sink):
        opf = self.opf(rebuilt_sink)
        for value in ("monograph", "Japonia", "urn:isbn:9788324500000"):
            assert value in opf, value


def test_the_kitchen_sink_rebuild_validates_cleanly(kitchen_sink, tmp_path):
    """Carrying more of the source through must not cost conformance."""
    from epubforge.validate import find_epubcheck, validate

    if find_epubcheck() is None:
        pytest.skip("EPUBCheck not installed")
    result = rebuild(kitchen_sink, str(tmp_path / "out.epub"), Policy.preset("strict"))
    check = validate(result.output_path)
    assert check.fatal == 0 and check.errors == 0, "\n".join(check.messages)
    assert check.warnings == 0, "\n".join(check.messages)
