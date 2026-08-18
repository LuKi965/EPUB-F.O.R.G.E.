"""End-to-end checks on the rebuilt container."""

from __future__ import annotations

import zipfile

import pytest
from lxml import etree

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Level

OPF_PATH = "EPUB/package.opf"
OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
XHTML_NS = "http://www.w3.org/1999/xhtml"


def opf_tree(archive: zipfile.ZipFile):
    return etree.fromstring(archive.read(OPF_PATH))


def test_mimetype_is_first_and_stored(rebuilt):
    with zipfile.ZipFile(rebuilt.output_path) as archive:
        entries = archive.infolist()
    assert entries[0].filename == "mimetype"
    assert entries[0].compress_type == zipfile.ZIP_STORED
    with zipfile.ZipFile(rebuilt.output_path) as archive:
        assert archive.read("mimetype") == b"application/epub+zip"


def test_container_points_at_the_generated_package(archive):
    container = etree.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(
        ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
    )
    assert rootfile.get("full-path") == OPF_PATH


def test_package_is_epub3_with_required_metadata(archive):
    package = opf_tree(archive)
    assert package.get("version") == "3.0"
    assert package.get("unique-identifier") == "pub-id"

    identifier = package.find(".//dc:identifier", OPF_NS)
    assert identifier.get("id") == "pub-id"

    modified = package.xpath(
        './/opf:meta[@property="dcterms:modified"]', namespaces=OPF_NS
    )
    assert len(modified) == 1
    assert modified[0].text.endswith("Z")


def test_broken_language_tag_is_normalised(archive):
    language = opf_tree(archive).find(".//dc:language", OPF_NS)
    assert language.text == "pl-PL"


def test_ambiguous_date_becomes_iso(archive):
    date = opf_tree(archive).find(".//dc:date", OPF_NS)
    assert date.text == "2011-03-12"


def test_calibre_series_becomes_epub3_collection(archive):
    package = opf_tree(archive)
    collection = package.xpath(
        './/opf:meta[@property="belongs-to-collection"]', namespaces=OPF_NS
    )
    assert collection[0].text == "Kroniki"
    position = package.xpath('.//opf:meta[@property="group-position"]', namespaces=OPF_NS)
    assert position[0].text == "2"


def test_creator_role_and_file_as_are_refined(archive):
    package = opf_tree(archive)
    creator = package.find(".//dc:creator", OPF_NS)
    assert creator.text == "Jan Kowalski"
    role = package.xpath(
        f'.//opf:meta[@refines="#{creator.get("id")}"][@property="role"]', namespaces=OPF_NS
    )
    assert role[0].text == "aut"


def test_every_manifest_item_exists_and_every_file_is_manifested(archive):
    package = opf_tree(archive)
    names = set(archive.namelist())
    hrefs = {
        "EPUB/" + item.get("href")
        for item in package.xpath(".//opf:manifest/opf:item", namespaces=OPF_NS)
    }
    assert hrefs <= names
    unlisted = names - hrefs - {"mimetype", "META-INF/container.xml", OPF_PATH}
    assert not unlisted, f"files present but unmanifested: {unlisted}"


def test_spine_references_only_existing_items(archive):
    package = opf_tree(archive)
    ids = {item.get("id") for item in package.xpath(".//opf:manifest/opf:item", namespaces=OPF_NS)}
    refs = [ref.get("idref") for ref in package.xpath(".//opf:spine/opf:itemref", namespaces=OPF_NS)]
    assert refs and set(refs) <= ids
    # The source spine pointed at a non-existent id; it must not survive.
    assert len(refs) == 2


def test_navigation_document_is_declared_and_parsable(archive):
    package = opf_tree(archive)
    nav_items = package.xpath('.//opf:item[contains(@properties, "nav")]', namespaces=OPF_NS)
    assert len(nav_items) == 1
    nav = etree.fromstring(archive.read("EPUB/" + nav_items[0].get("href")))
    toc = nav.xpath(
        '//xhtml:nav[@epub:type="toc"]',
        namespaces={"xhtml": XHTML_NS, "epub": "http://www.idpf.org/2007/ops"},
    )
    assert toc, "nav document has no toc"
    links = toc[0].xpath(".//xhtml:a/@href", namespaces={"xhtml": XHTML_NS})
    assert len(links) == 3


def test_legacy_ncx_is_emitted_and_wired_to_the_spine(archive):
    package = opf_tree(archive)
    spine = package.find(".//opf:spine", OPF_NS)
    toc_id = spine.get("toc")
    assert toc_id
    item = package.xpath(f'.//opf:item[@id="{toc_id}"]', namespaces=OPF_NS)[0]
    assert item.get("media-type") == "application/x-dtbncx+xml"
    etree.fromstring(archive.read("EPUB/" + item.get("href")))


def test_content_documents_are_well_formed_default_namespace_xhtml(archive):
    package = opf_tree(archive)
    documents = package.xpath(
        './/opf:item[@media-type="application/xhtml+xml"]', namespaces=OPF_NS
    )
    assert documents
    for item in documents:
        raw = archive.read("EPUB/" + item.get("href"))
        root = etree.fromstring(raw)  # raises on any well-formedness failure
        assert root.tag == f"{{{XHTML_NS}}}html"
        assert root.nsmap.get(None) == XHTML_NS
        assert b"<html:" not in raw
        assert root.get("lang") == "pl-PL"


def test_content_documents_use_the_xhtml_extension(archive):
    for name in archive.namelist():
        if name.startswith("EPUB/text/"):
            assert name.endswith(".xhtml")


class TestLegacyMarkup:
    def chapter(self, archive):
        return archive.read("EPUB/text/0000-chapter-1.xhtml").decode()

    def test_center_font_and_table_attributes_become_css(self, archive):
        html = self.chapter(archive)
        assert "<center>" not in html and "<font" not in html
        assert 'style="text-align: center;"' in html
        assert "color: #884400" in html
        assert "background-color: #eeeeee" in html
        assert "border-spacing: 3px" in html
        assert "vertical-align: top" in html
        assert 'bgcolor' not in html and 'valign' not in html

    def test_tt_and_big_are_replaced(self, archive):
        html = archive.read("EPUB/text/0001-chapter2.xhtml").decode()
        assert "<tt>" not in html and "<big>" not in html
        assert "font-family: monospace" in html
        assert "font-size: larger" in html

    def test_anchor_name_becomes_id(self, archive):
        html = self.chapter(archive)
        assert 'name="kotwica"' not in html
        assert 'id="kotwica"' in html

    def test_images_gain_alt_text(self, archive):
        assert self.chapter(archive).count("alt=") == 2

    def test_undefined_entities_are_resolved(self, archive):
        html = archive.read("EPUB/text/0001-chapter2.xhtml").decode()
        assert "&mdash;" not in html
        assert "—" in html


class TestReferenceIntegrity:
    def test_invalid_ids_are_renamed_and_links_follow(self, archive):
        chapter_one = archive.read("EPUB/text/0000-chapter-1.xhtml").decode()
        chapter_two = archive.read("EPUB/text/0001-chapter2.xhtml").decode()
        assert 'id="id-1st-heading"' in chapter_two
        assert 'href="0001-chapter2.xhtml#id-1st-heading"' in chapter_one

    def test_navigation_fragments_are_remapped_too(self, archive):
        nav = archive.read("EPUB/nav.xhtml").decode()
        ncx = archive.read("EPUB/toc.ncx").decode()
        assert "#id-1st-heading" in nav
        assert "#id-1st-heading" in ncx
        assert "#1st-heading\"" not in nav

    def test_stylesheet_link_is_repointed(self, archive):
        assert 'href="../styles/main.css"' in archive.read(
            "EPUB/text/0000-chapter-1.xhtml"
        ).decode()

    def test_css_urls_follow_transcoded_images(self, archive):
        css = archive.read("EPUB/styles/main.css").decode()
        assert "stara.bmp" not in css
        assert "stara.png" in css
        assert "../fonts/moja.ttf" in css

    def test_toc_entries_pointing_nowhere_are_dropped(self, rebuilt):
        nav = [
            f for f in rebuilt.report.findings
            if f.stage == "navigation" and f.rule == "nav.entry-dropped"
        ]
        assert nav


