"""Stage protocol and the shared context threaded through the rebuild."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Book
from ..policy import Policy
from ..report import Level, Report


@dataclass
class Context:
    book: Book
    policy: Policy
    report: Report
    #: Maps every original container path to its current one. Built once the
    #: path-mutating stages have finished, so href rewriting has a single source
    #: of truth even after several renames.
    path_map: dict[str, str] = field(default_factory=dict)
    #: The unique identifier as found in the source, captured before metadata
    #: normalisation because font deobfuscation is keyed on it.
    original_identifier: str | None = None
    #: Documents where an image had no alt at all and one was supplied. The
    #: accessibility stage runs after that repair, so it cannot see the gap in
    #: the DOM and would otherwise mistake a filled-in alt for a real one.
    auto_alt_locations: list[str] = field(default_factory=list)

    #: Every id present in each finished document, so navigation can check
    #: that the fragments it points at actually exist.
    document_ids: dict[str, set[str]] = field(default_factory=dict)

    #: Per-document ``{old_id: new_id}`` for ids that were not valid XML names.
    #: Navigation targets are fragments too, so they need the same remapping.
    id_map: dict[str, dict[str, str]] = field(default_factory=dict)

    def remap_fragment(self, target: str | None) -> str | None:
        if not target or "#" not in target:
            return target
        path, _, fragment = target.partition("#")
        renamed = self.id_map.get(path, {}).get(fragment)
        return f"{path}#{renamed}" if renamed else target

    def build_path_map(self) -> None:
        self.path_map = {
            (resource.original_path or resource.path): resource.path
            for resource in self.book.resources.values()
        }

    def remap(self, original_path: str) -> str | None:
        return self.path_map.get(original_path)


class Stage:
    """One transformation pass over the book."""

    name = "stage"

    def run(self, ctx: Context) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def note(self, ctx: Context, level: Level, message: str, location: str | None = None, detail: str | None = None):
        ctx.report.add(self.name, level, message, location, detail)


__all__ = ["Context", "Stage", "Level", "Policy", "Report", "Book"]
