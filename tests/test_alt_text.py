"""Images without a usable text alternative: asked about, never described.

Record 038's second half. 1 140 image places in 109 of 160 books carry no
text alternative a screen reader could use. The program sorts them by the
evidence a person would use anyway — an ornament repeated over every
chapter, a tiny separator, the cover the package names, everything else —
and asks one question per image file. It recommends; it never describes;
without an answer nothing changes (S-05).
"""

from __future__ import annotations

import io
import os
import re
import zipfile

from PIL import Image

from epubforge.decisions import KEEP, Answer
from epubforge.pipeline import rebuild
from epubforge.policy import Policy

from tests.factory import png_bytes
from tests.test_shelf_refusals import make_book, rules_of

PAGE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head><title>R</title></head>'
    "<body>{body}</body></html>"
)


def noisy_png(size=(200, 300)) -> bytes:
    """A picture that does not compress into the tiny bucket."""
    buffer = io.BytesIO()
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(buffer, format="PNG")
    return buffer.getvalue()


class Chooser:
    """Answers every image question the same way, or by a function."""

    def __init__(self, answer):
        self.answer = answer if callable(answer) else (lambda question: answer)
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return self.answer(question)


def build(tmp_path, documents, images, *, chooser=None, extra_items="", policy=None):
    items = "".join(
        f'<item id="i{n}" href="{name}" media-type="image/png"{extra}/>'
        for n, (name, extra) in enumerate(
            (name, ' properties="cover-image"' if name.startswith("cover") else "")
            for name in images
        )
    ) + extra_items
    source = make_book(
        tmp_path / "in.epub",
        {name: PAGE.format(body=body) for name, body in documents.items()},
        extra_items=items,
        extra_files={f"OEBPS/{name}": data for name, data in images.items()},
    )
    result = rebuild(
        source, str(tmp_path / "out.epub"),
        policy or Policy.preset("preserve", render_gate="off"),
        resolver=chooser,
    )
    return result


def images_of(result) -> list[dict]:
    """Every <img> of the rebuilt book, as its attributes, in document order."""
    found = []
    with zipfile.ZipFile(result.output_path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".xhtml") or name.endswith("nav.xhtml"):
                continue
            text = archive.read(name).decode("utf-8")
            for tag in re.findall(r"<img\b[^>]*>", text):
                found.append(dict(re.findall(r'([a-z-]+)="([^"]*)"', tag)))
    return found


def image_questions(chooser):
    return [q for q in chooser.asked if q.kind == "image"]


def untouched(mark: dict) -> bool:
    """Whether this stage left the image as the content stage handed it over:
    that stage adds an empty alt to every image lacking one, and an empty alt
    with nobody vouching for it is still an undescribed image."""
    return not mark.get("alt") and mark.get("role") != "presentation"


ORNAMENT_DOCS = {
    f"c{n}.xhtml": f'<p><img src="rose.png"/></p><h1>Rozdział {n}</h1><p>Tekst rozdziału.</p>'
    for n in range(3)
}


