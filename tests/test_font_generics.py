"""Pillar A, ninth slice: generic font families through the question queue.

Three answers, in order of authority: the embedded font's own PANOSE
(deterministic — and the whole book's `@font-face` blocks answer, not just
the local sheet's); common knowledge about faces nobody embedded ("Times
New Roman" is 41 913 of the shelf's 50 173 findings), offered through a
question and never applied on the program's own authority (S-05: no
answer, no change); and nothing — a symbol face gets no question, an
unknown name stays a guess, both counted.
"""

from __future__ import annotations

from epubforge.decisions import Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.test_shelf_refusals import make_book, rules_of
from tests.test_class_translation import PAGE
from tests.test_fonts_meta import sfnt, text_panose

BODY = (
    '<p class="jeden">Akapit z treścią.</p>'
    '<p class="dwa">Drugi akapit.</p>'
)


class _Chooser:
    def __init__(self, option: str):
        self.option = option
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return Answer(option=self.option)


def build(tmp_path, *, sheet, body=BODY, option=None, extra_items="", extra_files=None):
    source = make_book(
        tmp_path / "in.epub",
        {"c0.xhtml": PAGE.format(body=body)},
        extra_items='<item id="s" href="s.css" media-type="text/css"/>' + extra_items,
        extra_files={"OEBPS/s.css": sheet.encode(), **(extra_files or {})},
    )
    chooser = _Chooser(option) if option else None
    result = rebuild(
        source, str(tmp_path / "out.epub"),
        Policy.preset("preserve", render_gate="off"),
        resolver=chooser,
    )
    return result, chooser


def sheet_of(result):
    """Every stylesheet of the rebuild, concatenated — a book here may
    carry a fonts sheet beside the styles sheet."""
    import zipfile
    texts = []
    with zipfile.ZipFile(result.output_path) as archive:
        for name in archive.namelist():
            if name.endswith(".css"):
                texts.append(archive.read(name).decode("utf-8"))
    if not texts:
        raise AssertionError("no stylesheet in the rebuild")
    return "\n".join(texts)


class TestTheQuestion:
    def test_nobody_answers_nothing_changes(self, tmp_path):
        """S-05 is the ground rule: the recommendation is this program's
        opinion, and with nobody to ask the stack stays exactly as the
        publisher wrote it."""
        sheet = 'p.jeden { font-family: "Times New Roman"; }'
        result, _ = build(tmp_path, sheet=sheet)
        out = sheet_of(result)
        assert 'font-family: "Times New Roman";' in out
        assert ", serif" not in out
        assert "css.font-stack-generic-missing" in rules_of(result)
        assert "css.font-stack-generic-approved" not in rules_of(result)

    def test_an_answer_appends_to_every_declaration_in_the_group(self, tmp_path):
        """Times and Georgia are one serif question, one answer, both
        appended. The mutation that applies only the first entry fails
        here."""
        sheet = (
            'p.jeden { font-family: "Times New Roman"; } '
            "p.dwa { font-family: Georgia; }"
        )
        result, chooser = build(tmp_path, sheet=sheet, option="append")
        out = sheet_of(result)
        assert 'font-family: "Times New Roman", serif' in out
        assert "font-family: Georgia, serif" in out
        assert "css.font-stack-generic-approved" in rules_of(result)
        generic_questions = [q for q in chooser.asked
                             if q.group.startswith("style:generic-")]
        assert len(generic_questions) == 1
        assert generic_questions[0].recommended == "append"

    def test_each_generic_family_is_its_own_question(self, tmp_path):
        sheet = (
            'p.jeden { font-family: "Times New Roman"; } '
            "p.dwa { font-family: Verdana; }"
        )
        result, chooser = build(tmp_path, sheet=sheet, option="append")
        out = sheet_of(result)
        assert '"Times New Roman", serif' in out
        assert "Verdana, sans-serif" in out
        groups = sorted(q.group for q in chooser.asked
                        if q.group.startswith("style:generic-"))
        assert groups == ["style:generic-sans-serif", "style:generic-serif"]


class TestWhatIsNeverAsked:
    def test_an_unknown_face_stays_a_guess(self, tmp_path):
        sheet = "p.jeden { font-family: Krojwlasny; }"
        result, chooser = build(tmp_path, sheet=sheet, option="append")
        assert "Krojwlasny," not in sheet_of(result)
        assert not [q for q in chooser.asked
                    if q.group.startswith("style:generic-")]
        assert "css.font-stack-generic-missing" in rules_of(result)

    def test_a_symbol_face_gets_no_question(self, tmp_path):
        """`Wingdings, Arial` — the dictionary knows Arial, but the stack
        opens on a face that draws pictures, and no generic family does.
        Without the exclusion the Arial entry would earn the stack a
        `sans-serif` promise no substitute can keep. The mutation that
        drops the symbol exclusion fails here."""
        sheet = "p.jeden { font-family: Wingdings, Arial; }"
        result, chooser = build(tmp_path, sheet=sheet, option="append")
        assert "sans-serif" not in sheet_of(result)
        assert not [q for q in chooser.asked
                    if q.group.startswith("style:generic-")]


