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
* compatibility last — every measure there is a step away from the standard,
  taken for a named device, and nothing earlier should have to know about it.
"""

from .accessibility import AccessibilityStage
from .base import Context, Stage
from .compat import CompatibilityStage
from .content import ContentStage, StyleStage
from .fonts import FontStage
from .images import ImageStage
from .metadata import MetadataStage
from .navigation import NavigationStage
from .profile import ProfileStage
from .structure import StructureStage

DEFAULT_STAGES = (
    FontStage,
    ImageStage,
    StructureStage,
    MetadataStage,
    ProfileStage,
    ContentStage,
    StyleStage,
    NavigationStage,
    AccessibilityStage,
    CompatibilityStage,
)

__all__ = [
    "Context",
    "Stage",
    "DEFAULT_STAGES",
    "FontStage",
    "ImageStage",
    "StructureStage",
    "MetadataStage",
    "ProfileStage",
    "ContentStage",
    "StyleStage",
    "NavigationStage",
    "AccessibilityStage",
    "CompatibilityStage",
]