class TestAnOrnamentRepeatedOverTheChapters:
    def test_is_asked_about_once_and_marked_decorative_on_yes(self, tmp_path):
        """The same file standing alone in three documents is one question,
        recommended decorative; "yes" writes alt="" and role="presentation"
        into all three, and the accessibility stage stops counting it."""
        chooser = Chooser(Answer(option="decorative"))
        result = build(tmp_path, ORNAMENT_DOCS, {"rose.png": png_bytes((120, 40))}, chooser=chooser)
        asked = image_questions(chooser)
        assert len(asked) == 1
        assert asked[0].recommended == "decorative"
        assert asked[0].group.startswith("images:ornament:")
        assert asked[0].group != "images:ornament:"
        assert "rose.png" in asked[0].summary
        marks = images_of(result)
        assert len(marks) == 3
        assert all(m.get("alt") == "" and m.get("role") == "presentation" for m in marks)
        assert "pictures.decorative-marked" in rules_of(result)
        assert "a11y.missing-alt" not in rules_of(result)

    def test_nobody_answering_changes_nothing(self, tmp_path):
        """S-05: no answer, no change — and the report says so twice, once
        from this stage and once from the accessibility count."""
        result = build(tmp_path, ORNAMENT_DOCS, {"rose.png": png_bytes((120, 40))})
        assert all(untouched(m) for m in images_of(result))
        assert "pictures.left-alone" in rules_of(result)
        assert "pictures.decorative-marked" not in rules_of(result)
        assert "a11y.missing-alt" in rules_of(result)

    def test_keep_is_keep(self, tmp_path):
        chooser = Chooser(Answer(option=KEEP))
        result = build(tmp_path, ORNAMENT_DOCS, {"rose.png": png_bytes((120, 40))}, chooser=chooser)
        assert all(untouched(m) for m in images_of(result))
        assert "pictures.left-alone" in rules_of(result)

    def test_a_standing_answer_covers_the_other_ornaments_of_the_book(self, tmp_path):
        """Two ornament files, one answer "for all of them": the second is
        never put to the person and is marked all the same."""
        docs = {
            f"c{n}.xhtml": f'<p><img src="rose.png"/></p><h1>R{n}</h1><p>Tekst.</p><p><img src="leaf.png"/></p>'
            for n in range(3)
        }
        chooser = Chooser(Answer(option="decorative", apply_to_group=True))
        result = build(
            tmp_path, docs,
            {"rose.png": png_bytes((120, 40)), "leaf.png": png_bytes((110, 30), (0, 200, 0))},
            chooser=chooser,
        )
        assert len(image_questions(chooser)) == 1
        marks = images_of(result)
        assert len(marks) == 6
        assert all(m.get("role") == "presentation" for m in marks)


class TestABigPictureRepeatedOverTheParts:
    def test_is_an_illustration_however_often_it_recurs(self, tmp_path):
        """The first run on real books called a 2.2 MB plate repeated in five
        documents an ornament and recommended hiding it. A picture over the
        ornament bounds is asked about as an illustration, its repetition in
        the evidence, and the recommendation is to leave it. The mutation
        that drops the bounds fails here."""
        docs = {
            f"c{n}.xhtml": f'<div><img src="plate.png"/></div><h1>Część {n}</h1><p>Tekst.</p>'
            for n in range(3)
        }
        chooser = Chooser(Answer(option=KEEP))
        build(tmp_path, docs, {"plate.png": noisy_png((900, 1200))}, chooser=chooser)
        asked = image_questions(chooser)
        assert len(asked) == 1
        assert asked[0].group.startswith("images:illustration:")
        assert asked[0].recommended == KEEP
        assert "3" in asked[0].summary


class TestAnIllustration:
    def test_is_recommended_left_and_takes_a_typed_description(self, tmp_path):
        """A big picture in one document: the program has no opinion to
        recommend beyond "leave it", and the description a person types goes
        into the alt as typed."""
        docs = {"c0.xhtml": '<h1>R</h1><p>Tekst.</p><div><img src="map.png"/></div>'}
        chooser = Chooser(Answer(option="describe", value="Mapa wybrzeża"))
        result = build(tmp_path, docs, {"map.png": noisy_png()}, chooser=chooser)
        asked = image_questions(chooser)
        assert len(asked) == 1
        assert asked[0].recommended == KEEP
        assert asked[0].group.startswith("images:illustration:")
        assert [o.id for o in asked[0].options] == ["keep", "decorative", "describe"]
        assert next(o for o in asked[0].options if o.id == "describe").needs_value
        assert images_of(result)[0].get("alt") == "Mapa wybrzeża"
        assert "pictures.described" in rules_of(result)
        assert "a11y.missing-alt" not in rules_of(result)

    def test_describe_with_nothing_typed_changes_nothing(self, tmp_path):
        docs = {"c0.xhtml": '<h1>R</h1><p>Tekst.</p><div><img src="map.png"/></div>'}
        chooser = Chooser(Answer(option="describe", value="   "))
        result = build(tmp_path, docs, {"map.png": noisy_png()}, chooser=chooser)
        assert untouched(images_of(result)[0])
        assert "pictures.left-alone" in rules_of(result)


