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
        }

        for resource in book.resources.values():
            if resource.media_type.startswith("audio/"):
                survey["audio"] = True
            elif resource.media_type.startswith("video/"):
                survey["video"] = True

        for resource in book.content_docs():
            survey["documents"] += 1
            try:
                root, _ = xhtml.parse(resource.data)
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

        has_images = survey["images"] > 0 or survey["svg"]
        access_modes = ["textual"]
        if has_images:
            access_modes.append("visual")
        if survey["audio"]:
            access_modes.append("auditory")

        # Sufficient only if a reader who cannot see the images still gets the
        # whole work — which requires every non-decorative image to be described.
        meaningful_without_alt = survey["images_without_alt"] + survey["placeholder_alt"]
        if has_images and meaningful_without_alt == 0:
            sufficient = ["textual"]
        elif has_images:
            sufficient = ["textual,visual"]
        else:
            sufficient = ["textual"]

        features: list[str] = ["tableOfContents", "readingOrder"]
        if survey["headings"]:
            features.append("structuralNavigation")
        if has_images and meaningful_without_alt == 0:
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

        # Flashing and motion cannot be detected from markup. Claiming "none"
        # for a book that contains neither script nor moving media is safe;
        # anything else is honestly reported as unknown.
        if survey["video"] or survey["scripted"]:
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
                f"declared conformance with {metadata.conforms_to} because the caller asked for it",
                detail="EPUB-Forge did not verify this; it is the publisher's assertion.",
            )

        self.note(
            ctx,
            Level.FIX,
            "added EPUB Accessibility 1.1 discovery metadata",
            detail=(
                f"accessMode={'/'.join(access_modes)}; "
                f"features={', '.join(sorted(set(features)))}; hazard={hazards[0]}"
            ),
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
                f"{survey['images_without_alt']} image(s) have no usable alt text",
                location=locations[0] if len(locations) == 1 else f"{len(locations)} documents",
                detail=(
                    "Either the attribute is absent or it is empty. An empty alt asserts "
                    "the image is decorative, and that cannot be checked mechanically — "
                    "only role=\"presentation\" or aria-hidden=\"true\" says it outright. "
                    "So alternativeText is not claimed. If any of these images carry "
                    "meaning, only a human can write the description."
                ),
            )

        if survey["placeholder_alt"]:
            self.note(
                ctx,
                Level.WARN,
                f"{survey['placeholder_alt']} image(s) have alt text that only repeats the filename",
                detail=(
                    "; ".join(survey["placeholder_examples"])
                    + " — this passes validation but tells a screen-reader user nothing, "
                    "so alternativeText is not claimed."
                ),
            )

        if survey["heading_jumps"]:
            self.note(
                ctx,
                Level.WARN,
                f"heading levels skip a rank in {len(survey['heading_jumps'])} place(s)",
                detail="; ".join(survey["heading_jumps"][:3]),
            )

        if survey["tables_without_headers"]:
            self.note(
                ctx,
                Level.WARN,
                f"{survey['tables_without_headers']} table(s) have no header cells",
                detail="Screen readers cannot announce what a cell relates to without <th>.",
            )

        # Deliberately not reported: the absence of print page numbers. A survey
        # of 32 real books had it firing on all 32, which is what an absence
        # looks like when it is the norm rather than a defect — the publisher is
        # the only one who can supply them, so the entry named a fact nobody
        # could act on and pushed the findings that mattered further down the
        # page. A finding that is always true is not a finding.