class TestTheBookAnswersFirst:
    def test_a_face_embedded_in_another_sheet_needs_no_question(self, tmp_path):
        """`@font-face` lives in fonts.css, the styles in s.css — the book
        embeds the face all the same, its PANOSE says serif, and the
        generic is read, not asked about. The mutation that consults only
        the local sheet fails here."""
        font = sfnt(panose=text_panose(2))  # a serif by its own word
        fonts_css = (
            '@font-face { font-family: "Domowy"; src: url(f.ttf); }'
        )
        sheet = 'p.jeden { font-family: "Domowy"; }'
        result, chooser = build(
            tmp_path, sheet=sheet, option="append",
            extra_items=(
                '<item id="fc" href="fonts.css" media-type="text/css"/>'
                '<item id="f" href="f.ttf" media-type="font/ttf"/>'
            ),
            extra_files={
                "OEBPS/fonts.css": fonts_css.encode(),
                "OEBPS/f.ttf": font,
            },
        )
        out = sheet_of(result)
        assert '"Domowy", serif' in out
        assert "css.font-stack-generic-added" in rules_of(result)
        assert not [q for q in chooser.asked
                    if q.group.startswith("style:generic-")]


def embed(tmp_path, *, font: bytes, declared: str, stack: str, option="append"):
    """One embedded face under *declared*, one stack naming *stack*."""
    fonts_css = f'@font-face {{ font-family: "{declared}"; src: url(f.ttf); }}'
    sheet = f'p.jeden {{ font-family: "{stack}"; }}'
    return build(
        tmp_path, sheet=sheet, option=option,
        extra_items=(
            '<item id="fc" href="fonts.css" media-type="text/css"/>'
            '<item id="f" href="f.ttf" media-type="font/ttf"/>'
        ),
        extra_files={
            "OEBPS/fonts.css": fonts_css.encode(),
            "OEBPS/f.ttf": font,
        },
    )


class TestAnEmbeddedFaceThatIsSilentInOS2:
    """The shelf after the first wave: 224 of the 391 stacks still without a
    generic named faces the book embedded, whose designers left PANOSE at
    "any". What the font says elsewhere about itself is read; what it says
    nowhere goes to the question on its name; what is neither stays."""

    def test_its_own_name_saying_sans_is_read_not_asked(self, tmp_path):
        """`Alegreya Sans` with a blank OS/2 table: the name is the font's
        word, so the generic is added deterministically and no question is
        put."""
        font = sfnt(panose=(0,) * 10, family="Alegreya Sans")
        result, chooser = embed(
            tmp_path, font=font, declared="AlegreyaSans", stack="AlegreyaSans",
        )
        assert '"AlegreyaSans", sans-serif' in sheet_of(result)
        assert "css.font-stack-generic-added" in rules_of(result)
        assert "css.font-stack-generic-missing" not in rules_of(result)
        assert not [q for q in chooser.asked
                    if q.group.startswith("style:generic-")]

    def test_a_face_that_says_nothing_anywhere_goes_to_the_question(self, tmp_path):
        """TeX Gyre Heros: embedded, readable, blank OS/2, a name with no
        word in it. The book carries the face but does not state its kind,
        so common knowledge about the name is offered — through the question,
        never on the program's own authority. The mutation that treats
        "embedded" as "answered" fails here, and so does the one that skips
        the table for embedded faces."""
        font = sfnt(panose=(0,) * 10, family="TeX Gyre Heros")
        result, chooser = embed(
            tmp_path, font=font, declared="TexGyreHeros", stack="TexGyreHeros",
        )
        assert '"TexGyreHeros", sans-serif' in sheet_of(result)
        assert "css.font-stack-generic-approved" in rules_of(result)
        asked = [q for q in chooser.asked if q.group.startswith("style:generic-")]
        assert [q.group for q in asked] == ["style:generic-sans-serif"]
        assert asked[0].recommended == "append"

    def test_nobody_answering_leaves_the_silent_face_alone(self, tmp_path):
        font = sfnt(panose=(0,) * 10, family="TeX Gyre Heros")
        result, _ = embed(
            tmp_path, font=font, declared="TexGyreHeros", stack="TexGyreHeros",
            option=None,
        )
        assert '"TexGyreHeros";' in sheet_of(result)
        assert "css.font-stack-generic-missing" in rules_of(result)

    def test_a_face_nobody_knows_stays_a_guess(self, tmp_path):
        font = sfnt(panose=(0,) * 10, family="Krojwlasny")
        result, chooser = embed(
            tmp_path, font=font, declared="Krojwlasny", stack="Krojwlasny",
        )
        assert '"Krojwlasny";' in sheet_of(result)
        assert "css.font-stack-generic-missing" in rules_of(result)
        assert not [q for q in chooser.asked
                    if q.group.startswith("style:generic-")]


class TestSpellingOfACommonName:
    def test_a_name_written_without_spaces_is_the_same_face(self, tmp_path):
        """Word writes `TimesNewRoman` as readily as `Times New Roman`; both
        are the one serif question."""
        sheet = (
            'p.jeden { font-family: TimesNewRoman; } '
            'p.dwa { font-family: "Times New Roman"; }'
        )
        result, chooser = build(tmp_path, sheet=sheet, option="append")
        out = sheet_of(result)
        assert "font-family: TimesNewRoman, serif" in out
        assert '"Times New Roman", serif' in out
        assert len([q for q in chooser.asked
                    if q.group.startswith("style:generic-")]) == 1
