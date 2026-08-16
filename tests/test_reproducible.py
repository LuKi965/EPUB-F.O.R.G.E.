"""F-022 — the same book in, the same bytes out.

The audit filed this as "the output is not reproducible" and the reproduction
attempt came back **N**: the mechanism was already here. Every ZIP entry carries
a fixed timestamp and `modified_override` pins the one metadata field that moves,
so a caller who knew both of those could already get identical output.

That is not the same as the finding being wrong. A mechanism nobody can ask for
is a thing the author knows, not a feature of the program: there was no switch,
no flag, no box, and nothing that said which fields move. So F-022 is closed by
turning the mechanism into a **mode**, and by dealing with the second moving
part that `modified_override` never touched.

Two things move between runs:

* `dcterms:modified`, which is stamped from the clock;
* the identifier minted for a book that has none, which was `uuid4` — a
  different book every run, and not cosmetically: font obfuscation is keyed on
  the publication identifier.

Under `reproducible` the first comes from the source and the second is derived
from the content. What this file asserts is the property itself — build twice,
compare bytes — rather than the two mechanisms, because the property is the
promise and the mechanisms are how it is kept today.
"""

from __future__ import annotations

import hashlib
import zipfile


from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from tests.factory import MODERN_NAV, MODERN_OPF, png_bytes, write_zip

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title></head>
  <body><h1>Rozdzia&#x142;</h1><p>Tekst.</p></body>