class TestAssets:
    def test_a_foreign_image_is_transcoded_to_png(self, archive):
        """BMP is not a core media type and readers disagree about it."""
        names = archive.namelist()
        assert not any(name.endswith(".bmp") for name in names)
        assert "EPUB/images/stara.png" in names

    def test_webp_is_left_alone(self, archive):
        """It is a core media type in EPUB 3.3 — the EPUBCheck this repository
        ships validates a bare one with no fallback and says nothing. Converting
        it was work nobody asked for that cost an animation its frames."""
        names = archive.namelist()
        assert "EPUB/images/deco.webp" in names
        assert "EPUB/images/deco.png" not in names

    def test_non_ascii_filenames_are_slugged(self, archive):
        assert "EPUB/images/okladka.png" in archive.namelist()

    def test_cover_image_carries_the_manifest_property(self, archive):
        package = opf_tree(archive)
        covers = package.xpath(
            './/opf:item[contains(@properties, "cover-image")]', namespaces=OPF_NS
        )
        assert len(covers) == 1
        assert covers[0].get("href") == "images/okladka.png"

    def test_legacy_cover_meta_is_kept_for_old_readers(self, archive):
        package = opf_tree(archive)
        meta = package.xpath('.//opf:meta[@name="cover"]', namespaces=OPF_NS)
        assert meta and meta[0].get("content")

    def test_obfuscated_font_is_recovered_and_encryption_dropped(self, archive):
        assert "META-INF/encryption.xml" not in archive.namelist()
        font = archive.read("EPUB/fonts/moja.ttf")
        assert font.startswith(b"\x00\x01\x00\x00"), "font was not deobfuscated"

    def test_nothing_is_deleted_unless_asked(self, archive):
        """Since 0.1.7 the default keeps every file.

        The reference graph cannot yet see `srcset`, `<picture>` or a link made
        from inside an SVG, so "nothing points at this" is not the same claim as
        "nothing needs this" — and the difference was measured, not imagined.
        """
        names = archive.namelist()
        assert any("nieuzywany" in name for name in names)

    def test_removal_still_works_when_asked_for(self, legacy_epub, tmp_path):
        result = rebuild(
            legacy_epub,
            str(tmp_path / "swept.epub"),
            Policy.preset("preserve", drop_orphans=True),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
        assert not any("nieuzywany" in name for name in names)
        assert not any(".DS_Store" in name for name in names)

    def test_operating_system_junk_goes_either_way(self, archive):
        """`.DS_Store` and `Thumbs.db` are not book content under any reading,
        so they are not what the orphan question is about."""
        assert not any(".DS_Store" in name for name in archive.namelist())


class TestPolicyModes:
    def test_strict_neutralises_dead_links(self, rebuilt_strict):
        with zipfile.ZipFile(rebuilt_strict.output_path) as archive:
            html = archive.read("EPUB/text/0000-chapter-1.xhtml").decode()
        assert "brakujacy.xhtml" not in html
        assert "martwy link" in html, "link text must survive; only the href goes"

    def test_preserve_keeps_dead_links_and_says_so(self, rebuilt):
        with zipfile.ZipFile(rebuilt.output_path) as archive:
            html = archive.read("EPUB/text/0000-chapter-1.xhtml").decode()
        assert "brakujacy.xhtml" in html
        preserved = [f for f in rebuilt.report.findings if f.level is Level.PRESERVED]
        assert any(f.rule == "xhtml.dead-reference-kept" for f in preserved)

    def test_strict_removes_kindle_only_css(self, rebuilt_strict):
        with zipfile.ZipFile(rebuilt_strict.output_path) as archive:
            css = archive.read("EPUB/styles/main.css").decode()
        assert "amzn-kf8" not in css

    def test_preserve_keeps_kindle_css(self, archive):
        assert "amzn-kf8" in archive.read("EPUB/styles/main.css").decode()

    def test_minimal_preset_keeps_the_original_layout(self, legacy_epub, tmp_path):
        from epubforge.pipeline import rebuild
        from epubforge.policy import Policy

        result = rebuild(legacy_epub, str(tmp_path / "minimal.epub"), Policy.preset("minimal"))
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
        assert any(name.startswith("OEBPS/") for name in names)
        assert not any(name.startswith("EPUB/text/") for name in names)


class TestReportHonesty:
    """The report must account for structural work, not just content edits.

    A rebuild that relocates every file and upgrades the package version while
    reporting "0 fixed" is worse than useless — it reads as a no-op.
    """

    def rules(self, rebuilt, level: Level) -> set[str]:
        return {f.rule for f in rebuilt.report.findings if f.level is level}

    def test_version_upgrade_is_reported(self, rebuilt):
        assert "package.upgraded" in self.rules(rebuilt, Level.FIX)

    def test_file_reorganisation_is_reported_as_a_change(self, rebuilt):
        assert "structure.relaid-out" in self.rules(rebuilt, Level.FIX)

    def test_generated_navigation_is_reported_as_a_fix(self, rebuilt):
        assert self.rules(rebuilt, Level.FIX) & {"nav.generated", "nav.regenerated"}

    def test_corrected_manifest_media_types_are_reported(self, rebuilt):
        # The fixture declares chapter 2 as text/html, which it is not.
        assert any(
            "text/html" in (f.detail or "") + f.message for f in rebuilt.report.findings
        )

    def test_a_real_rebuild_never_reports_zero_changes(self, rebuilt):
        assert rebuilt.report.count(Level.FIX) > 0


class TestPublisherErrorRepair:
    """Mistakes the browser already discards, so repairing restores intent."""

    def stylesheet(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read("EPUB/styles/main.css").decode()

    def test_invalid_font_style_value_is_corrected(self, rebuilt):
        css = self.stylesheet(rebuilt)
        assert "font-style: regular" not in css
        assert "font-style: normal" in css
        assert any(
            "'regular'" in f.message for f in rebuilt.report.findings if f.level is Level.FIX
        )

    def test_positioning_with_no_faithful_translation_is_kept(self, rebuilt):
        """Nothing in this fixture is a page pinned to its foot — the rule is in
        the stylesheet, no document is that one block — so there is no
        equivalent to write, and the declaration stays.

        This is the conservative half of the pair. Deleting it would make a page
        appear and put its content somewhere the publisher did not ask for, and
        guessing at somebody's layout is how a tool that means well ruins a
        book. `TestAPagePinnedToItsFootStaysThere` is the other half.
        """
        assert "position: absolute" in self.stylesheet(rebuilt)
        assert any(
            f.level is Level.PRESERVED and f.rule == "css.position-kept-reflowable"
            for f in rebuilt.report.findings
        )

    # The strict half of this moved to `TestAPagePinnedToItsFootStaysThere`,
    # which builds a book that actually carries `class="dol"`. In this fixture
    # nothing does, so the rule is now removed by the unreachable-rule pass
    # before the positioning pass is asked anything — the test would have been
    # passing for the wrong reason.

    def test_fixed_layout_books_keep_their_positioning(self, legacy_epub, tmp_path):
        """Absolute positioning is how fixed-layout books work; never strip it."""
        from epubforge.policy import Policy
        from epubforge.reader import read_epub
        from epubforge.report import Report

        # Re-read and mark the book pre-paginated, then run the stage directly.
        from epubforge.stages import Context, StructureStage, StyleStage

        report = Report()
        book = read_epub(legacy_epub, report)
        book.rendition["layout"] = "pre-paginated"
        ctx = Context(book=book, policy=Policy.preset("preserve"), report=report)
        StructureStage().run(ctx)
        StyleStage().run(ctx)

        css = next(r for r in book.by_type("style")).text()
        assert "position: absolute" in css
        assert any(
            f.level is Level.PRESERVED and "fixed-layout" in (f.detail or "")
            for f in report.findings
        )


class TestImageParagraphs:
    """Cover and title pages are `<p><img/></p>`; body-text rules must not shift them."""

    def chapter(self, rebuilt) -> str:
        with zipfile.ZipFile(rebuilt.output_path) as archive:
            return archive.read("EPUB/text/0001-chapter2.xhtml").decode()

    def test_image_only_paragraph_is_centred_and_unindented(self, rebuilt):
        html = self.chapter(rebuilt)
        assert 'style="text-indent: 0; text-align: center;"' in html

    def test_explicit_alignment_is_respected(self, rebuilt):
        """An inline text-align is a deliberate choice and must survive."""
        import re

        html = self.chapter(rebuilt)
        paragraph = re.search(r'<p[^>]*>(?=<img[^>]*alt="ozdoba")', html)
        assert paragraph, "the decorative image paragraph is missing"
        assert "text-align: left" in paragraph.group()
        assert "center" not in paragraph.group()

    def test_paragraphs_with_text_are_left_alone(self, rebuilt):
        with zipfile.ZipFile(rebuilt.output_path) as archive:
            chapter_one = archive.read("EPUB/text/0000-chapter-1.xhtml").decode()
        # Chapter one's images sit inside a paragraph that also has prose.
        assert "text-indent: 0; text-align: center;" not in chapter_one

    def test_the_change_is_reported(self, rebuilt):
        assert any(
            "image-only paragraph" in f.message
            for f in rebuilt.report.findings
            if f.level is Level.FIX
        )

    def test_a_rule_targeting_the_paragraph_is_obeyed(self, rebuilt):
        """The publisher aimed p.ilustracja at these; right-aligned is a choice."""
        import re

        html = self.chapter(rebuilt)
        paragraph = re.search(r'<p[^>]*>(?=<img[^>]*alt="wybor wydawcy")', html)
        assert paragraph, "the publisher-styled image paragraph is missing"
        assert 'class="ilustracja"' in paragraph.group()
        assert "text-align" not in paragraph.group(), "its alignment must not be overridden"

    def test_respected_paragraphs_are_reported(self, rebuilt):
        assert any(
            "as the publisher styled them" in f.message
            for f in rebuilt.report.findings
            if f.level is Level.PRESERVED
        )


class TestEpub2ToEpub3Migration:
    """Constructs XHTML 1.1 allowed that XHTML 5 rejects."""

    def chapter(self, rebuilt) -> str:
        with zipfile.ZipFile(rebuilt.output_path) as archive:
            return archive.read("EPUB/text/0001-chapter2.xhtml").decode()

    def test_percentage_width_moves_from_attribute_to_css(self, rebuilt):
        """XHTML 5 requires width to be a bare integer; 10% makes it invalid."""
        import re

        html = self.chapter(rebuilt)
        image = re.search(r'<img[^>]*alt="procent"[^>]*/>', html)
        assert image, "the image is missing"
        assert 'width="10%"' not in image.group()
        assert "width: 10%" in image.group()

    def test_integer_width_stays_an_attribute(self, archive):
        """Where HTML 5 still defines the attribute, leave it alone."""
        # Chapter one's table had width="100%" on a <table>, which is not a
        # replaced element, so it must have become CSS.
        html = archive.read("EPUB/text/0000-chapter-1.xhtml").decode()
        assert 'width="100%"' not in html
        assert "width: 100%" in html

    def test_block_inside_inline_is_promoted(self, rebuilt):
        """A block span inside an inline <a> splits the line box."""
        import re

        html = self.chapter(rebuilt)
        anchor = re.search(r"<a[^>]*>(?=<span[^>]*numer)", html)
        assert anchor, "the heading anchor is missing"
        assert "display: inline-block" in anchor.group()

    def test_promotion_is_reported(self, rebuilt):
        assert any(
            f.rule == "xhtml.inline-promoted"
            for f in rebuilt.report.findings
            if f.level is Level.FIX
        )


class TestRemoteResources:
    def properties_of(self, rebuilt, href_fragment: str) -> str:
        with zipfile.ZipFile(rebuilt.output_path) as archive:
            package = etree.fromstring(archive.read(OPF_PATH))
        item = package.xpath(
            f'.//opf:item[contains(@href, "{href_fragment}")]', namespaces=OPF_NS
        )[0]
        return item.get("properties") or ""

    def test_an_external_hyperlink_is_not_a_remote_resource(self, rebuilt):
        """remote-resources covers embedded media, not where links point."""
        assert "remote-resources" not in self.properties_of(rebuilt, "chapter2")


class TestWatermarks:
    """The mark is the publisher's; the mess it makes is not."""

    def chapter(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read("EPUB/text/0001-chapter2.xhtml").decode()

    def stylesheet(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read("EPUB/styles/main.css").decode()

    def test_the_token_itself_is_never_touched(self, rebuilt):
        assert "NzgxMjI0NjMzOTUzNjQ" in self.chapter(rebuilt)

    def test_repeated_inline_styling_is_replaced_by_one_rule(self, rebuilt):
        html = self.chapter(rebuilt)
        assert "font-size:1px !important" not in html
        assert "epubforge-watermark" in html
        assert "epubforge-watermark" in self.stylesheet(rebuilt)

    def test_marker_is_hidden_from_assistive_technology(self, rebuilt):
        import re

        marker = re.search(r"<div[^>]*epubforge-watermark[^>]*>", self.chapter(rebuilt))
        assert marker and 'aria-hidden="true"' in marker.group()

    def test_replacement_is_never_more_visible_than_the_original(self, rebuilt):
        """Publishers hide these at 0pt as well as 1px; 0 is safe for both."""
        assert "font-size: 0 !important" in self.stylesheet(rebuilt)

    def test_a_visible_notice_is_left_alone(self, rebuilt):
        import re

        html = self.chapter(rebuilt)
        assert "Order ##46932" in html
        notice = re.search(r"<div[^>]*>(?=This document is protected)", html)
        assert notice, "the notice element is missing"
        # It is meant to be read, so it keeps its own styling and stays audible.
        assert "epubforge-watermark" not in notice.group()
        assert "aria-hidden" not in notice.group()
        assert "font-style:italic" in notice.group()

    def test_the_notice_and_its_personal_data_are_reported(self, rebuilt):
        findings = [
            f for f in rebuilt.report.findings
            if "visible watermark" in f.message
        ]
        assert findings and findings[0].level is Level.PRESERVED
        assert "jan@example.test" in (findings[0].detail or "")

    def test_ordinary_small_print_is_not_mistaken_for_a_watermark(self, rebuilt):
        """0.9em is how publishers set legitimate fine print."""
        import re

        html = self.chapter(rebuilt)
        paragraph = re.search(r"<p[^>]*>(?=Drobny druk)", html)
        assert paragraph, "the fine print is missing"
        assert "epubforge-watermark" not in paragraph.group()
        assert "aria-hidden" not in paragraph.group()

    def run_with(self, legacy_epub, tmp_path, mode: str):
        from epubforge.pipeline import rebuild as run
        from epubforge.policy import Policy

        policy = Policy.preset("preserve", watermarks=mode)
        return run(legacy_epub, str(tmp_path / f"{mode}.epub"), policy)

    def test_consolidation_can_be_switched_off(self, legacy_epub, tmp_path):
        result = self.run_with(legacy_epub, tmp_path, "keep")
        html = self.chapter(result)
        assert "font-size:1px !important" in html
        assert "epubforge-watermark" not in html

    def test_gathering_moves_the_token_to_the_head_of_its_own_document(
        self, legacy_epub, tmp_path
    ):
        """The point of `gather`: out of the text, still in the file.

        Not "somewhere in the book" — in the head of the document it came from,
        so a shop tracing a leak finds it where it put it.
        """
        result = self.run_with(legacy_epub, tmp_path, "gather")
        html = self.chapter(result)
        head = html.split("</head>")[0]
        assert 'name="epubforge-watermark"' in head
        assert "NzgxMjI0NjMzOTUzNjQ" in head
        # And nowhere else: the body is what a reader and its speech engine read.
        assert "NzgxMjI0NjMzOTUzNjQ" not in html.split("</head>", 1)[1]

    def test_gathering_leaves_the_surrounding_text_where_it_was(
        self, legacy_epub, tmp_path
    ):
        """The marker sits at the end of a chapter; the chapter is not the marker."""
        result = self.run_with(legacy_epub, tmp_path, "gather")
        html = self.chapter(result)
        assert "Order ##46932" in html  # the visible notice is untouched
        assert "Drobny druk" in html

    def test_removal_takes_the_token_out_of_the_book_entirely(
        self, legacy_epub, tmp_path
    ):
        result = self.run_with(legacy_epub, tmp_path, "remove")
        html = self.chapter(result)
        assert "NzgxMjI0NjMzOTUzNjQ" not in html
        assert "epubforge-watermark" not in html

    def test_removal_is_reported_as_a_warning_because_it_loses_something(
        self, legacy_epub, tmp_path
    ):
        result = self.run_with(legacy_epub, tmp_path, "remove")
        findings = [f for f in result.report.findings if f.rule == "xhtml.watermark-removed"]
        assert findings and findings[0].level is Level.WARN

    def test_no_preset_ever_reaches_removal(self):
        """The standing rule: nothing is deleted because a preset felt like it."""
        from epubforge.policy import Policy

        for name in ("preserve", "strict", "minimal"):
            assert Policy.preset(name).watermarks != "remove"

    def test_a_misspelt_mode_is_refused_rather_than_ignored(self):
        from epubforge.policy import Policy

        with pytest.raises(ValueError):
            Policy.preset("preserve", watermarks="gathr")


class TestStylesheetLinting:
    def stylesheet(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read("EPUB/styles/main.css").decode()

    def test_reader_specific_property_is_reported_and_kept(self, rebuilt):
        preserved = [
            f for f in rebuilt.report.findings
            if f.level is Level.PRESERVED and "reader-specific" in f.message
        ]
        assert preserved and "adobe-hyphenate" in (preserved[0].detail or "")
        assert "adobe-hyphenate" in self.stylesheet(rebuilt)

    def test_strict_removes_only_the_reader_specific_property(self, rebuilt_strict):
        css = self.stylesheet(rebuilt_strict)
        assert "adobe-hyphenate" not in css
        # The standard EPUB prefix must survive; readers honour it.
        assert "-epub-hyphenate" in css
        assert "color: #884400" in css or "color:#884400" in css

    def test_strict_output_is_still_parsable(self, rebuilt_strict):
        import cssutils

        sheet = cssutils.parseString(self.stylesheet(rebuilt_strict))
        assert len(sheet.cssRules) > 1

    def test_font_stack_without_generic_family_is_reported(self, rebuilt):
        findings = [
            f for f in rebuilt.report.findings if "generic family" in f.message
        ]
        assert findings and findings[0].level is Level.PRESERVED
        assert "Judson" in (findings[0].detail or "")

    def test_font_face_declarations_are_not_counted_as_stacks(self, rebuilt):
        # @font-face names a font; only "Judson" in the h1 rule lacks a fallback.
        findings = [f for f in rebuilt.report.findings if "generic family" in f.message]
        assert findings[0].message.startswith("1 font stack")


class TestAccessibility:
    """Declarations must follow the content, because under the EAA they are claims."""

    def metadata(self, result) -> str:
        with zipfile.ZipFile(result.output_path) as archive:
            return archive.read(OPF_PATH).decode()

    def properties(self, result, name: str) -> list[str]:
        package = etree.fromstring(self.metadata(result).encode())
        return [
            (node.text or "")
            for node in package.xpath(
                f'.//opf:meta[@property="{name}"]', namespaces=OPF_NS
            )
        ]

    def test_access_modes_reflect_the_content(self, rebuilt):
        modes = self.properties(rebuilt, "schema:accessMode")
        assert "textual" in modes
        assert "visual" in modes, "the fixture has images"

    def test_features_are_declared(self, rebuilt):
        features = self.properties(rebuilt, "schema:accessibilityFeature")
        assert "tableOfContents" in features
        assert "structuralNavigation" in features
        assert "displayTransformability" in features, "reflowable text is resizable"

    def test_alternative_text_is_not_claimed_without_real_descriptions(self, rebuilt):
        """The fixture's images get an empty alt, which means decorative."""
        features = self.properties(rebuilt, "schema:accessibilityFeature")
        assert "alternativeText" not in features
        assert self.properties(rebuilt, "schema:accessModeSufficient") == ["textual,visual"]

    def test_a_summary_is_written(self, rebuilt):
        summary = self.properties(rebuilt, "schema:accessibilitySummary")
        assert summary and len(summary[0]) > 20

    def test_conformance_is_never_claimed_on_its_own(self, rebuilt):
        assert "conformsTo" not in self.metadata(rebuilt)

    def test_conformance_is_claimed_only_when_asked(self, legacy_epub, tmp_path):
        from epubforge.pipeline import rebuild as run
        from epubforge.policy import Policy

        policy = Policy.preset("preserve")
        policy.claim_conformance = "wcag-aa"
        result = run(legacy_epub, str(tmp_path / "a11y.epub"), policy)
        assert "WCAG 2.2 Level AA" in self.metadata(result)

    def test_metadata_can_be_switched_off(self, legacy_epub, tmp_path):
        from epubforge.pipeline import rebuild as run
        from epubforge.policy import Policy

        policy = Policy.preset("preserve")
        policy.accessibility_metadata = False
        result = run(legacy_epub, str(tmp_path / "plain.epub"), policy)
        assert "schema:accessMode" not in self.metadata(result)

    def test_missing_alt_is_reported_not_silently_hidden(self, rebuilt):
        assert any(
            "alt text" in f.message
            for f in rebuilt.report.findings
            if f.level is Level.WARN
        )


class TestPlaceholderAltDetection:
    @pytest.mark.parametrize(
        "alt,source",
        [
            ("title-1", "../images/title-1.jpg"),
            ("cover", "cover.jpg"),
            ("image", None),
            ("okładka", "x.png"),
            ("cover.jpg", None),
        ],
    )
    def test_useless_alt_is_recognised(self, alt, source):
        from epubforge.stages.accessibility import is_placeholder_alt

        assert is_placeholder_alt(alt, source)

    @pytest.mark.parametrize(
        "alt",
        [
            "Rycerz walczy ze smokiem",
            "Portret autora w młodości",
            "Mapa Królestw Północy",
        ],
    )
    def test_real_descriptions_are_left_alone(self, alt):
        from epubforge.stages.accessibility import is_placeholder_alt

        assert not is_placeholder_alt(alt, "../images/pic.jpg")


def test_rebuild_is_idempotent(rebuilt, tmp_path):
    """Rebuilding an already-clean book must not degrade it."""
    from epubforge.pipeline import rebuild as run
    from epubforge.policy import Policy

    second = run(rebuilt.output_path, str(tmp_path / "again.epub"), Policy.preset("preserve"))
    assert second.output_path
    with zipfile.ZipFile(second.output_path) as archive:
        names = set(archive.namelist())
    with zipfile.ZipFile(rebuilt.output_path) as archive:
        first_names = set(archive.namelist())
    assert names == first_names
    assert second.report.count(Level.ERROR) == 0


# --------------------------------------------------------------- minimal mode
def test_minimal_mode_leaves_content_files_byte_identical(legacy_epub, tmp_path):
    """The mode's whole promise, with both exceptions written down.

    Parsing and reserialising would break it, so documents are not opened. Two
    edits are made on the bytes, and they are the same kind of edit: a legacy
    DOCTYPE and an empty `<title>` each make the output an invalid EPUB 3, and
    neither says anything about how a page renders. Nothing else is touched,
    and this asserts it by applying both edits to the source side rather than
    by relaxing the comparison — so a third edit appearing fails here.

    The `<title>` half was found by measurement, not by reading the spec: once
    a corpus run started recording EPUBCheck's message identifiers, all
    fourteen errors container-only mode introduced across thirteen books came
    back as one identifier, and on the book of that shape I could reach, one
    sentence — *Element "title" must not be empty.*
    """
    from epubforge.stages.content import ContentStage
    from epubforge.xhtml import fill_empty_title, modernise_doctype, parse

    result = rebuild(legacy_epub, str(tmp_path / "minimal.epub"), Policy.preset("minimal"))
    assert result.output_path, result.report.to_text()

    with zipfile.ZipFile(legacy_epub) as source, zipfile.ZipFile(result.output_path) as output:
        original = set(source.namelist())
        # Content documents and stylesheets are what the promise covers. Fonts
        # are excluded on purpose: deobfuscation is its own policy switch, and
        # an obfuscated font is a container defect rather than content.
        shared = [
            name
            for name in output.namelist()
            if name in original and name.endswith((".xhtml", ".html", ".htm", ".css"))
        ]
        assert shared, "the fixture shares no files with its rebuild"
        for name in shared:
            expected, _ = modernise_doctype(source.read(name))
            if name.endswith((".xhtml", ".html", ".htm")):
                root, _ = parse(expected)

                class Named:
                    path = name
                    original_path = None

                expected, _ = fill_empty_title(
                    expected, ContentStage()._derive_title(root, Named)
                )
            assert expected == output.read(name), name


def test_minimal_mode_still_produces_a_navigation_document(legacy_epub, tmp_path):
    result = rebuild(legacy_epub, str(tmp_path / "minimal.epub"), Policy.preset("minimal"))
    with zipfile.ZipFile(result.output_path) as archive:
        assert any(name.endswith("nav.xhtml") for name in archive.namelist())


class TestTheCoverFitsThePage:
    """A cover with no rule sizing it is shown at its own pixel dimensions.

    Seen after a Calibre edit that wrote the cover stylesheet to the archive
    root while the page went on linking `../Styles/cover.css`: the link
    dangles, no rule reaches the image, and the reader falls back to 1600px of
    artwork on a six-inch screen.

    Only when nothing sizes it. Both limits can only ever shrink an image below
    its natural size, so the worst outcome is a reader ignoring them.
    """

    COVER_PAGE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pl">
<head><meta charset="utf-8"/><title>Okladka</title>{link}</head>
<body><div><img src="picture.png" alt="okladka"/></div></body>
</html>"""

    def build(self, tmp_path, *, sheet: str | None) -> str:
        import zipfile

        from .factory import CONTAINER, MODERN_NAV, png_bytes

        stylesheet_item = (
            '    <item id="css" href="style.css" media-type="text/css"/>\n' if sheet else ""
        )
        opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Okladka</dc:title>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
{stylesheet_item}    <item id="img" href="picture.png" media-type="image/png" properties="cover-image"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""
        path = str(tmp_path / f"cover-{'styled' if sheet else 'bare'}.epub")
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, b"application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                CONTAINER.replace("OEBPS/content.opf", "OEBPS/package.opf"),
            )
            archive.writestr("OEBPS/package.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", MODERN_NAV)
            archive.writestr(
                "OEBPS/chapter.xhtml",
                self.COVER_PAGE.format(
                    link='<link rel="stylesheet" href="style.css" type="text/css"/>'
                    if sheet
                    else ""
                ),
            )
            if sheet:
                archive.writestr("OEBPS/style.css", sheet)
            archive.writestr("OEBPS/picture.png", png_bytes())
        return path

    def cover_markup(self, tmp_path, *, sheet: str | None):
        """The whole cover document, not just its `<img>`.

        It used to return the image tag alone, which was right while the limits
        were an inline style and became wrong when WP-8 moved them into the
        head — where they have to be, because two of the three rules are about
        `html` and `body`.
        """
        source = self.build(tmp_path, sheet=sheet)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            return archive.read(name).decode(), result

    def test_an_unsized_cover_is_given_limits(self, tmp_path):
        """The limits are now a `<style>` block in the head rather than an
        inline style on the image, and that is WP-8's point rather than a
        detail: two of the three rules are about `html` and `body`, and inline
        styles cannot say anything about an ancestor. Without a height there,
        `max-height: 100%` is a percentage of nothing and does not apply."""
        markup, result = self.cover_markup(tmp_path, sheet=None)
        assert "max-width: 100%" in markup and "max-height: 100%" in markup
        # The margin joined the height in EF-057: a body given `height: 100%`
        # while it still carries the browser's 8px default makes a page taller
        # than the window, and the cover then sits below the fold.
        assert "html, body { margin: 0; padding: 0; height: 100%; }" in markup
        assert any("page-fitting" in f.message for f in result.report.findings)

    def test_a_cover_the_publisher_sized_is_left_alone(self, tmp_path):
        markup, result = self.cover_markup(
            tmp_path, sheet="img { max-height: 98%; max-width: 100%; }"
        )
        # The claim is that *the cover repair* did nothing, not that nothing in
        # the document has a style: the image-paragraph centring is a different
        # rule with its own finding, and it fires here as it always did.
        assert "nothing in this book sized the cover" not in markup
        assert "max-height: 100%" not in markup
        assert not any("page-fitting" in f.message for f in result.report.findings)

    def test_a_width_attribute_counts_as_sizing(self, tmp_path):
        """Old books size images in HTML, and that is still a decision."""
        original = self.COVER_PAGE
        try:
            type(self).COVER_PAGE = original.replace(
                '<img src="picture.png"', '<img width="600" src="picture.png"'
            )
            source = self.build(tmp_path, sheet=None)
        finally:
            type(self).COVER_PAGE = original
        result = rebuild(source, str(tmp_path / "attr.epub"), Policy.preset("preserve"))
        assert not any("page-fitting" in f.message for f in result.report.findings)

    def test_only_one_document_is_touched(self, tmp_path):
        """Only the cover page. An illustration mid-chapter is a different
        question, and the cover page this tool generates already sizes its own.

        Counted per **document** rather than per `<img>` since WP-8: the rules
        moved from an inline style on the image to a block in the head, because
        two of the three are about `html` and `body`. The claim is the same one
        — exactly one page is fitted — measured where it now lives.

        This test is also the one that would have caught EF-024, and did not:
        it built a book with a single image, so "only the cover" and "every
        image" were indistinguishable. The fixture in
        `test_cover_by_manifest.py` carries a decoration as well.
        """
        source = self.build(tmp_path, sheet=None)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            pages = [
                archive.read(name).decode()
                for name in archive.namelist()
                if name.endswith(".xhtml")
            ]
        fitted = [page for page in pages if "nothing in this book sized the cover" in page]
        assert len(fitted) == 1, [page[:120] for page in fitted]


class TestContainerOnlyModeStillDeclaresWhatTheDocumentsHold:
    """It rebuilds the package as EPUB 3, so it owes EPUB 3 an honest manifest.

    Nineteen books in the private corpus went into this mode valid and came out
    with "The property svg should be declared in the OPF file". Calibre wraps a
    cover in `<svg>` and writes an EPUB 2 package, where no such declaration
    exists; we regenerate the package as EPUB 3, where it is required, and the
    code that works the properties out lived in the branch this mode skips.

    The one mode that promises to break nothing was breaking something, and it
    took a corpus that could tell "carried through" from "introduced" to see it
    at all — the same nineteen books had been counted as source defects.

    Reading a document to decide its properties writes no bytes, and this mode
    had already parsed every one of them to collect ids.
    """

    def book(self, tmp_path):
        from tests.factory import png_bytes, write_zip

        svg_page = (
            b'<?xml version="1.0" encoding="utf-8"?>\n'
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>C</title></head>'
            b'<body><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            b'<image xlink:href="c.png" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
            b"</svg></body></html>\n"
        )
        opf = (
            b'<?xml version="1.0" encoding="utf-8"?>\n'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="i">'
            b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"<dc:identifier id=\"i\">urn:uuid:1</dc:identifier><dc:title>T</dc:title>"
            b"<dc:language>pl</dc:language></metadata>"
            b'<manifest><item id="t" href="titlepage.xhtml" media-type="application/xhtml+xml"/>'
            b'<item id="c" href="c.png" media-type="image/png"/>'
            b'<item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>'
            b'<spine toc="n"><itemref idref="t"/></spine></package>\n'
        )
        ncx = (
            b'<?xml version="1.0" encoding="utf-8"?>\n'
            b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            b'<head><meta name="dtb:uid" content="urn:uuid:1"/></head>'
            b"<docTitle><text>T</text></docTitle><navMap><navPoint id=\"p1\" playOrder=\"1\">"
            b'<navLabel><text>C</text></navLabel><content src="titlepage.xhtml"/>'
            b"</navPoint></navMap></ncx>\n"
        )
        container = (
            b'<?xml version="1.0" encoding="utf-8"?>\n'
            b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
            b'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "svg.epub"),
            {
                "META-INF/container.xml": container,
                "OEBPS/content.opf": opf,
                "OEBPS/titlepage.xhtml": svg_page,
                "OEBPS/toc.ncx": ncx,
                "OEBPS/c.png": png_bytes(),
            },
        )

    def rebuilt(self, tmp_path):
        return rebuild(
            self.book(tmp_path), str(tmp_path / "out.epub"), Policy.preset("minimal")
        )

    def test_the_svg_property_is_declared(self, tmp_path):
        result = self.rebuilt(tmp_path)
        with zipfile.ZipFile(result.output_path) as archive:
            # This mode leaves the package where the source had it — moving it
            # would rewrite every href — so the container is what says where.
            container = etree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            )
            package = etree.fromstring(archive.read(rootfile.get("full-path")))
        item = package.xpath(
            './/opf:item[contains(@href, "titlepage")]', namespaces=OPF_NS
        )[0]
        assert "svg" in (item.get("properties") or "")

    def test_the_document_itself_is_untouched(self, tmp_path):
        """The property is a claim in the package about the document. Making it
        must not edit the document, which is this mode's entire promise."""
        source = self.book(tmp_path)
        with zipfile.ZipFile(source) as archive:
            before = archive.read("OEBPS/titlepage.xhtml")
        result = rebuild(source, str(tmp_path / "o.epub"), Policy.preset("minimal"))
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("titlepage.xhtml"))
            after = archive.read(name)
        assert after == before


class TestTheOneEditContainerOnlyModeMakes:
    """A legacy DOCTYPE makes a container-only rebuild an invalid EPUB 3.

    EPUBCheck: *Irregular DOCTYPE: found "-//W3C//DTD XHTML 1.1//EN", expected
    "<!DOCTYPE html>"*. It appeared on four of the first thirty-two real books
    this was run against, all of them in this mode. A DOCTYPE says nothing
    about how a page renders, so replacing it is the one edit that cannot
    change what the reader sees — and it is done on the bytes, because opening
    the document is what this mode promises not to do.
    """

    def _document(self, doctype: str, body: str = "<p>Tekst.</p>") -> bytes:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f"{doctype}\n"
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            f"<meta charset=\"utf-8\"/><title>R</title></head><body><h1>R</h1>{body}</body></html>"
        ).encode()

    def test_a_legacy_doctype_is_replaced(self):
        from epubforge.xhtml import modernise_doctype

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
            '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
        )
        updated, changed = modernise_doctype(data)
        assert changed
        assert b"<!DOCTYPE html>" in updated
        assert b"XHTML 1.1" not in updated
        # Everything else, to the byte.
        assert updated.replace(b"<!DOCTYPE html>", b"X") == data[: data.index(b"<!DOCTYPE")] + b"X" + data[data.index(b".dtd\">") + 6 :]

    def test_the_epub3_doctype_is_left_alone(self):
        from epubforge.xhtml import modernise_doctype

        data = self._document("<!DOCTYPE html>")
        updated, changed = modernise_doctype(data)
        assert not changed and updated == data

    def test_a_document_without_one_is_left_alone(self):
        from epubforge.xhtml import modernise_doctype

        data = b'<?xml version="1.0"?><html/>'
        updated, changed = modernise_doctype(data)
        assert not changed and updated == data

    def test_an_internal_subset_is_left_alone(self):
        """Those entities are used by the document, and `<!DOCTYPE html>` does
        not define them. Swapping it turns a book that is merely invalid into
        one that will not parse."""
        from epubforge.xhtml import modernise_doctype

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "x.dtd" '
            "[<!ENTITY mojaencja \"tekst\">]>",
            body="<p>&mojaencja;</p>",
        )
        updated, changed = modernise_doctype(data)
        assert not changed and updated == data

    def test_the_rebuild_reports_it(self, tmp_path):
        """The legacy fixture uses `&mdash;`, so it is now correctly left alone
        — which is the behaviour, not a gap in the test. This builds one that
        has a legacy DOCTYPE and no named entities."""
        from .factory import CONTAINER, MODERN_NAV, write_zip

        opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:title>Stary DOCTYPE</dc:title><dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        source = write_zip(
            str(tmp_path / "legacy-doctype.epub"),
            {
                "META-INF/container.xml": CONTAINER.replace(
                    "OEBPS/content.opf", "OEBPS/package.opf"
                ),
                "OEBPS/package.opf": opf,
                "OEBPS/nav.xhtml": MODERN_NAV,
                "OEBPS/ch.xhtml": self._document(
                    '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "x.dtd">'
                ).decode(),
            },
        )
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))
        assert any("DOCTYPE" in f.message for f in result.report.findings), [
            f.message for f in result.report.findings
        ]

    def test_a_named_entity_travels_with_the_doctype(self):
        """The case a real book found, and the reason this mode edits at all.

        A legacy DOCTYPE declares entities two ways: an internal subset, and
        the external DTD it names. The second is the one that matters — every
        XHTML 1.1 document may write `&nbsp;` because `xhtml11.dtd` declares
        it. Under EPUB 3 nothing fetches that DTD, so taking the declaration
        away without taking the entity with it strands the reference:
        *Fatal Error while parsing file: The entity "nbsp" was referenced, but
        not declared*. One book had 235 errors, and 228 of them traced back to
        seven documents that would not parse for this reason.

        A numeric reference is the same character and needs no declaration.
        """
        from epubforge.xhtml import modernise_doctype

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
            '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">',
            body="<p>Dwa&nbsp;słowa.</p>",
        )
        updated, changed = modernise_doctype(data)
        assert changed
        assert b"&nbsp;" not in updated
        assert b"&#160;" in updated
        assert b"<!DOCTYPE html>" in updated
        # The character is what matters, and it is the same one — which is
        # visible only once the document is parsed, since a numeric reference
        # is still a reference in the file.
        from lxml import etree

        root = etree.fromstring(updated)
        assert "Dwa\u00a0słowa." in "".join(root.itertext())

    def test_an_entity_nothing_can_resolve_stops_the_swap(self):
        """The safety net. A name no HTML vocabulary knows cannot be rewritten,
        so the declaration that defines it has to stay — the output remains an
        invalid EPUB 3, which is the lesser harm against a book that will not
        open."""
        from epubforge.xhtml import modernise_doctype, unresolvable_entities

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "x.dtd">',
            body="<p>&wydawnictwo;</p>",
        )
        updated, changed = modernise_doctype(data)
        assert not changed and updated == data
        assert unresolvable_entities(data) == {"wydawnictwo"}

    def test_the_five_xml_builtins_do_not_block_it(self):
        """`&amp;` and its four siblings need no declaration, so a document
        using only those is still safe to modernise. Treating them as a reason
        to stop would mean never modernising anything."""
        from epubforge.xhtml import modernise_doctype

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "x.dtd">',
            body="<p>Kowalski &amp; Wiśniewski &lt;tak&gt;</p>",
        )
        _, changed = modernise_doctype(data)
        assert changed

    def test_a_numeric_reference_does_not_block_it(self):
        from epubforge.xhtml import modernise_doctype

        data = self._document(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "x.dtd">',
            body="<p>Dwa&#160;słowa.</p>",
        )
        _, changed = modernise_doctype(data)
        assert changed


