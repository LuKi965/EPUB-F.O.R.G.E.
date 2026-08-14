"""No rule in this program is about a particular book.

The owner asked it directly, about the fixture roles added for WP-3: does this
treat `ksiazka-1` literally — *if it is this book, do X* — or as an example of a
shape? The answer has to be the second one, because the first would make the
program worthless: the point is that it repairs every book somebody adds, not
that it has a list.

Two things are true and only one of them is worth much. The first is that no
book identity is in the code today — checked below by reading the package. The
second is that nothing stops one being added tomorrow, and that is what the
rest of this file is for: the rebuild is shown to decide from *structure* by
changing a book's identity and requiring the decisions not to move.

`fixtures.py` is the near miss and the reason this file exists. It holds two
digests. It is a catalogue of which purchased book fills which *test* role, and
a test role is not a rebuild rule — but a module in `epubforge/` holding the
digest of a specific book is exactly the shape of thing that becomes one by
accident, one convenient import at a time.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import zipfile

import pytest

from epubforge import fixtures
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "epubforge"

#: The two places a book's identity is legitimately known, and the whole list.
#: `fixtures` is the catalogue itself; `cli` and the GUI are how a person reads
#: it. Nothing that rebuilds a book is here, and nothing may be added without
#: the argument for why a rebuild decision depends on which book it is.
MAY_KNOW_ABOUT_FIXTURES = {"fixtures.py", "cli.py", "tabs.py"}


def modules() -> "list[pathlib.Path]":
    return sorted(PACKAGE.rglob("*.py"))


class TestNothingOnTheRebuildPathKnowsAboutAnyBook:
    def test_no_rebuilding_module_imports_the_fixture_catalogue(self):
        offenders = []
        for path in modules():
            if path.name in MAY_KNOW_ABOUT_FIXTURES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                if any(name.split(".")[-1] == "fixtures" for name in names):
                    offenders.append(path.name)
        assert not offenders, (
            f"{offenders} import the fixture catalogue. A module that rebuilds a "
            f"book must not be able to find out which book it is."
        )

    def test_no_recorded_digest_appears_in_the_package(self):
        """The digests are in `tests/fixtures/*.json` and belong there."""
        recorded = {
            fixtures.recorded(role.id)["sha256"]
            for role in fixtures.ROLES
            if fixtures.recorded(role.id)
        }
        for path in modules():
            text = path.read_text(encoding="utf-8")
            for digest in recorded:
                assert digest not in text, f"{path.name} names a specific book"

    def test_the_catalogue_holds_role_names_and_not_book_names(self):
        source = (PACKAGE / "fixtures.py").read_text(encoding="utf-8")
        for role in fixtures.ROLES:
            assert role.id in source
        # Whatever else is in there, it is not sixty-four hex characters.
        assert not re.search(r"\b[0-9a-f]{64}\b", source)


class TestTheRebuildDecidesFromStructureAndNotFromIdentity:
    """The claim, tested by changing the identity and requiring the decisions
    not to move. This is the part that would catch a rule keyed on a title
    however it got there — an import, a constant, a regex on the file name."""

    def source(self, tmp_path, name: str, *, title: str, author: str, identifier: str) -> str:
        """One book, written twice with different identities and one layout.

        Deliberately carrying a defect the rebuild has to notice — a stylesheet
        pointing at a font that is not in the archive — so the test compares a
        rebuild that *did* something rather than two rebuilds that did nothing.
        """
        from tests.factory import write_zip

        package = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
            'unique-identifier="i"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:opf="http://www.idpf.org/2007/opf">'
            f"<dc:identifier id=\"i\">{identifier}</dc:identifier>"
            f"<dc:title>{title}</dc:title>"
            f'<dc:creator opf:role="aut">{author}</dc:creator>'
            "<dc:language>pl</dc:language></metadata>"
            '<manifest><item id="c" href="text/r.xhtml" '
            'media-type="application/xhtml+xml"/>'
            '<item id="s" href="style.css" media-type="text/css"/>'
            '<item id="t" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '</manifest><spine toc="t"><itemref idref="c"/></spine></package>'
        )
        ncx = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            f'<head><meta name="dtb:uid" content="{identifier}"/></head>'
            f"<docTitle><text>{title}</text></docTitle><navMap>"
            '<navPoint id="n1" playOrder="1"><navLabel><text>Rozdział</text>'
            '</navLabel><content src="text/r.xhtml"/></navPoint></navMap></ncx>'
        )
        return write_zip(
            str(tmp_path / name),
            {
                "META-INF/container.xml": (
                    '<?xml version="1.0" encoding="utf-8"?><container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                    'media-type="application/oebps-package+xml"/></rootfiles></container>'
                ).encode(),
                "OEBPS/content.opf": package.encode(),
                "OEBPS/toc.ncx": ncx.encode(),
                "OEBPS/style.css": (
                    "@font-face { font-family: X; src: url(Fonts/nie-ma.ttf); }"
                    "p { font-family: X, serif; }"
                ).encode(),
                "OEBPS/text/r.xhtml": (
                    '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
                    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
                    '<meta charset="utf-8"/><title>R</title>'
                    '<link rel="stylesheet" href="../style.css"/></head>'
                    "<body><h1>Rozdział</h1><center>Tekst.</center></body></html>"
                ).encode(),
            },
        )

    def rules_of(self, result) -> set:
        return {finding.rule for finding in result.report.findings if finding.rule}

    def rebuild_both(self, tmp_path):
        first = self.source(
            tmp_path, "a.epub",
            title="Zimła Książka", author="Jan Kowalski",
            identifier="urn:uuid:11111111-1111-4111-8111-111111111111",
        )
        second = self.source(
            tmp_path, "b.epub",
            title="Cokolwiek Innego", author="Nikt Nieznany",
            identifier="urn:uuid:22222222-2222-4222-8222-222222222222",
        )
        policy = Policy.preset("preserve", validate_before_publish="off")
        return (
            rebuild(first, str(tmp_path / "out-a.epub"), policy),
            rebuild(second, str(tmp_path / "out-b.epub"), policy),
        )

    def test_the_same_repairs_are_made_whoever_wrote_the_book(self, tmp_path):
        one, two = self.rebuild_both(tmp_path)
        assert one.status.wrote_a_file and two.status.wrote_a_file
        assert self.rules_of(one) == self.rules_of(two)

    def test_and_there_were_repairs_to_compare(self, tmp_path):
        """A guard on the test above: two books that provoked nothing would
        agree about nothing, and the comparison would prove nothing."""
        one, _ = self.rebuild_both(tmp_path)
        assert len(self.rules_of(one)) > 5, self.rules_of(one)

    def test_the_file_name_is_not_read_as_a_fact_about_the_book(self, tmp_path):
        """The cheapest way a book-specific rule gets in: a match on the name.

        The same bytes under two names, rebuilt reproducibly, come out as the
        same file. `dcterms:modified` is taken from the source in that mode, so
        what is left to differ is only what the program decided.
        """
        from tests.factory import make_legacy_epub

        # A name with the shape of a real book's — spaces, a dash, Polish
        # diacritics — and not any actual title. Naming one here would put it in
        # a public repository, which is the thing the fixture roles exist to
        # avoid; the check in `tools/sprawdz-nazwy.py` caught the first draft of
        # this very file doing it.
        first = tmp_path / "Zimła Książka - Część Wtóra.epub"
        make_legacy_epub(str(first))
        second = tmp_path / "jakas-ksiazka.epub"
        second.write_bytes(first.read_bytes())

        policy = Policy.preset(
            "preserve", reproducible=True, validate_before_publish="off"
        )
        one = rebuild(str(first), str(tmp_path / "out-a.epub"), policy)
        two = rebuild(str(second), str(tmp_path / "out-b.epub"), policy)
        assert one.status.wrote_a_file and two.status.wrote_a_file
        assert self.digest(one.output_path) == self.digest(two.output_path)

    @staticmethod
    def digest(path) -> str:
        """The archive's contents, entry by entry — the file name is *in* the
        ZIP, so hashing the whole file would find a difference this test is
        deliberately not about."""
        sha = hashlib.sha256()
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                sha.update(name.encode())
                sha.update(archive.read(name))
        return sha.hexdigest()


class TestTheFixtureRolesDescribeShapesAndNotBooks:
    """What the roles are *for*, stated as a test.

    A role says "an EPUB 2 package with full-page cover art and a dedication
    composed against the bottom edge". Any book of that shape plays it. The
    digest recorded beside it says which copy the numbers were measured on —
    it is provenance for a measurement, not a condition in a rule.
    """

    def test_a_role_is_described_by_what_the_book_contains(self):
        for role in fixtures.ROLES:
            assert role.exercises
            for line in role.exercises:
                assert len(line) > 20, f"{role.id}: {line!r} is a label, not a shape"

    def test_the_recorded_digest_is_provenance_and_not_a_condition(self):
        """It is used to *find* a copy on a shelf and by nothing else. If it
        were a condition, the rebuild would import this module — and the test
        at the top of this file says it does not."""
        source = (PACKAGE / "fixtures.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        users = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "rebuild" not in users

    @pytest.mark.parametrize("role", [role.id for role in fixtures.ROLES])
    def test_the_committed_profile_would_fit_more_than_one_book(self, role):
        """Deliberately so. The profile is a shape — "EPUB 2, about sixty-five
        documents, a handful of images" — and shapes are shared. That it is not
        an identity is the point; identification is the digest's job, and the
        one time this was allowed to identify by shape it handed a different
        novel to the role."""
        entry = fixtures.recorded(role)
        assert set(entry["profile"]) == {
            "package_version", "documents", "spine", "images", "fonts", "stylesheets"
        }
        assert all(
            isinstance(value, (int, str)) for value in entry["profile"].values()
        )


class TestTheRulesThemselvesNameConstructsAndNotWorks:
    """One level up from the fixtures: the rule catalogue.

    Every finding this program can report is a sentence about a construct —
    a dead reference, a missing language, a `<center>` element. A rule whose
    text named a publisher, a series or a title would be this program having an
    opinion about somebody's book rather than about EPUB.
    """

    #: Proper nouns a rule may legitimately contain: formats, specifications,
    #: tools and the devices the compatibility profiles are named after. The
    #: list is the test — anything capitalised mid-sentence that is not here is
    #: a name this program has no business holding an opinion about.
    ALLOWED_NAMES = frozenset({
        "EPUB", "EPUBCheck", "XHTML", "HTML", "XML", "CSS", "NCX", "OPF", "SVG",
        "MathML", "PNG", "JPEG", "GIF", "WebP", "TIFF", "ZIP", "OCF", "DRM",
        "URL", "URI", "UUID", "ISBN", "ASCII", "Unicode", "UTF", "PANOSE",
        "Calibre", "Kindle", "Kobo", "Apple", "Adobe", "Sigil", "InDesign",
        "PDF", "JavaScript", "Java", "Python", "Windows", "Linux", "OS",
        "Accessibility", "WCAG", "ARIA", "PLN", "MiB", "GiB", "KiB",
        "W3C", "IDPF", "DAISY", "META", "INF", "MACOSX", "Thumbs",
        "AppleDouble", "TAK", "BRAK", "NIE",
        "BCP", "Books", "DOCTYPE", "DTD", "HTML5", "ISO", "MIME", "PATH",
        "RMSDK", "Sigil", "InDesign",
        # Language names, which a rule about a language rule may state.
        "Polish",
        # Polish `Twoje`, capitalised after a colon in one rule's second half.
        "Twoje",
    })

    def test_no_rule_text_names_anything_this_program_should_not_know(self):
        """Deliberately written without naming a single book.

        The first version of this test listed the titles it was looking for —
        in a regex, in a public repository, which is the leak it was written to
        prevent. The naming check caught it within the minute. So it looks for
        the *shape* instead: a capitalised word in the middle of a sentence
        that is not a format, a specification or a device.
        """
        from epubforge.rules import CATALOGUES, DETAILS, DETAILS_PL

        catalogues = dict(CATALOGUES)
        catalogues["details-en"] = DETAILS
        catalogues["details-pl"] = DETAILS_PL
        # Mid-sentence only: a capital after `. ` or at the start is grammar.
        mid_sentence = re.compile(r"(?<=[a-ząćęłńóśźż,;:] )([A-ZĄĆĘŁŃÓŚŹŻ]\w+)")
        offenders = []
        for label, catalogue in catalogues.items():
            for rule, text in catalogue.items():
                for name in mid_sentence.findall(text):
                    if name not in self.ALLOWED_NAMES:
                        offenders.append(f"{label} {rule}: {name}")
        assert not offenders, offenders

    def test_there_are_enough_rules_for_that_to_mean_something(self):
        from epubforge.rules import CATALOGUES

        assert len(CATALOGUES["pl"]) > 100


def test_the_exemption_list_is_not_quietly_growing():
    """A ratchet on the list at the top of this file.

    Three modules may know which book is which, and each is a place a person
    *asks*. The failure this guards against is not somebody adding a rule about
    the Witcher on purpose; it is `fixtures` becoming importable from one more
    place each release until something on the rebuild path has it.
    """
    assert MAY_KNOW_ABOUT_FIXTURES == {"fixtures.py", "cli.py", "tabs.py"}
    for name in MAY_KNOW_ABOUT_FIXTURES:
        assert any(path.name == name for path in modules()), f"{name} is gone"


def test_the_recorded_profiles_are_the_only_committed_trace_of_a_book():
    """And they are counts. Read as JSON rather than trusted: a title added to
    one of these files would be the same mistake as a title in the code, and
    would sit in a public repository."""
    for role in fixtures.ROLES:
        entry = json.loads(fixtures.profile_path(role.id).read_text(encoding="utf-8"))
        assert entry["role"] == role.id
        assert set(entry) == {"role", "sha256", "bytes", "profile"}