class TestATinyPicture:
    def test_alone_is_recommended_decorative_but_inside_text_is_not(self, tmp_path):
        """Size alone cannot tell a separator from a symbol the story uses.
        Standing alone the recommendation is decorative; inside a line of
        text it is to leave it for the person."""
        docs = {
            "c0.xhtml": '<h1>R</h1><p><img src="rule.png"/></p><p>Ma <img src="sym.png"/> znak.</p>',
        }
        chooser = Chooser(Answer(option=KEEP))
        build(tmp_path, docs, {"rule.png": png_bytes((10, 10)), "sym.png": png_bytes((12, 12), (0, 0, 0))}, chooser=chooser)
        by_file = {q.summary.split()[2]: q for q in image_questions(chooser)}
        assert by_file["rule.png"].recommended == "decorative"
        assert by_file["sym.png"].recommended == KEEP
        assert all(q.group.startswith("images:tiny:") for q in by_file.values())


class TestTheCover:
    def test_is_never_asked_about_because_the_content_stage_already_named_it(self, tmp_path):
        """The cover's description is the book's own title — a fact from the
        package that the content stage writes before this stage runs. So the
        cover reaches this stage described, and no question is put."""
        docs = {"c0.xhtml": '<div><img src="cover.png"/></div>', "c1.xhtml": "<h1>R</h1><p>Tekst.</p>"}
        chooser = Chooser(Answer(option="decorative"))
        result = build(tmp_path, docs, {"cover.png": noisy_png((300, 450))}, chooser=chooser)
        assert not image_questions(chooser)
        with zipfile.ZipFile(result.output_path) as archive:
            package = next(n for n in archive.namelist() if n.endswith(".opf"))
            title = re.search(r"<dc:title[^>]*>([^<]+)</dc:title>", archive.read(package).decode()).group(1)
        assert title
        assert images_of(result)[0].get("alt") == title


class TestWhatIsNeverAsked:
    def test_described_and_declared_decorative_pictures(self, tmp_path):
        docs = {
            "c0.xhtml": (
                '<h1>R</h1><p>Tekst.</p><div><img src="map.png" alt="Mapa"/></div>'
                '<p><img src="rule.png" alt="" role="presentation"/></p>'
            ),
        }
        chooser = Chooser(Answer(option="decorative"))
        result = build(tmp_path, docs, {"map.png": noisy_png(), "rule.png": png_bytes((10, 10))}, chooser=chooser)
        assert not image_questions(chooser)
        assert not [r for r in rules_of(result) if r.startswith("pictures.")]

    def test_a_placeholder_alt_is_asked_and_shown(self, tmp_path):
        """An alt that only repeats the file name is no description; the
        question says what stands there today."""
        docs = {"c0.xhtml": '<h1>R</h1><p>Tekst.</p><div><img src="image1.png" alt="image1"/></div>'}
        chooser = Chooser(Answer(option="decorative"))
        result = build(tmp_path, docs, {"image1.png": noisy_png()}, chooser=chooser)
        asked = image_questions(chooser)
        assert len(asked) == 1
        assert "image1" in asked[0].detail
        mark = images_of(result)[0]
        assert mark.get("alt") == "" and mark.get("role") == "presentation"

    def test_switched_off_nothing_is_asked(self, tmp_path):
        policy = Policy.preset("preserve", render_gate="off")
        policy.detect_undescribed_images = False
        chooser = Chooser(Answer(option="decorative"))
        result = build(tmp_path, ORNAMENT_DOCS, {"rose.png": png_bytes((120, 40))}, chooser=chooser, policy=policy)
        assert not image_questions(chooser)
        assert all(untouched(m) for m in images_of(result))
        assert "a11y.missing-alt" in rules_of(result)


class TestTheEvidenceIsReadFromTheFile:
    def test_dimensions_of_the_three_formats(self):
        from epubforge.stages.alt_text import dimensions

        assert dimensions(png_bytes((33, 44))) == (33, 44)
        buffer = io.BytesIO()
        Image.new("RGB", (50, 20)).save(buffer, format="JPEG")
        assert dimensions(buffer.getvalue()) == (50, 20)
        buffer = io.BytesIO()
        Image.new("P", (7, 9)).save(buffer, format="GIF")
        assert dimensions(buffer.getvalue()) == (7, 9)
        assert dimensions(b"not a picture") is None
        assert dimensions(b"\x89PNG\r\n\x1a\n\x00") is None