class TestTheArchiveDeclaresWhatItHolds:
    """`create_system = 3` says these are Unix attributes; the mode has to be
    a possible Unix mode.

    `0o644 << 16` leaves the file-type field zero — not a regular file, not a
    directory, not anything. Python's own `writestr` does the same, which is
    why it is common and why nothing on a desktop notices. It surfaced when an
    e-reader hung on every file this program had ever written, and both files
    that worked on it — one from another tool, one from Calibre — carry
    `S_IFREG`.
    """

    def test_every_entry_is_a_regular_file(self, rebuilt):
        import stat
        import zipfile

        with zipfile.ZipFile(rebuilt.output_path) as archive:
            for info in archive.infolist():
                mode = info.external_attr >> 16
                assert stat.S_ISREG(mode), f"{info.filename}: mode {mode:#o}"

    def test_the_permission_bits_are_still_readable(self, rebuilt):
        import zipfile

        with zipfile.ZipFile(rebuilt.output_path) as archive:
            for info in archive.infolist():
                assert (info.external_attr >> 16) & 0o777 == 0o644, info.filename

    def test_two_runs_still_produce_the_same_bytes(self, legacy_epub, tmp_path):
        """The attributes are a constant, so reproducibility is untouched — the
        thing every other field in this writer is arranged around."""
        one = rebuild(legacy_epub, str(tmp_path / "a.epub"), Policy.preset("preserve", modified_override="2020-01-01T00:00:00Z"))
        two = rebuild(legacy_epub, str(tmp_path / "b.epub"), Policy.preset("preserve", modified_override="2020-01-01T00:00:00Z"))
        assert open(one.output_path, "rb").read() == open(two.output_path, "rb").read()


