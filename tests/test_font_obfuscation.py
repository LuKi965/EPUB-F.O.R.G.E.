"""F-007 — two obfuscated fonts, one key that does not fit.

This one is here because the tool that is supposed to answer "is F-007 done?"
said **no**, and it was right. The fix shipped with the F-010 commit and carried
no test at all: the plan claimed one file, `audyt-status.py` looked for a class
named after the finding and found none, and the entry had been reading "done" on
nothing but my memory of writing it. That is exactly the failure the checkability
clause exists for, so the test comes before anything else today.

**The defect.** Fonts are obfuscated with a key derived from the publication's
unique identifier, and a book can carry two of them where only one decodes —
a font obfuscated under a different identifier, most often because somebody
merged two publications or edited the identifier after the fact. The stage
recovered what it could and then ran `book.encrypted.clear()` on *any* success,
so the entry for the font that had **not** been recovered was wiped too. The
output then held scrambled bytes with `font/ttf` on the label and nothing in the
container saying they were obfuscated: a font that loads, draws nothing, and
whose book insists everything is fine.

Recovery is decided by looking at the result rather than by the call not
raising — XOR always "succeeds", so the only evidence that a key was right is
that a font came out the other end.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.reader import IDPF_OBFUSCATION
from epubforge.stages.fonts import IDPF_PREFIX_LENGTH, deobfuscate, idpf_key, sniff_font_type
from tests.factory import MODERN_OPF, fake_ttf, png_bytes, write_zip

IDENTIFIER = "urn:uuid:11111111-2222-3333-4444-555555555555"
#: What a font obfuscated under somebody else's publication was keyed with.
FOREIGN = "urn:uuid:99999999-8888-7777-6666-555555555555"

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
  <head><meta charset="utf-8"/><title>Rozdzia&#x142;</title>
    <style>@font-face { font-family: A; src: url("dobry.ttf"); }
           @font-face { font-family: B; src: url("zly.ttf"); }</style>
  </head>
  <body><p style="font-family: A">Tekst</p><p style="font-family: B">Więcej</p></body>
</html>
"""

