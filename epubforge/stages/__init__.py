"""Rebuild stages, in the order the pipeline runs them.

Order is load-bearing:

* fonts before metadata — deobfuscation is keyed on the *source* identifier;
* images before structure — transcoding renames files, and the structure stage
  is what freezes the final path map;
* structure before content — href rewriting needs that map;
* navigation last — it generates files that need no further normalisation.
"""

from .base import Context, Stage
from .content import ContentStage, StyleStage
from .fonts import FontStage
from .images import ImageStage
from .metadata import MetadataStage
from .navigation import NavigationStage
from .structure import StructureStage

DEFAULT_STAGES = (
    FontStage,
    ImageStage,
    StructureStage,
    MetadataStage,
    ContentStage,
    StyleStage,
    NavigationStage,
)

__all__ = [
    "Context",
    "Stage",
    "DEFAULT_STAGES",
    "FontStage",
    "ImageStage",
    "StructureStage",
    "MetadataStage",
    "ContentStage",
    "StyleStage",
    "NavigationStage",
]