</html>
"""


def book(path, *, identifier: bool = True, modified: bool = True) -> str:
    package = MODERN_OPF.format(title="Test", extra_metadata="")
    if not identifier:
        package = package.replace(
            '<dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>',
            "",
        ).replace('unique-identifier="pub-id"', "")
    if not modified:
        package = package.replace(
            '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>', ""
        )
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "OEBPS/package.opf": package.encode(),
            "OEBPS/nav.xhtml": MODERN_NAV.encode(),
            "OEBPS/chapter.xhtml": PAGE.encode(),
            "OEBPS/picture.png": png_bytes(),
        },
    )


def digest(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def twice(source: str, tmp_path, **policy) -> tuple[str, str]:
    settings = Policy.preset("preserve")
    for key, value in policy.items():
        setattr(settings, key, value)
    first = str(tmp_path / "first.epub")
    second = str(tmp_path / "second.epub")
    for destination in (first, second):
        result = rebuild(source, destination, settings)
        assert result.output_path, result.report.to_text()
    return first, second


def package_of(path: str) -> str:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".opf"))
        return archive.read(name).decode("utf-8")


class TestF022TheModeThatWasMissing:
    def test_two_builds_of_one_book_are_the_same_file(self, tmp_path):
        first, second = twice(book(tmp_path / "in.epub"), tmp_path, reproducible=True)
        assert digest(first) == digest(second)

    def test_without_it_they_are_not(self, tmp_path):
        """The guard on the guard. If two builds matched anyway — a coarse
        clock, a cached result — every assertion above would be vacuous.

        `modified_override` is what the ordinary path leaves free, so it is set
        to two different values here to stand in for two runs a second apart.
        """
        source = book(tmp_path / "in2.epub")
        one = str(tmp_path / "a.epub")
        two = str(tmp_path / "b.epub")
        rebuild(source, one, Policy.preset("preserve", modified_override="2026-01-01T00:00:00Z"))
        rebuild(source, two, Policy.preset("preserve", modified_override="2026-01-01T00:00:01Z"))
        assert digest(one) != digest(two)

    def test_the_modification_date_comes_from_the_source(self, tmp_path):
        first, _ = twice(book(tmp_path / "date.epub"), tmp_path, reproducible=True)
        assert "2020-01-01T00:00:00Z" in package_of(first)

    def test_a_book_with_no_date_at_all_gets_one_that_is_obviously_not_real(self, tmp_path):
        """The alternative was a plausible-looking date, which would be this
        program inventing a fact about somebody's book to keep a promise about
        bytes. The epoch is the reproducible-builds convention and nobody will
        mistake it for a publication date."""
        source = book(tmp_path / "nodate.epub", modified=False)
        first, second = twice(source, tmp_path, reproducible=True)
        assert "1970-01-01T00:00:00Z" in package_of(first)
        assert digest(first) == digest(second)

    def test_and_says_so_in_the_report(self, tmp_path):
        source = book(tmp_path / "nodate2.epub", modified=False)
        result = rebuild(
            source, str(tmp_path / "out.epub"), Policy.preset("preserve", reproducible=True)
        )
        assert "metadata.modified-pinned-to-epoch" in {
            f.rule for f in result.report.findings if f.rule
        }

    def test_an_explicit_timestamp_still_wins(self, tmp_path):
        """`--modified` is a statement by the person running the build. The mode
        is a default, not an override of what they asked for."""
        result = rebuild(
            book(tmp_path / "both.epub"),
            str(tmp_path / "both-out.epub"),
            Policy.preset("preserve", reproducible=True, modified_override="2031-05-05T05:05:05Z"),
        )
        assert "2031-05-05T05:05:05Z" in package_of(result.output_path)


class TestF022TheIdentifierThatWasNotFixed:
    """The half `modified_override` never covered.

    A book with no `dc:identifier` had one minted with `uuid4`. Two rebuilds
    produced two different publications — and because IDPF font obfuscation is
    keyed on the publication identifier, "different publication" is not a
    cosmetic difference for a book with obfuscated fonts in it.
    """

    def test_a_book_without_one_still_rebuilds_to_the_same_bytes(self, tmp_path):
        source = book(tmp_path / "noid.epub", identifier=False)
        first, second = twice(source, tmp_path, reproducible=True)
        assert digest(first) == digest(second)

    def test_the_identifier_is_derived_rather_than_random(self, tmp_path):
        source = book(tmp_path / "noid2.epub", identifier=False)
        first, second = twice(source, tmp_path, reproducible=True)
        assert package_of(first) == package_of(second)
        assert "urn:uuid:" in package_of(first)

    def test_two_different_books_do_not_get_the_same_one(self, tmp_path):
        """Derived from the content, so it has to *be* derived from the content
        — a constant would reproduce beautifully and make every book the same
        publication."""
        one = rebuild(
            book(tmp_path / "x.epub", identifier=False),
            str(tmp_path / "x-out.epub"),
            Policy.preset("preserve", reproducible=True),
        )
        different = write_zip(
            str(tmp_path / "y.epub"),
            {
                "META-INF/container.xml": CONTAINER.encode(),
                "OEBPS/package.opf": MODERN_OPF.format(title="Inna", extra_metadata="")
                .replace(
                    '<dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>',
                    "",
                )
                .replace('unique-identifier="pub-id"', "")
                .encode(),
                "OEBPS/nav.xhtml": MODERN_NAV.encode(),
                "OEBPS/chapter.xhtml": PAGE.replace("Tekst.", "Inny tekst.").encode(),
                "OEBPS/picture.png": png_bytes(color=(9, 9, 9)),
            },
        )
        two = rebuild(
            different,
            str(tmp_path / "y-out.epub"),
            Policy.preset("preserve", reproducible=True),
        )

        def identifier(path):
            text = package_of(path)
            return text.split("urn:uuid:", 1)[1].split("<", 1)[0]

        assert identifier(one.output_path) != identifier(two.output_path)

    def test_the_ordinary_path_still_mints_a_fresh_one(self, tmp_path):
        """Off the mode, a rebuilt book that never had an identifier is a new
        publication each time, which is the correct reading of "this file has no
        identity of its own"."""
        source = book(tmp_path / "fresh.epub", identifier=False)
        one = rebuild(source, str(tmp_path / "f1.epub"), Policy.preset("preserve"))
        two = rebuild(source, str(tmp_path / "f2.epub"), Policy.preset("preserve"))
        assert package_of(one.output_path) != package_of(two.output_path)


class TestF022ItIsReachable:
    """The whole finding, in the end, was that nobody could ask for it."""

    def test_the_command_line_offers_it(self):
        from epubforge.cli import build_parser

        parsed = build_parser().parse_args(["build", "x.epub", "--reproducible"])
        assert parsed.reproducible

    def test_and_it_reaches_the_policy(self):
        import argparse

        from epubforge.cli import build_parser, build_policy

        parsed = build_parser().parse_args(["build", "x.epub", "--reproducible"])
        assert isinstance(parsed, argparse.Namespace)
        assert build_policy(parsed).reproducible

    def test_the_window_offers_it_too(self):
        import pathlib

        from epubforge.gui.strings import EN, PL

        source = (
            pathlib.Path(__file__).resolve().parent.parent / "epubforge" / "gui" / "app.py"
        ).read_text(encoding="utf-8")
        assert "policy.reproducible = self.reproducible_check.isChecked()" in source
        for catalogue in (EN, PL):
            assert catalogue["policy.reproducible"]
            assert len(catalogue["policy.reproducible.tip"]) > 200