TWO_FONTS = """<?xml version="1.0" encoding="UTF-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{algorithm}"/>
    <enc:CipherData><enc:CipherReference URI="OEBPS/dobry.ttf"/></enc:CipherData>
  </enc:EncryptedData>
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{algorithm}"/>
    <enc:CipherData><enc:CipherReference URI="OEBPS/zly.ttf"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""


def obfuscated(identifier: str) -> bytes:
    return deobfuscate(fake_ttf(), idpf_key(identifier), IDPF_PREFIX_LENGTH)


def two_fonts(path) -> str:
    """One font this book can decode and one it cannot, both declared."""
    package = MODERN_OPF.format(title="Test", extra_metadata="").replace(
        "</manifest>",
        '<item id="f1" href="dobry.ttf" media-type="font/ttf"/>'
        '<item id="f2" href="zly.ttf" media-type="font/ttf"/></manifest>',
    )
    return write_zip(
        str(path),
        {
            "META-INF/container.xml": CONTAINER.encode(),
            "META-INF/encryption.xml": TWO_FONTS.format(algorithm=IDPF_OBFUSCATION).encode(),
            "OEBPS/package.opf": package.encode(),
            "OEBPS/nav.xhtml": (
                '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" '
                'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl">'
                "<head><meta charset='utf-8'/><title>Spis</title></head><body>"
                '<nav epub:type="toc"><ol><li><a href="chapter.xhtml">R</a></li></ol></nav>'
                "</body></html>"
            ).encode(),
            "OEBPS/chapter.xhtml": PAGE.encode(),
            "OEBPS/picture.png": png_bytes(),
            "OEBPS/dobry.ttf": obfuscated(IDENTIFIER),
            "OEBPS/zly.ttf": obfuscated(FOREIGN),
        },
    )


@pytest.fixture
def rebuilt(tmp_path):
    source = two_fonts(tmp_path / "fonts.epub")
    result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
    assert result.output_path, result.report.to_text()
    return result


def contents(result) -> dict[str, bytes]:
    with zipfile.ZipFile(result.output_path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def rules_of(result) -> set[str]:
    return {f.rule for f in result.report.findings if f.rule}


class TestF007OneBadKeyDoesNotWipeTheOtherDeclaration:
    def test_the_font_that_decodes_comes_out_a_font(self, rebuilt):
        good = next(data for name, data in contents(rebuilt).items() if "dobry" in name)
        assert sniff_font_type(good) == "font/ttf"

    def test_the_font_that_does_not_decode_is_left_as_it_arrived(self, rebuilt):
        """Not half-decoded, not deleted: exactly the bytes the publisher
        shipped, so somebody with the right identifier can still use them."""
        bad = next(data for name, data in contents(rebuilt).items() if "zly" in name)
        assert bad == obfuscated(FOREIGN)

    def test_and_the_container_still_says_it_is_obfuscated(self, rebuilt):
        """The whole finding in one assertion. Bytes no reading system can use
        must not go out wearing the media type of a font that works, with
        nothing anywhere to say otherwise."""
        files = contents(rebuilt)
        assert "META-INF/encryption.xml" in files, (
            "the surviving obfuscation was declared in the source and has to be "
            "declared in the output — otherwise the book claims a working font"
        )
        declaration = files["META-INF/encryption.xml"].decode("utf-8")
        assert "zly" in declaration

    def test_and_does_not_claim_the_recovered_one_still_is(self, rebuilt):
        declaration = contents(rebuilt)["META-INF/encryption.xml"].decode("utf-8")
        assert "dobry" not in declaration

    def test_the_declaration_names_the_path_the_output_uses(self, rebuilt):
        """`encryption.xml` is keyed by container path, and the rebuild renames
        every file. A declaration pointing at the source's path declares nothing
        — which is `Book.rename` not carrying the register, the second defect
        that fell out of this one."""
        files = contents(rebuilt)
        declaration = files["META-INF/encryption.xml"].decode("utf-8")
        actual = next(name for name in files if "zly" in name)
        assert actual in declaration, f"{actual} is not what {declaration!r} names"

    def test_the_report_says_both_things_happened(self, rebuilt):
        found = rules_of(rebuilt)
        assert "font.deobfuscated" in found
        assert "font.deobfuscation-failed" in found
        assert "font.obfuscation-declared" in found

    def test_a_book_where_everything_decodes_declares_nothing(self, tmp_path):
        """The guard on the guard: if `encryption.xml` were written whenever the
        source had one, every assertion above would pass while the code was
        wrong."""
        source = two_fonts(tmp_path / "clean.epub")
        # Re-key the second font to this book's own identifier.
        with zipfile.ZipFile(source) as archive:
            entries = {
                name: archive.read(name)
                for name in archive.namelist()
                if name != "mimetype"  # `write_zip` writes it itself, uncompressed
            }
        entries["OEBPS/zly.ttf"] = obfuscated(IDENTIFIER)
        good = write_zip(str(tmp_path / "clean2.epub"), entries)
        result = rebuild(good, str(tmp_path / "clean-out.epub"), Policy.preset("preserve"))
        assert "META-INF/encryption.xml" not in contents(result)
        assert "font.obfuscation-declared" not in rules_of(result)


class TestF007TheRegisterSurvivesTheRebuild:
    """`Book.rename` carried the spine, the cover, the navigation and the media
    durations — and not the register of what is still encrypted. Invisible while
    the register was always emptied; a stale key in a dictionary nothing reads.
    It shows the moment the register survives a rebuild, which is what the fix
    above makes it do."""

    def test_a_move_takes_the_encryption_entry_with_it(self):
        from epubforge.model import Book, Resource

        book = Book()
        book.add(Resource(path="OEBPS/f.ttf", media_type="font/ttf", data=b"\x00"))
        book.encrypted["OEBPS/f.ttf"] = IDPF_OBFUSCATION
        book.rename("OEBPS/f.ttf", "EPUB/fonts/f.ttf")
        assert book.encrypted == {"EPUB/fonts/f.ttf": IDPF_OBFUSCATION}