class TestTheContentDirectoryMayBeTheRoot:
    """Calibre puts the package document at the archive root, and readers exist
    that were built against that layout.

    Making the directory configurable produced "/content.opf" and "/images/…" —
    a leading slash, which is not a container path at all and which EPUBCheck
    rejected on sight, 214 errors deep. Every place that builds a path inside
    the content directory now goes through one helper, because there were four
    of them and three were wrong.
    """

    def test_an_empty_directory_puts_the_package_at_the_root(self, legacy_epub, tmp_path):
        result = rebuild(
            legacy_epub,
            str(tmp_path / "root.epub"),
            Policy.preset("preserve", content_dir="", package_name="content.opf"),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
        assert "content.opf" in names
        assert not [n for n in names if n.startswith("/")]

    def test_a_named_directory_still_works(self, legacy_epub, tmp_path):
        result = rebuild(
            legacy_epub,
            str(tmp_path / "oebps.epub"),
            Policy.preset("preserve", content_dir="OEBPS", package_name="content.opf"),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            assert "OEBPS/content.opf" in archive.namelist()

    @pytest.mark.parametrize(
        "directory, name",
        [("", "content.opf"), ("OEBPS", "content.opf"), ("EPUB", "package.opf")],
    )
    def test_the_container_points_at_wherever_it_went(self, legacy_epub, tmp_path, directory, name):
        result = rebuild(
            legacy_epub,
            str(tmp_path / f"{directory or 'root'}.epub"),
            Policy.preset("preserve", content_dir=directory, package_name=name),
        )
        with zipfile.ZipFile(result.output_path) as archive:
            container = etree.fromstring(archive.read("META-INF/container.xml"))
            declared = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            ).get("full-path")
            assert declared in archive.namelist(), declared


class TestNoManifestHrefClimbsOutOfItsOwnDirectory:
    """A container-only rebuild left every href pointing at `../OEBPS/…`.

    `content_dir` says where the package document goes; `reorganize_files` says
    where the resources go. In `minimal` the second is off and the first was
    not, so the package landed in `EPUB/` while the files it describes stayed in
    `OEBPS/` — seventy manifest entries each having to climb back out.

    EPUBCheck passes that without a word: the path never leaves the container,
    so it is legal. Readers are a different matter. `..` inside an archive is
    the shape of a zip-slip attack, and a reader that refuses it on sight
    refuses the entire book — which is how this was found, on a device that
    hung and died on a file with zero validation errors.
    """

    @staticmethod
    def _hrefs(archive: zipfile.ZipFile) -> list[str]:
        container = etree.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(
            ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
        ).get("full-path")
        package = etree.fromstring(archive.read(opf_path))
        return [
            item.get("href")
            for item in package.iter("{http://www.idpf.org/2007/opf}item")
        ]

    @pytest.mark.parametrize("preset", ["preserve", "strict", "minimal"])
    def test_no_href_contains_a_parent_step(self, legacy_epub, tmp_path, preset):
        result = rebuild(legacy_epub, str(tmp_path / f"{preset}.epub"), Policy.preset(preset))
        with zipfile.ZipFile(result.output_path) as archive:
            climbing = [href for href in self._hrefs(archive) if href.startswith("../")]
        assert climbing == [], climbing

    def test_a_container_only_rebuild_keeps_the_package_where_it_was(self, legacy_epub, tmp_path):
        result = rebuild(legacy_epub, str(tmp_path / "minimal.epub"), Policy.preset("minimal"))
        with zipfile.ZipFile(result.output_path) as archive:
            assert "OEBPS/content.opf" in archive.namelist()
        assert any(
            finding.rule == "package.layout-kept" for finding in result.report.findings
        ), result.report.to_text()

    def test_a_full_rebuild_still_uses_the_configured_directory(self, legacy_epub, tmp_path):
        """The fix must not reach past the case that needed it: when the files
        do move, the policy's layout is the one that applies."""
        result = rebuild(legacy_epub, str(tmp_path / "preserve.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            assert "EPUB/package.opf" in archive.namelist()
        assert not any(
            finding.rule == "package.layout-kept" for finding in result.report.findings
        )


class TestTheEmptyTitleTheUpgradeMadeIllegal:
    """Container-only mode was creating errors, not carrying them.

    A corpus run reported fourteen EPUBCheck errors introduced across thirteen
    books in the mode that promises to touch no content. Nobody could say which
    errors: the signatures held counts. Once they held EPUBCheck's message
    identifiers as well, all fourteen came back as `RSC-005`, and on the one
    book of that shape reachable from here, one sentence — *Element "title" must
    not be empty.*

    EPUB 2 allowed it. EPUB 3 does not, and this mode rebuilds the package as
    EPUB 3 around content it will not open, so the book was legal when it
    arrived and illegal when it left without a byte of its content changing.
    """

    def book(self, tmp_path, title_markup: str) -> str:
        from .factory import png_bytes, write_zip

        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Stara ksiazka</dc:title>
    <dc:identifier id="id">urn:uuid:0e4c2f16-6f5d-4a67-9a2c-91b0e2f5d833</dc:identifier>
    <dc:language>pl</dc:language>
  </metadata>
  <manifest>
    <item id="ch" href="Text/chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="Images/pic.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        chapter = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            f"<head>{title_markup}</head>\n"
            "<body><h1>Rozdzial pierwszy</h1><p>Tresc.</p></body>\n"
            "</html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "old.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/content.opf": package.encode(),
                "OEBPS/Text/chapter.xhtml": chapter.encode(),
                "OEBPS/Images/pic.png": png_bytes(),
            },
        )

    def forged(self, tmp_path, title_markup):
        source = self.book(tmp_path, title_markup)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("minimal"))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            return result, archive.read(name).decode("utf-8")

    def test_an_empty_title_is_filled_from_the_documents_own_heading(self, tmp_path):
        result, document = self.forged(tmp_path, "<title></title>")
        assert "<title>Rozdzial pierwszy</title>" in document
        assert "xhtml.title-filled" in {f.rule for f in result.report.findings}

    def test_a_self_closing_one_counts_as_empty(self, tmp_path):
        _, document = self.forged(tmp_path, "<title/>")
        assert "<title>Rozdzial pierwszy</title>" in document

    def test_whitespace_is_not_content(self, tmp_path):
        _, document = self.forged(tmp_path, "<title>   </title>")
        assert "<title>Rozdzial pierwszy</title>" in document

    def test_a_title_that_says_something_is_left_alone(self, tmp_path):
        """The promise still holds everywhere it can. Only the empty ones."""
        result, document = self.forged(tmp_path, "<title>Wlasny tytul</title>")
        assert "<title>Wlasny tytul</title>" in document
        assert "xhtml.title-filled" not in {f.rule for f in result.report.findings}

    def test_the_body_is_not_touched_by_it(self, tmp_path):
        """The edit is in the head, and the head is not rendered. If this ever
        reaches into the body the mode has stopped being what it claims."""
        _, document = self.forged(tmp_path, "<title></title>")
        body = document[document.index("<body") :]
        assert body.startswith("<body><h1>Rozdzial pierwszy</h1><p>Tresc.</p></body>")

    def test_an_svg_label_further_down_is_nobodys_business(self):
        """`<title>` inside SVG is a label on a shape and may legitimately hold
        nothing. Only the head window is considered."""
        from epubforge.xhtml import fill_empty_title

        data = (
            b'<html><head><title>Set</title></head><body>'
            + b"<p>x</p>" * 900
            + b"<svg><title></title></svg></body></html>"
        )
        assert fill_empty_title(data, "Nope") == (data, False)


