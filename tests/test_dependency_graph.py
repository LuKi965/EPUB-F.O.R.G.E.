"""F-016 — what this program thinks a file is used by, before it deletes it.

Two halves, and they are the same mistake pointed in two directions.

**The graph was incomplete.** `srcset`, `<picture><source srcset>` and anything
referenced from inside an SVG were invisible to it, so a picture in daily use
looked like an orphan. That matters because a setting exists whose entire
promise is "delete only what nothing uses", and it was keeping that promise
against a map with holes in it.

**And one deletion never consulted the graph at all.** `_drop_junk` removed by
*name*: `.DS_Store`, `Thumbs.db`, `__MACOSX/`, `._` shadows — and `.bak`, which
is a name a publisher can give a chapter. `chapter.bak`, in the manifest, linked
from the navigation, was deleted on the strength of its extension, with no
switch to turn it off and no proof of anything. A name is a guess about content,
and this program is not allowed those.

What is asserted here is the rule rather than the file list: a file the book
refers to is not deleted, whatever it is called, and a reference this program
cannot follow is not evidence that nothing follows it.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.stages.structure import scan_references
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
  <body>{body}</body>
</html>
"""

DRAWING = """<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 60 90"><image xlink:href="rysunek.png" width="60" height="90"/></svg>
"""


def entries(**extra: bytes) -> dict[str, bytes]:
    base = {
        "META-INF/container.xml": CONTAINER.encode(),
        "OEBPS/nav.xhtml": MODERN_NAV.encode(),
        "OEBPS/picture.png": png_bytes(),
    }
    base.update(extra)
    return base


def package(*items: str, spine: str = "") -> bytes:
    text = MODERN_OPF.format(title="Test", extra_metadata="")
    if items:
        text = text.replace("</manifest>", "".join(items) + "</manifest>")
    if spine:
        text = text.replace("</spine>", spine + "</spine>")
    return text.encode()


def names_in(result) -> set[str]:
    with zipfile.ZipFile(result.output_path) as archive:
        return set(archive.namelist())


def built(source, tmp_path, **policy):
    settings = Policy.preset("preserve")
    for key, value in policy.items():
        setattr(settings, key, value)
    return rebuild(source, str(tmp_path / "out.epub"), settings)


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestTheScanner:
    """Unit-level, because the graph is used by three different decisions and a
    hole in it is easier to see here than three failures away."""

    def test_it_reads_every_candidate_of_a_srcset(self):
        found = scan_references(b'<img src="a.png" srcset="a.png 1x, a@2x.png 2x, a@3x.png 3x">')
        assert set(found) == {"a.png", "a@2x.png", "a@3x.png"}

    def test_a_srcset_with_no_descriptors_still_parses(self):
        assert scan_references(b'<source srcset="one.png, two.png">') == ["one.png", "two.png"]

    def test_a_media_overlay_names_the_document_it_narrates(self):
        """`textref` is the only attribute that says so, and nothing else uses
        it — so without it a narrated chapter has no incoming reference."""
        found = scan_references(b'<seq epub:textref="../text/ch1.xhtml#p1"><audio src="a.mp3"/></seq>')
        assert "../text/ch1.xhtml#p1" in found
        assert "a.mp3" in found

    def test_a_remote_candidate_is_not_a_packaged_file(self):
        assert scan_references(b'<img srcset="https://example.com/a.png 2x">') == []


