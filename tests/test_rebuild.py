"""End-to-end checks on the rebuilt container."""

from __future__ import annotations

import zipfile

from lxml import etree

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
        assert "EPUB/images/okadka.png" in archive.namelist()

    def test_cover_image_carries_the_manifest_property(self, archive):
        package = opf_tree(archive)
        covers = package.xpath(
            './/opf:item[contains(@properties, "cover-image")]', namespaces=OPF_NS
        )
        assert len(covers) == 1
        assert covers[0].get("href") == "images/okadka.png"

    def test_legacy_cover_meta_is_kept_for_old_readers(self, archive):
        package = opf_tree(archive)
        meta = package.xpath('.//opf:meta[@name="cover"]', namespaces=OPF_NS)
        assert meta and meta[0].get("content")

    def test_obfuscated_font_is_recovered_and_encryption_dropped(self, archive):
        assert "META-INF/encryption.xml" not in archive.namelist()
        font = archive.read("EPUB/fonts/moja.ttf")
        assert font.startswith(b"\x00\x01\x00\x00"), "font was not deobfuscated"

    def test_unreferenced_files_and_junk_are_removed(self, archive):
        names = archive.namelist()
        assert not any("nieuzywany" in name for name in names)
        assert not any(".DS_Store" in name for name in names)


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

    def test_out_of_flow_positioning_is_removed_from_reflowable_books(self, rebuilt):
        css = self.stylesheet(rebuilt)
        assert "position: absolute" not in css
        # Only the positioning goes; the rest of the rule is left alone.
        assert "width: 100%" in css
        assert "text-align: center" in css

    def test_removal_is_reported(self, rebuilt):
        assert any(
            "absolute/fixed position" in f.message
            for f in rebuilt.report.findings
            if f.level is Level.FIX
        )

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