class TestAPagePinnedToItsFootStaysThere:
    """`div.dol { position: absolute; bottom: 0; width: 100% }` — a real rule
    from a real book, `.dol` being Polish for "bottom", on a page whose whole
    content is a dedication.

    On the owner's reader that page came out **blank**: the block left the flow
    and pagination went round it. The first repair deleted the declaration,
    which made the page appear and moved the dedication to the top. His answer
    settled the design:

        Dla mnie reguła nie jest istotna tylko zachowanie wyglądu WIZUALNEGO
        tej strony w niezmienionej formie tak jak chciał wydawca.

    And this file's own first paragraph had said so all along: a construct that
    carries visual meaning is translated into the equivalent that renders the
    same way, never simply deleted. Deleting it was the tool breaking its own
    rule. `margin-top: auto` in a flex column puts a block at the foot of the
    page exactly as `bottom: 0` was meant to, and keeps it in the flow.
    """

    STYLE = "div.dol { position: absolute; bottom: 0; width: 100%; }\np { margin: 1em 0; }\n"

    def book(self, tmp_path, body: str, *, layout: str = "") -> str:
        from .factory import write_zip

        rendition = (
            f'<meta property="rendition:layout">{layout}</meta>' if layout else ""
        )
        package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"
         prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Dedykacja</dc:title>
    <dc:identifier id="id">urn:uuid:6d1f0b52-3a77-4c19-9f0e-1c8b7a3d2e45</dc:identifier>
    <dc:language>pl</dc:language>
    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
    {rendition}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ded" href="dedication.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
  </manifest>
  <spine><itemref idref="ded"/></spine>
