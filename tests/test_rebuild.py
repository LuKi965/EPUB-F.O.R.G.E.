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
        assert "deco.webp" not in css
        assert "deco.png" in css
        assert "../fonts/moja.ttf" in css

    def test_toc_entries_pointing_nowhere_are_dropped(self, rebuilt):
        nav = [
            f for f in rebuilt.report.findings
            if f.stage == "navigation" and "pointing nowhere" in f.message
        ]
        assert nav


class TestAssets:
    def test_webp_is_transcoded_to_png(self, archive):
        names = archive.namelist()
        assert not any(name.endswith(".webp") for name in names)
        assert "EPUB/images/deco.png" in names

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
        assert any("not present in the book" in f.message for f in preserved)

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

    def messages(self, rebuilt, level: Level) -> list[str]:
        return [f.message for f in rebuilt.report.findings if f.level is level]

    def test_version_upgrade_is_reported(self, rebuilt):
        assert any(
            "EPUB 2.0 to EPUB 3.3" in message for message in self.messages(rebuilt, Level.FIX)
        )

    def test_file_reorganisation_is_reported_as_a_change(self, rebuilt):
        assert any("reorganised" in message for message in self.messages(rebuilt, Level.FIX))

    def test_generated_navigation_is_reported_as_a_fix(self, rebuilt):
        assert any(
            "navigation document" in message for message in self.messages(rebuilt, Level.FIX)
        )

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

    def test_out_of_flow_positioning_is_kept_by_default(self, rebuilt):
        """A publisher pinning content to the page foot is intent, not a defect."""
        assert "position: absolute" in self.stylesheet(rebuilt)
        assert any(
            f.level is Level.PRESERVED and "absolute/fixed position" in f.message
            for f in rebuilt.report.findings
        )

    def test_strict_removes_out_of_flow_positioning(self, rebuilt_strict):
        css = self.stylesheet(rebuilt_strict)
        assert "position: absolute" not in css
        # Only the positioning goes; the rest of the rule is left alone.
        assert "width: 100%" in css
        assert "text-align: center" in css

    def test_fixed_layout_books_keep_their_positioning(self, legacy_epub, tmp_path):
        """Absolute positioning is how fixed-layout books work; never strip it."""
        from epubforge.pipeline import rebuild
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
            "contain block-level content" in f.message
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

    def test_consolidation_can_be_switched_off(self, legacy_epub, tmp_path):
        from epubforge.pipeline import rebuild as run
        from epubforge.policy import Policy

        policy = Policy.preset("preserve")
        policy.normalize_watermarks = False
        result = run(legacy_epub, str(tmp_path / "kept.epub"), policy)
        with zipfile.ZipFile(result.output_path) as archive:
            html = archive.read("EPUB/text/0001-chapter2.xhtml").decode()
        assert "font-size:1px !important" in html
        assert "epubforge-watermark" not in html


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
            "Geralt walczy z wiedźminem",
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
    """The mode's whole promise, with the one exception written down.

    Parsing and reserialising would break it, so documents are not opened. The
    DOCTYPE is replaced on the bytes, because a legacy one makes the output an
    invalid EPUB 3 and a DOCTYPE says nothing about how a page renders — the
    one edit that cannot change what the reader sees. Everything else is
    identical, and this asserts that by comparing with the DOCTYPE normalised
    on both sides rather than by relaxing the comparison.
    """
    from epubforge.xhtml import modernise_doctype

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
        import re

        source = self.build(tmp_path, sheet=sheet)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("chapter.xhtml"))
            html = archive.read(name).decode()
        return re.search(r"<img[^>]*>", html).group(), result

    def test_an_unsized_cover_is_given_limits(self, tmp_path):
        markup, result = self.cover_markup(tmp_path, sheet=None)
        assert "max-width: 100%" in markup and "max-height: 100%" in markup
        assert any("page-fitting" in f.message for f in result.report.findings)

    def test_a_cover_the_publisher_sized_is_left_alone(self, tmp_path):
        markup, result = self.cover_markup(
            tmp_path, sheet="img { max-height: 98%; max-width: 100%; }"
        )
        assert "style=" not in markup
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

    def test_only_one_image_is_touched(self, tmp_path):
        """Only the cover. An illustration mid-chapter is a different question,
        and the cover page this tool generates already sizes its own."""
        import re

        source = self.build(tmp_path, sheet=None)
        result = rebuild(source, str(tmp_path / "out.epub"), Policy.preset("preserve"))
        with zipfile.ZipFile(result.output_path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".xhtml")]
            markup = "".join(archive.read(n).decode() for n in names)
        styled = [tag for tag in re.findall(r"<img[^>]*>", markup) if "style=" in tag]
        assert len(styled) == 1, styled


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

    def test_the_rebuild_reports_it(self, legacy_epub, tmp_path):
        result = rebuild(legacy_epub, str(tmp_path / "out.epub"), Policy.preset("minimal"))
        assert any("DOCTYPE" in f.message for f in result.report.findings), [
            f.message for f in result.report.findings
        ]
