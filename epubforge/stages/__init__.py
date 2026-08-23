"""Rebuild stages, in the order the pipeline runs them.

Order is load-bearing:

* fonts before metadata — deobfuscation is keyed on the *source* identifier;
* images before structure — transcoding renames files, and the structure stage
  is what freezes the final path map;
* structure before content — href rewriting needs that map;
* profile between metadata and content — earlier is impossible because paths
  are only frozen once the structure stage has run, and later is pointless
  because the content stage has by then rewritten the markup it describes;
* navigation before accessibility — the latter counts what the former built;
* accessibility before compatibility — it must measure the book proper, not the
  device concessions layered on top of it;
* typography after content — it edits the text, and the content stage moves
  markup around it;
* footnotes after hyphens and before navigation — the linking question needs
  the text in its final shape, and the anchors it may add exist before
  anything counts or validates references. Running it first would mean unwrapping a `<span>` through a
  paragraph the text of which had just been retyped, for no gain;
* compatibility last — every measure there is a step away from the standard,
  taken for a named device, and nothing earlier should have to know about it.
"""

from .accessibility import AccessibilityStage
from .base import Context, Stage
from .compat import CompatibilityStage
from .content import ContentStage
from .font_subset import FontSubsetStage
from .fonts import FontStage
from .footnotes import FootnoteStage
from .images import ImageStage
from .metadata import MetadataStage
from .navigation import NavigationStage
from .profile import ProfileStage
from .style import StyleStage
from .structure import StructureStage
from .hyphens import HyphenStage
from .typography import TypographyStage

DEFAULT_STAGES = (
    FontStage,
    ImageStage,
    StructureStage,
    MetadataStage,
    ProfileStage,
    ContentStage,
    StyleStage,
    TypographyStage,
    HyphenStage,
    FootnoteStage,
    NavigationStage,
    AccessibilityStage,
    CompatibilityStage,
    # Last, and the reason is the glyph set: the navigation document this
    # program generates and the cover page it synthesises carry text the
    # source never had, so a font cut before them would lose exactly the
    # glyphs the rebuild had just added (filar E).
    FontSubsetStage,
)

__all__ = [
    "Context",
    "Stage",
    "DEFAULT_STAGES",
    "FontStage",
    "FontSubsetStage",
    "FootnoteStage",
    "ImageStage",
    "StructureStage",
    "MetadataStage",
    "ProfileStage",
    "ContentStage",
    "StyleStage",
    "TypographyStage",
    "HyphenStage",
    "NavigationStage",
    "AccessibilityStage",
    "CompatibilityStage",
]