</package>
"""
        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl"><head><title>Spis</title>'
            "</head><body><nav epub:type=\"toc\"><ol><li>"
            '<a href="dedication.xhtml">Dedykacja</a></li></ol></nav></body></html>\n'
        )
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            "<title>Dedykacja</title>"
            '<link rel="stylesheet" href="style.css"/></head>\n'
            f"<body>{body}</body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/dedication.xhtml": document.encode(),
                "OEBPS/style.css": self.STYLE.encode(),
            },
        )

    def forge(self, tmp_path, body, *, mode="preserve", layout=""):
        source = self.book(tmp_path, body, layout=layout)
        result = rebuild(source, str(tmp_path / f"out-{mode}.epub"), Policy.preset(mode))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("dedication.xhtml"))
            sheet = next(n for n in archive.namelist() if n.endswith(".css"))
            return result, archive.read(name).decode(), archive.read(sheet).decode()

    ONE_BLOCK = '<div class="dol"><p>Nie wspominaj grzechow mej mlodosci.</p></div>'

    def test_the_block_is_put_at_the_foot_of_the_page_in_the_flow(self, tmp_path):
        result, document, _ = self.forge(tmp_path, self.ONE_BLOCK)
        assert "margin-top: auto" in document
        assert "position: static" in document
        assert "display: flex" in document and "flex-direction: column" in document
        assert "xhtml.position-pinned-in-flow" in {f.rule for f in result.report.findings}

    def test_the_flex_column_never_reaches_the_rest_of_the_book(self, tmp_path):
        """Scoped into the one document, never into the shared stylesheet.
        Flexing every body in a book would stop adjacent margins collapsing on
        every page of it — a change to the whole book for one page."""
        _, _, sheet = self.forge(tmp_path, self.ONE_BLOCK)
        assert "display: flex" not in sheet
        assert "flex-direction" not in sheet

    def test_the_publishers_declaration_is_left_where_it_was(self, tmp_path):
        """Superseded, not deleted. The inline equivalent outranks it, and
        deleting from a shared sheet would reach documents nobody examined."""
        result, _, sheet = self.forge(tmp_path, self.ONE_BLOCK)
        assert "position: absolute" in sheet
        assert "css.position-superseded" in {f.rule for f in result.report.findings}

    def test_strict_translates_it_too_rather_than_deleting_it(self, tmp_path):
        """The translated form is conforming, so there is nothing for strict to
        win. Conformance and appearance stopped disagreeing here."""
        result, document, _ = self.forge(tmp_path, self.ONE_BLOCK, mode="strict")
        assert "margin-top: auto" in document
        assert "xhtml.position-pinned-in-flow" in {f.rule for f in result.report.findings}

    def test_an_offset_from_the_foot_is_carried_over_as_a_margin(self, tmp_path):
        """A block two ems clear of the foot was two ems clear on purpose."""
        self.STYLE = "div.dol { position: absolute; bottom: 2em; width: 100%; }\n"
        try:
            _, document, _ = self.forge(tmp_path, self.ONE_BLOCK)
        finally:
            del self.STYLE
        assert "margin-bottom: 2em" in document

    def test_a_page_with_siblings_is_not_touched(self, tmp_path):
        """With siblings, making the body a flex column would stop their
        margins collapsing — a repair changing the spacing of a page it was not
        called for. No faithful translation, so none is invented."""
        body = self.ONE_BLOCK + "<p>Cos jeszcze na tej stronie.</p>"
        result, document, _ = self.forge(tmp_path, body)
        assert "margin-top: auto" not in document
        assert "xhtml.position-pinned-in-flow" not in {f.rule for f in result.report.findings}
        assert "css.position-kept-reflowable" in {f.rule for f in result.report.findings}

    def test_a_block_pinned_between_top_and_bottom_is_not_translated(self, tmp_path):
        """Stretched between both edges is a different layout, and `margin-top:
        auto` is not what it means."""
        self.STYLE = "div.dol { position: absolute; top: 0; bottom: 0; }\n"
        try:
            result, document, _ = self.forge(tmp_path, self.ONE_BLOCK)
        finally:
            del self.STYLE
        assert "margin-top: auto" not in document
        assert "css.position-kept-reflowable" in {f.rule for f in result.report.findings}

    def test_a_fixed_layout_book_keeps_its_positioning_untouched(self, tmp_path):
        """There the viewport is declared, nothing paginates, and out-of-flow
        positioning is how the format works."""
        result, document, sheet = self.forge(
            tmp_path, self.ONE_BLOCK, layout="pre-paginated"
        )
        assert "margin-top: auto" not in document
        assert "position: absolute" in sheet
        assert "css.position-kept" in {f.rule for f in result.report.findings}


    def test_strict_takes_the_positioning_and_leaves_the_rest_of_the_rule(self, tmp_path):
        """Where no faithful translation exists, strict drops the declaration
        and only that: the width and the offset are the publisher's and stay.

        Its home used to be the shared legacy fixture, where nothing carries
        `class="dol"` — so the whole rule is unreachable and now goes for that
        reason instead, and the test would have kept passing while measuring
        something else entirely.
        """
        body = self.ONE_BLOCK + "<p>Cos jeszcze na tej stronie.</p>"
        _, _, sheet = self.forge(tmp_path, body, mode="strict")
        assert "position: absolute" not in sheet
        assert "width: 100%" in sheet


class TestPositioningHeldInsideItsOwnBox:
    """The precondition nobody had written down.

    The argument for touching `position: absolute` is a rendering argument: the
    block leaves the flow, pagination goes round it, and a real dedication page
    came out blank. That argument holds when the element's containing block is
    the page. Put the same declaration inside an ancestor the publisher
    positioned — a caption over a picture — and it cannot go anywhere: it is
    laid out against a box that is itself in the flow and travels with it.

    `--strict` deleted it anyway, which drops the caption below the image on
    every reader, including all the ones where it was fine. Nothing was broken
    and the repair broke it.
    """

    STYLE = (
        ".okladka { position: relative; }\n"
        ".podpis { position: absolute; bottom: 8px; left: 0; width: 100%; }\n"
    )
    BODY = (
        '<div class="okladka"><img src="obraz.png" alt="obraz"/>'
        '<p class="podpis">Podpis na obrazku</p></div>'
        "<p>Zwykly akapit, zeby div nie byl jedynym dzieckiem body.</p>"
    )

    def book(self, tmp_path, style, body):
        from tests.factory import png_bytes, write_zip

        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Podpis</dc:title><dc:language>pl</dc:language>
    <dc:identifier id="pub-id">urn:uuid:6b1d0f6e-0000-4000-8000-0000000000aa</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="doc" href="doc.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="img" href="obraz.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="doc"/></spine>
</package>
"""
        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" lang="pl"><head><title>Spis</title>'
            '</head><body><nav epub:type="toc"><ol><li>'
            '<a href="doc.xhtml">Strona</a></li></ol></nav></body></html>\n'
        )
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            "<title>Strona</title>"
            '<link rel="stylesheet" href="style.css"/></head>\n'
            f"<body>{body}</body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/doc.xhtml": document.encode(),
                "OEBPS/style.css": style.encode(),
                "OEBPS/obraz.png": png_bytes(),
            },
        )

    def forge(self, tmp_path, *, mode="strict", style=None, body=None):
        source = self.book(tmp_path, style or self.STYLE, body or self.BODY)
        result = rebuild(source, str(tmp_path / f"out-{mode}.epub"), Policy.preset(mode))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            sheet = next(n for n in archive.namelist() if n.endswith(".css"))
            return result, archive.read(sheet).decode()

    def test_strict_no_longer_deletes_a_caption_that_cannot_escape(self, tmp_path):
        result, sheet = self.forge(tmp_path)
        assert "position: absolute" in sheet
        assert "css.position-removed" not in {f.rule for f in result.report.findings}

    def test_it_says_why_it_kept_it(self, tmp_path):
        result, _ = self.forge(tmp_path)
        found = [f for f in result.report.findings if f.rule == "css.position-contained"]
        assert found and found[0].level is Level.PRESERVED

    def test_an_uncontained_block_is_still_removed_under_strict(self, tmp_path):
        """The guard is about containment, not about the word `absolute`. A
        block whose containing block really is the page still goes."""
        style = ".podpis { position: absolute; bottom: 8px; width: 100%; }\n"
        result, sheet = self.forge(tmp_path, style=style)
        assert "position: absolute" not in sheet
        assert "css.position-removed" in {f.rule for f in result.report.findings}

    def test_fixed_is_not_held_by_a_positioned_ancestor(self, tmp_path):
        """`position: fixed` resolves against the viewport, so `position:
        relative` on an ancestor is not its containing block and promises it
        nothing. Reading the two as the same thing would keep a declaration
        that genuinely does leave the page."""
        style = (
            ".okladka { position: relative; }\n"
            ".podpis { position: fixed; bottom: 8px; width: 100%; }\n"
        )
        result, sheet = self.forge(tmp_path, style=style)
        assert "position: fixed" not in sheet
        assert "css.position-removed" in {f.rule for f in result.report.findings}

    def test_an_inline_style_counts_as_a_positioned_ancestor(self, tmp_path):
        """Publishers write it both ways, and a wrapper positioned inline holds
        its children exactly as one positioned in the sheet does."""
        body = (
            '<div style="position: relative"><img src="obraz.png" alt="obraz"/>'
            '<p class="podpis">Podpis na obrazku</p></div>'
            "<p>Zwykly akapit.</p>"
        )
        style = ".podpis { position: absolute; bottom: 8px; }\n"
        result, sheet = self.forge(tmp_path, style=style, body=body)
        assert "position: absolute" in sheet
        assert "css.position-contained" in {f.rule for f in result.report.findings}