class TestAFileTheBookActuallyUses:
    @pytest.mark.parametrize(
        "markup",
        [
            '<img src="picture.png" srcset="duzy.png 2x" alt=""/>',
            '<picture><source srcset="duzy.png"/><img src="picture.png" alt=""/></picture>',
        ],
        ids=["srcset", "picture"],
    )
    def test_it_survives_the_orphan_sweep(self, tmp_path, markup):
        source = write_zip(
            str(tmp_path / "srcset.epub"),
            entries(**{
                "OEBPS/package.opf": package(
                    '<item id="big" href="duzy.png" media-type="image/png"/>',
                    '<item id="ch1x" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                ),
                "OEBPS/chapter.xhtml": PAGE.format(body=f"<p>{markup}</p>").encode(),
                "OEBPS/duzy.png": png_bytes(size=(120, 180)),
            }),
        )
        result = built(source, tmp_path, drop_orphans=True)
        assert any(name.endswith("duzy.png") for name in names_in(result)), (
            "a picture the markup offers as an alternative is not an orphan"
        )

    def test_and_so_does_one_used_only_from_inside_an_svg(self, tmp_path):
        """The audit's own example, pointed the other way: an SVG is the one
        image type that can hold a link, and the walk used to skip every image."""
        source = write_zip(
            str(tmp_path / "svg.epub"),
            entries(**{
                "OEBPS/package.opf": package(
                    '<item id="draw" href="rysunek.svg" media-type="image/svg+xml"/>',
                    '<item id="drawn" href="rysunek.png" media-type="image/png"/>',
                    '<item id="ch1x" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                ),
                "OEBPS/chapter.xhtml": PAGE.format(
                    body='<p><img src="rysunek.svg" alt=""/></p>'
                ).encode(),
                "OEBPS/rysunek.svg": DRAWING.encode(),
                "OEBPS/rysunek.png": png_bytes(),
            }),
        )
        result = built(source, tmp_path, drop_orphans=True)
        assert any(name.endswith("rysunek.png") for name in names_in(result))


class TestDeletionByName:
    """`.bak` is the one entry on that list a publisher can mean."""

    @staticmethod
    def book_with_a_bak_chapter(path) -> str:
        return write_zip(
            str(path),
            entries(**{
                "OEBPS/package.opf": package(
                    '<item id="ch1x" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                    '<item id="old" href="rozdzial.bak" media-type="application/xhtml+xml"/>',
                ),
                "OEBPS/chapter.xhtml": PAGE.format(
                    body='<p><a href="rozdzial.bak">dalej</a></p>'
                ).encode(),
                "OEBPS/rozdzial.bak": PAGE.format(body="<p>Dalszy ciąg.</p>").encode(),
            }),
        )

    def test_a_file_the_book_links_to_is_kept_whatever_it_is_called(self, tmp_path):
        result = built(self.book_with_a_bak_chapter(tmp_path / "bak.epub"), tmp_path)
        assert any("rozdzial" in name for name in names_in(result)), (
            "the navigation links to it and the manifest lists it; the extension "
            "is not evidence about the content"
        )
        assert "structure.junk-kept" in rules_of(result)

    def test_the_text_of_that_chapter_is_still_in_the_book(self, tmp_path):
        """K1, which is the reason any of this is argued about."""
        result = built(self.book_with_a_bak_chapter(tmp_path / "bak2.epub"), tmp_path)
        with zipfile.ZipFile(result.output_path) as archive:
            everything = b"".join(archive.read(name) for name in archive.namelist())
        assert "Dalszy ciąg".encode() in everything

    def test_what_nothing_refers_to_is_still_removed(self, tmp_path):
        """The feature is not withdrawn — a `.DS_Store` nobody links to goes."""
        source = write_zip(
            str(tmp_path / "junk.epub"),
            entries(**{
                "OEBPS/package.opf": package(
                    '<item id="ch1x" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                ),
                "OEBPS/chapter.xhtml": PAGE.format(body="<p>Tekst.</p>").encode(),
                "OEBPS/.DS_Store": b"\x00\x01rubbish",
                "OEBPS/kopia.bak": b"old draft nobody links to",
            }),
        )
        result = built(source, tmp_path)
        assert not any(".DS_Store" in name for name in names_in(result))
        assert not any("kopia" in name for name in names_in(result))
        assert "structure.junk-removed" in rules_of(result)

    def test_and_the_person_holding_the_book_can_switch_it_off(self, tmp_path):
        """The owner's standing rule, which has no exception for obvious cases."""
        source = write_zip(
            str(tmp_path / "keep.epub"),
            entries(**{
                "OEBPS/package.opf": package(
                    '<item id="ch1x" href="chapter.xhtml" media-type="application/xhtml+xml"/>',
                ),
                "OEBPS/chapter.xhtml": PAGE.format(body="<p>Tekst.</p>").encode(),
                "OEBPS/.DS_Store": b"\x00\x01rubbish",
            }),
        )
        result = built(source, tmp_path, remove_junk=False)
        # Lowercased: the relayout gives it an ASCII name (`misc.ds_store`),
        # which is a different decision and not the one under test here.
        assert any("ds_store" in name.lower() for name in names_in(result))
        assert "structure.junk-removed" not in rules_of(result)
