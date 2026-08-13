"""EPUB Accessibility 1.1 discovery metadata, derived from the book itself.

Since June 2025 the European Accessibility Act makes these declarations a legal
matter for anyone distributing e-books in the EU, which sets the rule this stage
follows: **every value must be derived from what the book demonstrably
contains.** A tool that writes ``alternativeText`` onto a book whose images have
no alt text has not improved accessibility — it has manufactured a false claim
and made the problem harder to find.

So the stage measures, declares only what it measured, and reports the rest as
work a human has to do. Conformance itself is never asserted automatically:
WCAG AA cannot be established by machine, and claiming it is the publisher's
statement to make, not this tool's.
"""

from __future__ import annotations

import re

from .. import xhtml
from ..report import Level
from .base import Context, Stage

#: The subset of WCAG-relevant traits that can be established mechanically.
CONFORMANCE_URLS = {
    "wcag-a": "EPUB Accessibility 1.1 - WCAG 2.2 Level A",
    "wcag-aa": "EPUB Accessibility 1.1 - WCAG 2.2 Level AA",
    "wcag-aaa": "EPUB Accessibility 1.1 - WCAG 2.2 Level AAA",
}

_HEADING_RE = re.compile(r"^h([1-6])$")

#: SVG's own animation elements. Their presence means something moves, and this
#: tool has no way to judge whether it flashes.
_SVG_ANIMATION_TAGS = {"animate", "animatetransform", "animatemotion", "set"}

#: CSS that makes something move. Matched on the property name rather than on a
#: parsed cascade, because the question here is only "is there any motion at
#: all" — a false positive costs an honest `unknown`, a false negative costs a
#: false `none`.
_CSS_MOTION_RE = re.compile(r"\b(?:animation|transition)(?:-[a-z-]+)?\s*:", re.IGNORECASE)


def _is_animated(data: bytes) -> bool:
    """Whether a GIF or WebP holds more than one frame.

    Read from the container rather than by decoding: an animated GIF has more
    than one image descriptor, and an animated WebP carries an ANIM chunk. Both
    checks are cheap and neither can be fooled into saying "still" by a file
    that moves.
    """
    if data[:6] in (b"GIF87a", b"GIF89a"):
        # Graphic Control Extension blocks: introducer 0x21, label 0xF9, size
        # 0x04. A still image has at most one (transparency uses it too), so
        # more than one means more than one frame.
        return data.count(b"\x21\xf9\x04") > 1
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return b"ANIM" in data[:512] or b"ANMF" in data[:512]
    return False


def _svg_is_described(element) -> bool:
    """Whether an inline SVG offers a text alternative.

    Four ways, all of them things somebody wrote on purpose: a child `<title>`
    with text, a child `<desc>`, an ARIA label, or an explicit statement that
    the graphic is decorative. An SVG with none of them is a picture the reader
    cannot get at, and it is exactly what used to be counted as nothing at all.
    """
    if (element.get("aria-label") or "").strip() or element.get("aria-labelledby"):
        return True
    if (element.get("role") or "").strip().lower() == "presentation":
        return True
    if (element.get("aria-hidden") or "").strip().lower() == "true":
        return True
    for child in element.iter():
        if xhtml.local_name(child).lower() in ("title", "desc") and (child.text or "").strip():
            return True
    return False

#: Alt text that exists but says nothing. Publishers generate these from the
#: filename or a template, which satisfies a validator and helps nobody.
_PLACEHOLDER_ALT = re.compile(
    r"^(image|img|picture|photo|graphic|illustration|figure|cover|okladka|ok\u0142adka|"
    r"obraz|obrazek|ilustracja|zdj\u0119cie|rysunek|grafika|untitled|bez\s*tytu\u0142u|"
    r"[a-z0-9._-]+\.(jpe?g|png|gif|svg|webp))$",
    re.IGNORECASE,
)


def is_placeholder_alt(alt: str, source: str | None) -> bool:
    """True when the alt merely names the file instead of describing it."""
    text = alt.strip()
    if _PLACEHOLDER_ALT.match(text):
        return True
    if source:
        stem = source.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if stem and text.lower() == stem.lower():
            return True
    # "title-1", "img_02" and similar: a token plus a number, carrying no words.
    return bool(re.fullmatch(r"[a-z]{1,12}[\s._-]*\d{1,3}", text, re.IGNORECASE))