class TestWhatContainerOnlyModeCannotReach:
    """The mode edits the head and nothing else, so markup that XHTML 1.1
    allowed and EPUB 3 forbids stays — and the output is invalid through no
    fault of the content.

    Found by the corpus: eleven books gaining exactly one `RSC-005` each, and on
    the shelf reachable from here the sentence behind it was always
    *value of attribute "width" is invalid; must be an integer* — `<img
    width="50%">`. Checked against six real books: six warnings, six EPUBCheck
    errors, and the construct named in the warning matched the validator's
    message every time.

    Saying so is the whole feature. Without it a reader runs a validator, gets a
    schema complaint, and has no way to learn that the answer is "use another
    mode".
    """

    def forge(self, tmp_path, markup: str, mode: str = "minimal", head: str = ""):
        from .factory import png_bytes, write_zip

        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Stara ksiazka</dc:title>
    <dc:identifier id="id">urn:uuid:5f2b8c14-6d3a-4e91-8c07-2b6d9f1a3e47</dc:identifier>
    <dc:language>pl</dc:language>
  </metadata>
  <manifest>
    <item id="ch" href="Text/chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="Images/pic.png" media-type="image/png"/>
  </manifest>
  <spine><itemref idref="ch"/></spine>
</package>
"""
        chapter = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Rozdzial</title>'
            f"{head}</head>\n"
            f"<body><p>Tresc.</p>{markup}</body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        source = write_zip(
            str(tmp_path / "old.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/content.opf": package.encode(),
                "OEBPS/Text/chapter.xhtml": chapter.encode(),
                "OEBPS/Images/pic.png": png_bytes(),
            },
        )
        result = rebuild(source, str(tmp_path / f"out-{mode}.epub"), Policy.preset(mode))
        assert result.output_path, result.report.to_text()
        return result

    def finding(self, result):
        return next(
            (f for f in result.report.findings if f.rule == "xhtml.epub2-only-markup"),
            None,
        )

    def test_a_percentage_width_is_named(self, tmp_path):
        result = self.forge(tmp_path, '<img src="../Images/pic.png" alt="" width="50%"/>')
        found = self.finding(result)
        assert found is not None
        assert "img[width]" in found.values["what"]

    def test_a_percentage_height_too(self, tmp_path):
        result = self.forge(tmp_path, '<img src="../Images/pic.png" alt="" height="30%"/>')
        assert "img[height]" in self.finding(result).values["what"]

    def test_a_plain_pixel_count_is_fine(self, tmp_path):
        """HTML5 wants an integer, and an integer is what this is."""
        result = self.forge(tmp_path, '<img src="../Images/pic.png" alt="" width="600"/>')
        assert self.finding(result) is None

    def test_it_says_nothing_when_there_is_nothing_to_say(self, tmp_path):
        result = self.forge(tmp_path, '<img src="../Images/pic.png" alt=""/>')
        assert self.finding(result) is None

    def test_the_modes_that_open_documents_do_not_warn(self, tmp_path):
        """They fix it — the attribute becomes CSS and renders the same — so a
        warning there would be telling somebody about a problem they no longer
        have."""
        result = self.forge(
            tmp_path, '<img src="../Images/pic.png" alt="" width="50%"/>', mode="preserve"
        )
        assert self.finding(result) is None

    def test_it_is_a_warning_and_not_an_error(self, tmp_path):
        """Nothing went wrong here. The book is what it is and the mode did what
        it promised; this is the sentence that connects the two."""
        result = self.forge(tmp_path, '<img src="../Images/pic.png" alt="" width="50%"/>')
        assert self.finding(result).level is Level.WARN

    # ---------------------------------------------------------- EF-045
    #
    # The fourth shape, and the first one that does not need the document to be
    # read to matter. Three books of the owner's 67 were counted as errors this
    # program had introduced, and none of them was: raising the package to
    # EPUB 3 changes which rules the validator applies to documents this mode
    # never opened, and the encoding declaration is the construct that notices.

    ENCODING_META = (
        '<meta http-equiv="Content-Type" '
        'content="application/xhtml+xml; charset=utf-8"/>'
    )

    def test_the_old_encoding_declaration_is_named(self, tmp_path):
        result = self.forge(tmp_path, "", head=self.ENCODING_META)
        found = self.finding(result)
        assert found is not None, "trzy ksiazki z kolekcji 67 mialy dokladnie to"
        assert "meta[http-equiv]" in found.values["what"]

    def test_the_declaration_epub3_wants_is_left_alone(self, tmp_path):
        result = self.forge(
            tmp_path,
            "",
            head='<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>',
        )
        assert self.finding(result) is None

    def test_spacing_and_case_are_the_authors_business(self, tmp_path):
        """`Content-Type` against `content-type`, and a semicolon with or
        without a space, are the same declaration. Warning about them would be
        warning about nothing."""
        result = self.forge(
            tmp_path,
            "",
            head='<meta http-equiv="content-type" content="TEXT/HTML;charset=UTF-8"/>',
        )
        assert self.finding(result) is None

    def test_a_title_behind_a_wall_of_word_junk_is_still_filled(self, tmp_path):
        """EF-053, i przyczyna jest zabawna dokładnie do chwili, w której kosztuje.

        Wypełnianie pustego `<title>` szukało go w pierwszych 4096 bajtach —
        liczbie wziętej z rozsądku i niezmierzonej na niczym. Na kolekcji
        właściciela siedzi książka wyeksportowana z Worda: jej `<head>` niesie
        **91 486 bajtów** komentarzy warunkowych `<!--[if gte mso 9]>`,
        a `<title>` zaczyna się na bajcie 91 469. Dwanaście dokumentów,
        dwanaście pustych tytułów, i naprawa istniejąca dokładnie na to nie
        zobaczyła ani jednego — więc tryb kontenerowy produkował na tej książce
        `RSC-005: Element "title" must not be empty`.

        Granicą jest teraz `</head>`, a to nie jest zgadywanie: tytuł przed nim
        jest tytułem dokumentu, tytuł za nim należy do czegoś osadzonego.
        """
        from epubforge import xhtml

        smiec = b"<!--[if gte mso 9]><xml><o:shapedefaults/></xml><![endif]-->" * 200
        assert len(smiec) > 4096, "atrapa przestala byc dluzsza niz stare okno"
        dokument = (
            b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            + smiec
            + b"<title></title></head><body><p>Tresc.</p></body></html>"
        )
        wynik, wypelnione = xhtml.fill_empty_title(dokument, "Rozdzial")
        assert wypelnione, "tytul za smieciem Worda znowu jest niewidoczny"
        assert b"<title>Rozdzial</title>" in wynik

    def test_a_title_past_the_head_is_left_alone(self, tmp_path):
        """Druga strona tej samej granicy, bo bez niej poprawka byłaby
        rozszerzeniem zasięgu, a nie jego wyprostowaniem: `<title>` wewnątrz
        SVG w treści jest etykietą kształtu i nie jest niczyją sprawą."""
        from epubforge import xhtml

        dokument = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            b"<title>Ma tytul</title></head><body>"
            b"<svg><title></title><rect/></svg></body></html>"
        )
        wynik, wypelnione = xhtml.fill_empty_title(dokument, "Nie tykaj")
        assert not wypelnione
        assert b"Nie tykaj" not in wynik

    def test_a_named_meta_without_content_is_named(self, tmp_path):
        """EF-053, kształt drugi. Dwie książki kolekcji niosą w głowie
        breadcrumb DRM-u Adobe zapisany jako `value` zamiast `content` —
        i kosztuje to **dwa** błędy pod nowymi regułami, nie jeden."""
        result = self.forge(
            tmp_path,
            "",
            head='<meta name="Adept.resource" value="urn:uuid:abc"/>',
        )
        found = self.finding(result)
        assert found is not None
        assert "meta[content]" in found.values["what"]

    def test_a_meta_that_has_its_content_is_fine(self, tmp_path):
        result = self.forge(
            tmp_path, "", head='<meta name="generator" content="cokolwiek"/>'
        )
        assert self.finding(result) is None

    def test_the_mode_that_opens_documents_really_does_fix_it(self, tmp_path):
        """The whole point of naming it is the advice at the end: *use another
        mode*. So this reads the other mode's **output**, rather than settling
        for the absence of a warning — the warning is only raised in
        container-only mode, so its absence here would prove nothing at all.
        A wrong instruction is worse than none."""
        import zipfile

        result = self.forge(tmp_path, "", mode="preserve", head=self.ENCODING_META)
        assert self.finding(result) is None
        with zipfile.ZipFile(result.output_path) as archive:
            chapter = next(
                archive.read(name)
                for name in archive.namelist()
                if name.endswith("chapter.xhtml")
            ).decode("utf-8")
        assert "application/xhtml+xml; charset=utf-8" not in chapter, chapter


class TestADeclaredLanguageTheTextContradicts:
    """Found on a real library of 2 200 books: 2 187 declared `en` and 1 815 of
    those carried `„`, a mark English typesetting does not use. Calibre had
    left `dc:language` at its default and nothing had ever looked.

    It is not a typographic nicety. A reading system speaks `dc:language` to its
    text-to-speech engine and hyphenates by it.
    """

    def book(self, tmp_path, language, body):
        from tests.factory import write_zip

        package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Proba</dc:title><dc:language>{language}</dc:language>
    <dc:identifier id="pub-id">urn:uuid:6b1d0f6e-0000-4000-8000-0000000000bb</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="doc" href="doc.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="doc"/></spine>
</package>
"""
        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Spis</title>'
            '</head><body><nav epub:type="toc"><ol><li>'
            '<a href="doc.xhtml">Strona</a></li></ol></nav></body></html>\n'
        )
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Strona</title>'
            f"</head><body>{body}</body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / "in.epub"),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/nav.xhtml": nav.encode(),
                "OEBPS/doc.xhtml": document.encode(),
            },
        )

    # Ordinary prose, not a pangram. A diacritic-dense fixture scores three
    # hundred Polish-only letters per thousand where a real Polish novel scores
    # about seventy, so a test written on one proves nothing about the floor —
    # every ratio passes.
    POLISH = (
        "<p>Wieczorem wrócił do domu i usiadł przy oknie. Na dworze padało, "
        "a on patrzył w ciemność, jakby czegoś tam szukał. Nie umiał "
        "powiedzieć, co go trzyma w tym mieście od tylu lat.</p>"
    ) * 12
    ENGLISH = (
        "<p>In the evening he came home and sat down by the window. It was "
        "raining outside, and he looked into the darkness as if searching for "
        "something there. He could not say what kept him here.</p>"
    ) * 12

    def rules_of(self, tmp_path, language, body, name):
        source = self.book(tmp_path, language, body)
        result = rebuild(source, str(tmp_path / f"{name}.epub"), Policy.preset("preserve"))
        assert result.output_path, result.report.to_text()
        return result, {f.rule for f in result.report.findings}

    def test_polish_text_declaring_english_is_corrected(self, tmp_path):
        result, rules = self.rules_of(tmp_path, "en", self.POLISH, "a")
        assert "metadata.language-corrected" in rules
        with zipfile.ZipFile(result.output_path) as archive:
            package = archive.read(OPF_PATH).decode()
        assert ">pl<" in package.replace(" ", "")

    def test_it_is_a_fix_because_the_declaration_was_simply_wrong(self, tmp_path):
        result, _ = self.rules_of(tmp_path, "en", self.POLISH, "b")
        found = [f for f in result.report.findings if f.rule == "metadata.language-corrected"]
        assert found and found[0].level is Level.FIX

    def test_english_text_declaring_english_is_left_alone(self, tmp_path):
        _, rules = self.rules_of(tmp_path, "en", self.ENGLISH, "c")
        assert "metadata.language-corrected" not in rules

    def test_polish_text_declaring_polish_says_nothing(self, tmp_path):
        _, rules = self.rules_of(tmp_path, "pl", self.POLISH, "d")
        assert "metadata.language-corrected" not in rules

    def test_a_caption_is_not_enough_text_to_judge_a_language(self, tmp_path):
        """The floor, and it is here because of a real false positive: a
        Japanese manga was reported as Polish, on the strength of the
        navigation page this tool had just generated — whose title is "Spis
        treści" in a Polish report, one `ś` in seventeen characters."""
        _, rules = self.rules_of(tmp_path, "ja", "<p>Zażółć</p>", "f")
        assert "metadata.language-corrected" not in rules

    def test_a_bilingual_book_is_not_relabelled(self, tmp_path):
        """The floor is "more than half the book", not "some Polish in it".

        Real Polish prose runs about 69 Polish-only letters per thousand
        characters. The first floor was 5 — a book roughly 7% Polish — and an
        English novel carrying one Polish quotation scores 4.4, so two of them
        would have had the book relabelled.
        """
        body = self.POLISH * 2 + self.ENGLISH * 3
        _, rules = self.rules_of(tmp_path, "en", body, "g")
        assert "metadata.language-corrected" not in rules

    def test_an_explicit_language_still_wins(self, tmp_path):
        """The overrides are applied after the correction, so somebody who says
        what the language is gets what they said."""
        source = self.book(tmp_path, "en", self.POLISH)
        policy = Policy.preset("preserve")
        policy.metadata_overrides["language"] = "cs"
        result = rebuild(source, str(tmp_path / "override.epub"), policy)
        with zipfile.ZipFile(result.output_path) as archive:
            package = archive.read(OPF_PATH).decode()
        assert ">cs<" in package.replace(" ", "")


