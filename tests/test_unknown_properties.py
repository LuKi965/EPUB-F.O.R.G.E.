"""Pillar A of the 0.4 plan, first slice: properties CSS does not have.

The lint baseline over the whole shelf (41 997 findings) is 87% one thing:
declarations of properties that do not exist in CSS — Word's `mso-*` inside
`@font-face`, thousands per book. Every conforming parser drops such a
declaration before any reader sees it, which is the same argument the `=`
declarations rest on; the difference the owner asked for in pillar A is that
the conclusion is now drawn — removed in both modes, behind the sweep's
opt-out — instead of counted and kept. The authority is deliberately the
gate's own: `KNOWN_PROPERTIES` is the dataset stylelint's
`property-no-unknown` reads. The second, smaller slice is the `<!-- -->`
comment shield around `<style>` content, which was 312 of the baseline's
314 parse errors.
"""

from __future__ import annotations

from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of
from tests.test_class_translation import PAGE, sheet_of

BODY = (
    '<h2 class="rozdz">Nagłówek</h2>'
    '<p class="tresc">Akapit z treścią rozdziału.</p>'
)

#: The measured shape: Word's font plumbing beside real declarations, and a
#: vendor-prefixed property a real reader honours.
SHEET = (
    '@font-face { font-family: "Charis"; src: url(F.ttf); '
    "mso-font-charset: 0; mso-font-pitch: variable; } "
    "h2.rozdz { font-size: 1.1em; mso-fareast-font-family: Calibri; margin: 1em 0; } "
    "p.tresc { margin: 0; -epub-hyphens: auto; text-indent: 1.2em; line-height: 1.4; }"
)


def build(tmp_path, *, sheet=SHEET, preset="preserve", sweep=None):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=BODY)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>'
        '<item id="f" href="F.ttf" media-type="font/ttf"/>',
        extra_files={"OEBPS/s.css": sheet.encode(), "OEBPS/F.ttf": b"\x00\x01\x00\x00"},
    )
    policy = Policy.preset(preset, render_gate="off")
    if sweep is not None:
        policy.sweep_style_blocks = sweep
    return rebuild(source, str(tmp_path / "out.epub"), policy)


class TestTheConclusionIsDrawn:
    def test_unknown_properties_go_in_both_modes(self, tmp_path):
        """Pillar A's line: the safety is the analysis (no parser knows the
        name) plus the render gate — not the mode. The mutation that gates
        this back to strict-only fails on the preserve half."""
        for preset in ("preserve", "strict"):
            result = build(tmp_path, preset=preset)
            assert result.status.wrote_a_file, result.report.to_text()
            sheet = sheet_of(result)
            assert "mso-" not in sheet, preset
            assert "css.unknown-properties-removed" in rules_of(result)

    def test_what_a_reader_honours_survives(self, tmp_path):
        """`-epub-hyphens` is honoured by real reading systems; `panose-1` is
        the CSS 2.1 font descriptor Calibre writes and suppresses in its own
        lint. And `-czytnik-page-mode` — an invented prefix standing for the
        class no catalogue can enumerate, a reader's private property — is
        the load-bearing case: the guard never judges a prefixed name, listed
        or not, because the catalogue knows 523 prefixes and cannot know
        tomorrow's. The mutation that judges prefixed names fails here."""
        sheet = SHEET.replace(
            "src: url(F.ttf);", "src: url(F.ttf); panose-1: 2 4 5;"
        ).replace(
            "-epub-hyphens: auto;", "-epub-hyphens: auto; -czytnik-page-mode: pan;"
        )
        result = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert "-epub-hyphens: auto" in out
        assert "-czytnik-page-mode: pan" in out
        assert "panose-1: 2 4 5" in out

    def test_the_healthy_neighbours_are_untouched(self, tmp_path):
        out = sheet_of(build(tmp_path))
        assert "font-size: 1.1em" in out and "margin: 1em 0" in out
        assert 'font-family: "Charis"' in out and "src:" in out

    def test_the_opt_out_counts_instead(self, tmp_path):
        """`--keep-style-junk` reaches this removal like every other (S-02)."""
        result = build(tmp_path, sweep=False)
        assert "mso-font-charset" in sheet_of(result)
        assert "css.unknown-properties-found" in rules_of(result)
        assert "css.unknown-properties-removed" not in rules_of(result)

    def test_a_rule_emptied_whole_goes_whole(self, tmp_path):
        """A rule reduced to `{}` by the removal would only trade one lint
        finding for another (`block-no-empty`) — same rule as the plumbing."""
        sheet = SHEET + " p.pusty { mso-only-thing: yes; }"
        body = BODY + '<p class="pusty">Jeszcze akapit.</p>'
        source = make_book(
            tmp_path / "in2.epub",
            {"c0.xhtml": PAGE.format(body=body)},
            extra_items='<item id="s" href="s.css" media-type="text/css"/>'
            '<item id="f" href="F.ttf" media-type="font/ttf"/>',
            extra_files={"OEBPS/s.css": sheet.encode(), "OEBPS/F.ttf": b"\x00\x01\x00\x00"},
        )
        result = rebuild(
            source, str(tmp_path / "out2.epub"),
            Policy.preset("preserve", render_gate="off"),
        )
        out = sheet_of(result)
        assert "p.pusty" not in out and "{}" not in out.replace("{ }", "{}")


class TestTheCommentShield:
    def test_the_wrapper_leaves_a_style_block(self, tmp_path):
        page = (
            '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
            '<meta charset="utf-8"/><title>R</title>'
            "<style>&lt;!--\np.tresc { margin: 0; text-indent: 1em; line-height: 1.3; }\n--&gt;</style>"
            '</head><body><p class="tresc">Akapit z treścią.</p></body></html>'
        )
        result = rebuild(
            make_book(tmp_path / "in.epub", {"c0.xhtml": page}),
            str(tmp_path / "out.epub"),
            Policy.preset("preserve", render_gate="off"),
        )
        assert result.status.wrote_a_file, result.report.to_text()
        import zipfile

        with zipfile.ZipFile(result.output_path) as archive:
            document = next(
                archive.read(n).decode("utf-8")
                for n in archive.namelist()
                if n.endswith(".xhtml") and "tresc" in archive.read(n).decode("utf-8")
            )
        assert "&lt;!--" not in document and "--&gt;" not in document
        assert "text-indent: 1em" in document  # the CSS itself survives
        assert "css.comment-shield-removed" in rules_of(result)

    def test_an_arrow_inside_content_stays(self, tmp_path):
        """Only the leading/trailing shield is the measured shape; a `-->`
        in the middle of a sheet is somebody's content."""
        sheet = 'p.tresc { margin: 0; } p.tresc::before { content: "-->"; }'
        result = build(tmp_path, sheet=sheet)
        assert 'content: "-->"' in sheet_of(result)