class AccessibilityStage(Stage):
    name = "accessibility"

    def run(self, ctx: Context) -> None:
        if not ctx.policy.accessibility_metadata:
            return

        survey = self._survey(ctx)
        self._declare(ctx, survey)
        self._report_gaps(ctx, survey)

    # ------------------------------------------------------------- surveying
    def _survey(self, ctx: Context) -> dict:
        book = ctx.book
        survey = {
            "images": 0,
            "images_without_alt": 0,
            "decorative": 0,
            "placeholder_alt": 0,
            "placeholder_examples": [],
            "documents": 0,
            "headings": 0,
            "heading_jumps": [],
            "tables": 0,
            "tables_without_headers": 0,
            "mathml": False,
            "svg": False,
            "audio": False,
            "video": False,
            "scripted": False,
            "missing_alt_locations": [],
            #: Inline <svg> graphics, counted separately from <img> because they
            #: carry their alternative differently — in a child <title>, not in
            #: an attribute. Until 0.1.7 they were not counted at all, so a
            #: document whose only graphic was an undescribed inline SVG came
            #: out asserting alternativeText.
            "inline_svg": 0,
            "inline_svg_without_alt": 0,
            #: Anything that could move. Motion cannot be ruled out by reading
            #: markup alone, so this decides between "no hazard" and "unknown"
            #: rather than between "hazard" and "no hazard".
            "motion_sources": [],
        }

        for resource in book.resources.values():
            if resource.media_type.startswith("audio/"):
                survey["audio"] = True
            elif resource.media_type.startswith("video/"):
                survey["video"] = True
            elif resource.media_type in ("image/gif", "image/webp"):
                if _is_animated(resource.data):
                    survey["motion_sources"].append(f"animated image: {resource.path}")
            elif resource.media_type == "text/css":
                if _CSS_MOTION_RE.search(resource.text()):
                    survey["motion_sources"].append(f"CSS animation: {resource.path}")

        for resource in book.content_docs():
            survey["documents"] += 1
            try:
                root = ctx.parsed(resource).root
            except Exception:
                continue

            if "scripted" in resource.properties:
                survey["scripted"] = True
            if "mathml" in resource.properties:
                survey["mathml"] = True
            if "svg" in resource.properties:
                survey["svg"] = True

            previous_level = 0
            for element in xhtml.iter_elements(root):
                tag = xhtml.local_name(element).lower()

                if tag == "img":
                    survey["images"] += 1
                    alt = element.get("alt")
                    # An empty alt is a claim — "this image carries no
                    # information" — and nothing here can check it. It used to
                    # count as decorative unless the content stage remembered
                    # supplying it, but that memory lived in the run and not in
                    # the file: send the output back through and the same empty
                    # alt was read as a description, so a book with no alt text
                    # at all came out asserting alternativeText. State that has
                    # to survive the write cannot live in the context.
                    #
                    # Only an explicit, checkable assertion counts as
                    # decorative now. A bare empty alt counts as undescribed,
                    # which over-reports on books that use it correctly — that
                    # is the safe direction, and the report says so.
                    if alt is None or not alt.strip():
                        if self._declared_decorative(element):
                            survey["decorative"] += 1
                        else:
                            survey["images_without_alt"] += 1
                            survey["missing_alt_locations"].append(resource.path)
                    elif is_placeholder_alt(alt, element.get("src")):
                        survey["placeholder_alt"] += 1
                        if len(survey["placeholder_examples"]) < 4:
                            survey["placeholder_examples"].append(f'{resource.path}: alt="{alt}"')

                elif _HEADING_RE.match(tag):
                    level = int(tag[1])
                    survey["headings"] += 1
                    if previous_level and level > previous_level + 1:
                        survey["heading_jumps"].append(
                            f"{resource.path}: h{previous_level} → h{level}"
                        )
                    previous_level = level

                inline_style = element.get("style")
                if inline_style and _CSS_MOTION_RE.search(inline_style):
                    survey["motion_sources"].append(f"inline animation: {resource.path}")

                elif tag == "svg":
                    survey["inline_svg"] += 1
                    if not _svg_is_described(element):
                        survey["inline_svg_without_alt"] += 1
                        survey["missing_alt_locations"].append(resource.path)
                    if any(
                        xhtml.local_name(child).lower() in _SVG_ANIMATION_TAGS
                        for child in element.iter()
                    ):
                        survey["motion_sources"].append(f"SVG animation: {resource.path}")

                elif tag == "style" and element.text and _CSS_MOTION_RE.search(element.text):
                    survey["motion_sources"].append(f"CSS animation: {resource.path}")

                elif tag == "table":
                    survey["tables"] += 1
                    if not any(
                        xhtml.local_name(cell).lower() == "th" for cell in element.iter()
                    ):
                        survey["tables_without_headers"] += 1

        return survey

    @staticmethod
    def _declared_decorative(element) -> bool:
        """Whether the markup states outright that this image carries nothing.

        `role="presentation"` and `aria-hidden="true"` are assertions somebody
        wrote deliberately, which is what distinguishes them from an empty alt
        that may equally well be a placeholder nobody ever filled in.
        """
        return (
            (element.get("role") or "").strip().lower() == "presentation"
            or (element.get("aria-hidden") or "").strip().lower() == "true"
        )

    # ------------------------------------------------------------ declaring
    def _declare(self, ctx: Context, survey: dict) -> None:
        book = ctx.book
        metadata = book.metadata

        has_images = survey["images"] > 0 or survey["svg"] or survey["inline_svg"] > 0
        access_modes = ["textual"]
        if has_images:
            access_modes.append("visual")
        if survey["audio"]:
            access_modes.append("auditory")

        # Sufficient only if a reader who cannot see the images still gets the
        # whole work — which requires every non-decorative image to be described.
        meaningful_without_alt = (
            survey["images_without_alt"]
            + survey["placeholder_alt"]
            + survey["inline_svg_without_alt"]
        )

        # A book can declare `svg` on a document without this stage having seen
        # a single <svg> element — the property is on the manifest item, and the
        # graphic may sit in a file the parser could not read. That is a graphic
        # in an unknown state, and an unknown state must not be counted as a
        # described one.
        unexamined_graphics = survey["svg"] and survey["inline_svg"] == 0
        described = has_images and meaningful_without_alt == 0 and not unexamined_graphics
        if described or not has_images:
            sufficient = ["textual"]
        else:
            sufficient = ["textual,visual"]

        features: list[str] = ["tableOfContents", "readingOrder"]
        if survey["headings"]:
            features.append("structuralNavigation")
        # Only when every graphic in the book has been looked at and every one
        # of them offers an alternative. This is an assertion by the publisher
        # under EPUB Accessibility 1.1, and a false one is worse than a missing
        # one: it tells a reader who depends on it that the book is usable.
        if described:
            features.append("alternativeText")
        if book.page_list:
            features.append("printPageNumbers")
        if survey["mathml"]:
            features.append("MathML")
        if any(landmark.epub_type == "index" for landmark in book.landmarks):
            features.append("index")
        if book.rendition.get("layout") != "pre-paginated":
            # Reflowable text can be resized and recoloured by the reader.
            features.append("displayTransformability")

        # "none" says: nothing in this book flashes, moves or induces motion
        # sickness. Saying it required looking at every source of movement, and
        # until 0.1.7 the check covered two of them — video and script. A book
        # with a CSS keyframe animation, an animated GIF or an animating SVG
        # came out asserting `none`.
        #
        # The remaining honesty gap is stated rather than hidden: even with no
        # motion source at all, this tool cannot see a flashing sequence baked
        # into a video it did not decode. What it can do is refuse to claim
        # "none" whenever anything might move.
        motion = survey["motion_sources"]
        if survey["video"] or survey["scripted"] or motion:
            hazards = ["unknown"]
        else:
            hazards = ["none"]

        metadata.accessibility = {
            "schema:accessMode": access_modes,
            "schema:accessModeSufficient": sufficient,
            "schema:accessibilityFeature": sorted(set(features)),
            "schema:accessibilityHazard": hazards,
        }
        metadata.accessibility_summary = self._summary(ctx, survey, meaningful_without_alt)

        if ctx.policy.claim_conformance:
            metadata.conforms_to = CONFORMANCE_URLS.get(
                ctx.policy.claim_conformance, ctx.policy.claim_conformance
            )
            self.note(
                ctx,
                Level.INFO,
                "a11y.conformance-declared",
                values={"profile": metadata.conforms_to},
            )

        self.note(
            ctx,
            Level.FIX,
            "a11y.metadata-added",
            detail=f"accessMode={'/'.join(access_modes)}; "
                f"features={', '.join(sorted(set(features)))}; hazard={hazards[0]}",
        )

    def _summary(self, ctx: Context, survey: dict, missing_alt: int) -> str:
        parts = []
        if survey["headings"]:
            parts.append("nawigacja strukturalna oparta na nagłówkach")
        parts.append("spis treści zgodny z EPUB 3")
        if survey["images"] and not missing_alt:
            parts.append("wszystkie ilustracje mają tekst alternatywny")
        elif missing_alt:
            parts.append(f"{missing_alt} ilustracji nie ma tekstu alternatywnego")
        if ctx.book.page_list:
            parts.append("numeracja stron wydania drukowanego")
        if ctx.book.rendition.get("layout") != "pre-paginated":
            parts.append("tekst przepływalny, skalowalny przez czytnik")
        return "Publikacja zawiera: " + "; ".join(parts) + "."

    # -------------------------------------------------------------- gaps
    def _report_gaps(self, ctx: Context, survey: dict) -> None:
        if survey["images_without_alt"]:
            locations = sorted(set(survey["missing_alt_locations"]))
            self.note(
                ctx,
                Level.WARN,
                "a11y.missing-alt",
                values={"count": survey["images_without_alt"]},
                location=locations[0] if len(locations) == 1 else f"{len(locations)} documents",
            )

        if survey["placeholder_alt"]:
            self.note(
                ctx,
                Level.WARN,
                "a11y.placeholder-alt",
                values={
                    "count": survey["placeholder_alt"],
                    "examples": "; ".join(survey["placeholder_examples"]),
                },
            )

        if survey["heading_jumps"]:
            self.note(
                ctx,
                Level.WARN,
                "a11y.heading-jump",
                values={"count": len(survey["heading_jumps"])},
                detail="; ".join(survey["heading_jumps"][:3]),
            )

        if survey["tables_without_headers"]:
            self.note(
                ctx,
                Level.WARN,
                "a11y.table-without-headers",
                values={"count": survey["tables_without_headers"]},
            )

        # Deliberately not reported: the absence of print page numbers. A survey
        # of 32 real books had it firing on all 32, which is what an absence
        # looks like when it is the norm rather than a defect — the publisher is
        # the only one who can supply them, so the entry named a fact nobody
        # could act on and pushed the findings that mattered further down the
        # page. A finding that is always true is not a finding.