class TestWhatADutchAndEnglishShelfFound:
    """Sixty-seven books out of Sigil, Word and Calibre, in languages the tool
    had never been measured on, produced 120 EPUBCheck errors in the modes that
    open documents — against zero on the Polish shelf. Two shapes accounted for
    fifty-eight of them and both were ours.
    """

    def build(self, tmp_path, body, head="", name="in.epub"):
        from tests.factory import write_zip

        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Proba</dc:title><dc:language>nl</dc:language>
    <dc:identifier id="pub-id">urn:uuid:6b1d0f6e-0000-4000-8000-0000000000dd</dc:identifier>
  </metadata>
  <manifest>
    <item id="doc" href="doc.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="doc"/></spine>
</package>
"""
        ncx = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            "<head/><docTitle><text>Proba</text></docTitle><navMap>"
            '<navPoint id="n1" playOrder="1"><navLabel><text>Strona</text></navLabel>'
            '<content src="doc.xhtml"/></navPoint></navMap></ncx>\n'
        )
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Strona</title>'
            f"{head}</head>{body}</html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / name),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/doc.xhtml": document.encode(),
                "OEBPS/toc.ncx": ncx.encode(),
            },
        )

    def forge(self, tmp_path, body, head="", name="out"):
        source = self.build(tmp_path, body, head, name=f"{name}-in.epub")
        result = rebuild(source, str(tmp_path / f"{name}.epub"), Policy.preset("preserve"))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            path = next(n for n in archive.namelist() if n.endswith("doc.xhtml"))
            return result, archive.read(path).decode()

    def test_the_body_palette_becomes_css_or_goes(self, tmp_path):
        """`bgcolor` was translated from the start and these four were not."""
        body = ('<body text="#101010" link="#0000ff" vlink="#800080" '
                'alink="#ff0000"><p>Tekst</p></body>')
        _, html = self.forge(tmp_path, body, name="a")
        assert "color: #101010" in html
        for attribute in ("text=", "link=", "vlink=", "alink="):
            assert attribute not in html

    def test_a_link_colour_is_dropped_rather_than_invented(self, tmp_path):
        """CSS says link colours with pseudo-classes and an inline style cannot
        hold one. Writing `a:link` into a shared stylesheet would reach
        documents nobody looked at."""
        body = '<body link="#0000ff"><p>Tekst</p></body>'
        _, html = self.forge(tmp_path, body, name="b")
        assert "a:link" not in html

    def test_a_coloured_table_border_becomes_a_border_colour(self, tmp_path):
        body = '<body><table bordercolor="#cccccc"><tr><td>x</td></tr></table></body>'
        _, html = self.forge(tmp_path, body, name="c")
        assert "border-color: #cccccc" in html
        assert "bordercolor" not in html

    def test_a_link_target_goes_because_an_epub_has_no_windows(self, tmp_path):
        body = '<body><p><a href="doc.xhtml" target="_blank">tu</a></p></body>'
        _, html = self.forge(tmp_path, body, name="d")
        assert "target=" not in html
        assert 'href="' in html

    def test_value_on_something_that_is_not_a_list_item_goes(self, tmp_path):
        body = '<body><p value="3">Tekst</p></body>'
        _, html = self.forge(tmp_path, body, name="e")
        assert "value=" not in html

    def test_value_on_an_ordered_list_item_stays(self, tmp_path):
        """There it numbers the item, which is what it is for."""
        body = '<body><ol><li value="7">Siedem</li></ol></body>'
        _, html = self.forge(tmp_path, body, name="f")
        assert 'value="7"' in html

    def test_a_meta_with_a_name_and_no_content_is_completed(self, tmp_path):
        """HTML requires the pair and EPUBCheck refuses the document without
        it. Completed rather than removed: the publisher named something, and
        dropping the element would throw the name away too."""
        head = '<meta name="generator"/>'
        _, html = self.forge(tmp_path, "<body><p>x</p></body>", head, name="g")
        assert 'name="generator"' in html
        assert 'content=""' in html


class TestAFontStackGetsTheFamilyTheFontDeclares:
    """Calibre calls a stack with no generic family an error and it is right:
    when the embedded font fails to load — and on an e-reader it often does —
    the reader falls back to whatever it likes. This tool reported it and left
    it alone because picking serif or sans-serif from a *name* is guesswork.
    Wherever the book embeds the font, it is not."""

    def build(self, tmp_path, css, font=None, name="in.epub"):
        import glob as _glob
        import pathlib as _pathlib

        from tests.factory import write_zip

        if font is None:
            found = {
                _pathlib.Path(p).name: p
                for p in _glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
            }
            for candidate in ("DejaVuSerif.ttf", "DejaVuSans.ttf"):
                if candidate in found:
                    font = _pathlib.Path(found[candidate]).read_bytes()
                    break
        package = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Proba</dc:title><dc:language>pl</dc:language>
    <dc:identifier id="pub-id">urn:uuid:6b1d0f6e-0000-4000-8000-0000000000ee</dc:identifier>
  </metadata>
  <manifest>
    <item id="doc" href="doc.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="s.css" media-type="text/css"/>
    <item id="f" href="f.ttf" media-type="font/ttf"/>
  </manifest>
  <spine><itemref idref="doc"/></spine>
</package>
"""
        document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>S</title>'
            '<link rel="stylesheet" href="s.css"/></head>'
            "<body><p>Tekst</p></body></html>\n"
        )
        container = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/package.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>\n'
        )
        return write_zip(
            str(tmp_path / name),
            {
                "META-INF/container.xml": container.encode(),
                "OEBPS/package.opf": package.encode(),
                "OEBPS/doc.xhtml": document.encode(),
                "OEBPS/s.css": css.encode(),
                "OEBPS/f.ttf": font or b"",
            },
        )

    def forge(self, tmp_path, css, font=None, name="out"):
        source = self.build(tmp_path, css, font, name=f"{name}-in.epub")
        result = rebuild(source, str(tmp_path / f"{name}.epub"), Policy.preset("preserve"))
        assert result.output_path, result.report.to_text()
        with zipfile.ZipFile(result.output_path) as archive:
            sheet = next(n for n in archive.namelist() if n.endswith(".css"))
            return result, archive.read(sheet).decode()

    EMBEDDED = (
        '@font-face { font-family: "Ksiazkowa"; src: url("f.ttf"); }\n'
        "p { font-family: Ksiazkowa; }\n"
    )

    def test_the_stack_gains_what_the_font_says_about_itself(self, tmp_path):
        import glob as _glob

        if not _glob.glob("/usr/share/fonts/**/DejaVu*.ttf", recursive=True):
            pytest.skip("no system font to embed")
        result, sheet = self.forge(tmp_path, self.EMBEDDED, name="a")
        body = sheet.split("@font-face")[-1]
        assert "serif" in body
        assert "css.font-stack-generic-added" in {f.rule for f in result.report.findings}

    def test_the_font_face_rule_itself_is_not_touched(self, tmp_path):
        """A declaration inside @font-face names a font, it does not build a
        stack, and appending a generic family there would be nonsense."""
        import glob as _glob

        if not _glob.glob("/usr/share/fonts/**/DejaVu*.ttf", recursive=True):
            pytest.skip("no system font to embed")
        _, sheet = self.forge(tmp_path, self.EMBEDDED, name="b")
        face = sheet[sheet.index("@font-face"):sheet.index("}", sheet.index("@font-face"))]
        assert "serif" not in face

    def test_a_font_the_book_does_not_embed_is_still_only_reported(self, tmp_path):
        """Then it really would be a guess, and the finding stays what it was."""
        css = "p { font-family: Garamond; }\n"
        result, sheet = self.forge(tmp_path, css, font=b"", name="c")
        assert "serif" not in sheet
        rules = {f.rule for f in result.report.findings}
        assert "css.font-stack-generic-missing" in rules
        assert "css.font-stack-generic-added" not in rules

    def test_a_stack_that_already_ends_in_a_generic_is_left_alone(self, tmp_path):
        css = "p { font-family: Ksiazkowa, serif; }\n"
        _, sheet = self.forge(tmp_path, css, font=b"", name="d")
        assert sheet.count("serif") == 1
