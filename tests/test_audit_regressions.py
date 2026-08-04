"""Regressions for defects that survived a full test suite by changing nothing visible.

Both were found by an external audit rather than by the suite, and both share a
shape worth naming: they corrupted *data* while leaving the *shape* of the
output alone — same files, same counts, same validator verdict. The invariant
tests in `test_invariants.py` are the general defence; these pin the specific
behaviours so a future refactor cannot quietly reintroduce them.
"""

from __future__ import annotations

import re
import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from .factory import make_modern_epub

OPF = "EPUB/package.opf"


def package_document(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(OPF).decode()


# ------------------------------------------------------- series numbering
class TestSeriesNumberSurvivesARoundTrip:
    """`group-position` is only ever a refinement, so skipping all refinements
    lost it — but only on the second pass, when the source of the number had
    already moved from `calibre:series_index` to the EPUB 3 spelling."""

    def index_of(self, opf: str) -> str | None:
        match = re.search(r'property="group-position">([^<]*)<', opf)
        return match.group(1) if match else None

    def test_first_pass_writes_the_series_number(self, rebuilt):
        assert self.index_of(package_document(rebuilt.output_path)) == "2"

    def test_second_pass_keeps_it(self, rebuilt, tmp_path):
        again = rebuild(
            rebuilt.output_path, str(tmp_path / "again.epub"), Policy.preset("preserve")
        )
        assert self.index_of(package_document(again.output_path)) == "2"

    def test_series_name_also_survives(self, rebuilt, tmp_path):
        again = rebuild(
            rebuilt.output_path, str(tmp_path / "again.epub"), Policy.preset("preserve")
        )
        assert "Kroniki" in package_document(again.output_path)

    @pytest.mark.parametrize(
        "collection_type, carried",
        [("series", True), ("set", False)],
    )
    def test_only_a_series_collection_becomes_a_series(
        self, tmp_path, collection_type, carried
    ):
        """A "set" is a boxed edition, not a series, and does not belong in one."""
        source = make_modern_epub(
            str(tmp_path / "collection.epub"),
            extra_metadata=(
                '    <meta property="belongs-to-collection" id="c">Dzieła zebrane</meta>\n'
                f'    <meta refines="#c" property="collection-type">{collection_type}</meta>'
            ),
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert ("Dzieła zebrane" in package_document(result.output_path)) is carried


# ------------------------------------------------------------ empty alt text
class TestEmptyAltIsNeverADescription:
    """An empty alt asserts "decorative", and nothing here can verify that.

    The previous code trusted it whenever the current run had not supplied it
    itself — a fact it kept in memory. Send the output back in and that memory
    was gone, so a book with no descriptions at all came out claiming
    `alternativeText`.
    """

    def features(self, path: str) -> set[str]:
        return set(
            re.findall(r'property="schema:accessibilityFeature">([^<]*)<', package_document(path))
        )

    def test_first_pass_withholds_the_claim(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" not in self.features(result.output_path)

    def test_second_pass_withholds_it_too(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        assert "alternativeText" not in self.features(second.output_path)

    def test_the_summary_does_not_claim_it_either(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "in.epub"))
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        assert "wszystkie ilustracje" not in package_document(second.output_path)

    @pytest.mark.parametrize(
        "image",
        [
            '<img src="picture.png" alt="" role="presentation"/>',
            '<img src="picture.png" alt="" aria-hidden="true"/>',
        ],
    )
    def test_an_explicit_decorative_marking_is_believed(self, tmp_path, image):
        """Because that one *is* a statement somebody deliberately made."""
        source = make_modern_epub(str(tmp_path / "in.epub"), image=image)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" in self.features(result.output_path)

    def test_a_real_description_is_believed(self, tmp_path):
        source = make_modern_epub(
            str(tmp_path / "in.epub"),
            image='<img src="picture.png" alt="Mapa wybrzeża z zaznaczonym portem"/>',
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        assert "alternativeText" in self.features(result.output_path)

    def test_the_gap_is_reported(self, tmp_path):
        from epubforge.report import Level

        source = make_modern_epub(str(tmp_path / "in.epub"))
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        warnings = [f.message for f in result.report.findings if f.level is Level.WARN]
        assert any("alt text" in message for message in warnings), warnings


# ------------------------------------------------------- collection numbering
class TestSeriesNumberComesFromTheRightCollection:
    """A book can belong to several collections; the number is not free-floating.

    The 0.8.0 fix separated a boxed `set` from a `series` by name, but the
    number was still taken from whichever `group-position` the document listed
    first. The seventh Chronicle, published inside a boxed set as part one, came
    out as "Chronicles, volume 1".
    """

    BOX_THEN_SERIES = (
        '    <meta property="belongs-to-collection" id="box">Dzieła zebrane</meta>\n'
        '    <meta refines="#box" property="collection-type">set</meta>\n'
        '    <meta refines="#box" property="group-position">1</meta>\n'
        '    <meta property="belongs-to-collection" id="ser">Kroniki</meta>\n'
        '    <meta refines="#ser" property="collection-type">series</meta>\n'
        '    <meta refines="#ser" property="group-position">7</meta>'
    )

    def read(self, tmp_path, extra_metadata):
        from epubforge.reader import read_epub
        from epubforge.report import Report

        source = make_modern_epub(str(tmp_path / "c.epub"), extra_metadata=extra_metadata)
        return read_epub(source, Report(source=source)).metadata

    def test_name_and_number_come_from_the_same_collection(self, tmp_path):
        metadata = self.read(tmp_path, self.BOX_THEN_SERIES)
        assert (metadata.series, metadata.series_index) == ("Kroniki", "7")

    def test_an_untyped_collection_counts_as_a_series(self, tmp_path):
        """EPUB 3 says that is the default, and most books never state it."""
        metadata = self.read(
            tmp_path,
            '    <meta property="belongs-to-collection" id="s">Kroniki</meta>\n'
            '    <meta refines="#s" property="group-position">3</meta>',
        )
        assert (metadata.series, metadata.series_index) == ("Kroniki", "3")

    def test_a_set_alone_yields_no_series_at_all(self, tmp_path):
        metadata = self.read(
            tmp_path,
            '    <meta property="belongs-to-collection" id="b">Pudełko</meta>\n'
            '    <meta refines="#b" property="collection-type">set</meta>\n'
            '    <meta refines="#b" property="group-position">2</meta>',
        )
        assert metadata.series is None and metadata.series_index is None

    def test_it_survives_a_round_trip(self, tmp_path):
        source = make_modern_epub(str(tmp_path / "c.epub"), extra_metadata=self.BOX_THEN_SERIES)
        first = rebuild(source, str(tmp_path / "one.epub"), Policy.preset("preserve"))
        second = rebuild(first.output_path, str(tmp_path / "two.epub"), Policy.preset("preserve"))
        opf = package_document(second.output_path)
        assert "Kroniki" in opf
        assert re.search(r'property="group-position">7<', opf), opf
