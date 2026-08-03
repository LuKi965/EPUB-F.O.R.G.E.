"""Enough CSS cascade awareness to tell a publisher's decision from a side effect.

The distinction this module exists to draw: ``p { text-align: justify }`` is a
default for running text, while ``p.obraz { text-align: center }`` is a statement
about one specific kind of paragraph. Both reach an image-only paragraph, but
only the second is a decision about *that* paragraph — and decisions must not be
overridden.

Specificity is the signal. A rule selected by class or id is deliberate; a bare
type selector is a blanket default that happens to also land on the image.

This is not a CSS engine. It answers one narrow question — "does any rule that
could match this element declare this property, and was that rule targeted or
generic?" — and errs toward *targeted* whenever a selector is too complex to
read confidently, because that outcome leaves the book alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import cssutils

cssutils.log.setLevel(50)

#: Splits a selector into compound parts; only the rightmost one matches the
#: element itself, the rest constrain its ancestors.
_COMBINATOR = re.compile(r"\s*[>+~]\s*|\s+")

#: tag, then any number of .class / #id fragments.
_COMPOUND = re.compile(r"^([a-zA-Z][\w-]*|\*)?((?:[.#][\w-]+)*)$")


@dataclass
class Rule:
    tag: str | None
    classes: frozenset[str]
    element_id: str | None
    declarations: dict[str, str]
    #: True when the rule is selected by class, id, attribute or pseudo-class,
    #: i.e. the author aimed at something narrower than "every <p>".
    targeted: bool

    def matches(self, tag: str, classes: frozenset[str], element_id: str | None) -> bool:
        if self.tag not in (None, "*", tag):
            return False
        if not self.classes <= classes:
            return False
        return self.element_id in (None, element_id)


@dataclass
class Cascade:
    """The rules from one document's stylesheets, indexed for lookup."""

    rules: list[Rule] = field(default_factory=list)

    @classmethod
    def parse(cls, sources: list[str]) -> "Cascade":
        cascade = cls()
        for text in sources:
            if not text or not text.strip():
                continue
            try:
                sheet = cssutils.parseString(text, validate=False)
            except Exception:
                continue
            for rule in sheet:
                if rule.type != rule.STYLE_RULE:
                    continue
                declarations = {
                    property_name.name.lower(): property_name.value
                    for property_name in rule.style
                }
                if not declarations:
                    continue
                for selector in rule.selectorText.split(","):
                    parsed = cls._parse_selector(selector.strip())
                    if parsed is None:
                        continue
                    tag, classes, element_id, targeted = parsed
                    cascade.rules.append(
                        Rule(tag, classes, element_id, declarations, targeted)
                    )
        return cascade

    @staticmethod
    def _parse_selector(selector: str):
        if not selector:
            return None
        rightmost = _COMBINATOR.split(selector)[-1]
        # Pseudo-elements do not affect which element the rule targets.
        rightmost = re.sub(r"::?[\w-]+(\([^)]*\))?", "", rightmost)
        if "[" in rightmost:
            # Attribute selectors are targeted by nature; keep the tag, mark it.
            tag_only = rightmost.split("[", 1)[0] or None
            return (tag_only or None, frozenset(), None, True)

        match = _COMPOUND.match(rightmost)
        if match is None:
            # Something exotic. Treating it as targeted means "leave it alone".
            return (None, frozenset(), None, True)

        tag = match.group(1)
        fragments = re.findall(r"[.#][\w-]+", match.group(2) or "")
        classes = frozenset(f[1:] for f in fragments if f.startswith("."))
        ids = [f[1:] for f in fragments if f.startswith("#")]
        return (
            tag if tag and tag != "*" else None,
            classes,
            ids[0] if ids else None,
            bool(classes or ids),
        )

    def lookup(
        self, prop: str, tag: str, classes: frozenset[str], element_id: str | None
    ) -> tuple[str | None, bool]:
        """Return ``(value, targeted)`` for *prop* as it applies to this element.

        Later rules win, matching the cascade for equal specificity closely
        enough for this purpose. ``targeted`` reports whether the winning
        declaration came from a rule aimed at this element specifically.
        """
        value: str | None = None
        targeted = False
        for rule in self.rules:
            if prop not in rule.declarations:
                continue
            if not rule.matches(tag, classes, element_id):
                continue
            # A targeted rule outranks a generic one regardless of order.
            if rule.targeted or not targeted:
                value = rule.declarations[prop]
                targeted = targeted or rule.targeted
        return value, targeted

    def declares_targeted(
        self, prop: str, tag: str, classes: frozenset[str], element_id: str | None
    ) -> bool:
        """True when some rule aimed at this element specifically sets *prop*."""
        return any(
            prop in rule.declarations
            and rule.targeted
            and rule.matches(tag, classes, element_id)
            for rule in self.rules
        )


def is_zero_length(value: str | None) -> bool:
    """True for ``0``, ``0%``, ``0px`` and friends — anything with no effect."""
    if value is None:
        return True
    return bool(re.fullmatch(r"0(\.0+)?\s*(%|[a-z]{2,4})?", value.strip(), re.IGNORECASE))


#: HTML's default rendering. Only the elements this tool needs to reason about
#: are listed; anything unknown is treated as inline, which is the safer guess
#: because it leads to no intervention.
_DEFAULT_BLOCK = {
    "address", "article", "aside", "blockquote", "body", "dd", "details", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "html", "main", "nav", "ol",
    "p", "pre", "section", "table", "ul",
}
_DEFAULT_LIST_ITEM = {"li"}

#: Display values that establish a block-level box inside their parent.
BLOCK_LEVEL_DISPLAYS = {
    "block", "flow-root", "list-item", "table", "flex", "grid", "table-row",
    "table-cell", "table-row-group",
}


def effective_display(
    cascade: "Cascade", tag: str, classes: frozenset[str], element_id: str | None,
    inline_style: str = "",
) -> str:
    """Best-effort computed ``display`` for an element."""
    match = re.search(r"(?:^|;)\s*display\s*:\s*([\w-]+)", inline_style or "", re.IGNORECASE)
    if match:
        return match.group(1).lower()
    declared, _ = cascade.lookup("display", tag, classes, element_id)
    if declared:
        return declared.strip().lower().split()[0]
    if tag in _DEFAULT_LIST_ITEM:
        return "list-item"
    return "block" if tag in _DEFAULT_BLOCK else "inline"


def is_block_level(display: str) -> bool:
    return display in BLOCK_LEVEL_DISPLAYS
