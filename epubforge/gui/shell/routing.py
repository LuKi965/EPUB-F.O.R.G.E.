"""Which module a file belongs to, decided once.

The window used to have one answer — everything went to the rebuild — and the
converter was reached by dropping a PDF on the rebuild's own drop zone. That is
the arrangement D-057 ends: a file is *classified*, and the classification says
which job it starts.

No Qt here on purpose: what kind of file something is has nothing to do with
widgets, and this way the routing table is testable as a table.
"""

from __future__ import annotations

import pathlib

#: Route name → the suffixes that belong to it. The two modules' own lists,
#: in one place, so a drop zone and a file dialog cannot disagree.
ROUTES = {
    "rebuild": (".epub",),
    "pdf": (".pdf",),
}


def route_for(path) -> str:
    """Which module reads *path*: `"rebuild"`, `"pdf"`, or `""` for neither.

    By suffix, and deliberately: this decides *where a person is taken*, and a
    person who names a file has said what they think it is. Whether it really
    is one is the reading module's question, and it answers it by refusing.
    """
    name = str(path).lower()
    for route, suffixes in ROUTES.items():
        if name.endswith(suffixes):
            return route
    return ""


def sort_out(paths) -> "dict[str, list[pathlib.Path]]":
    """Split a mixed set of files by the module each belongs to.

    Every route is a key, always, including the empty one — a caller reporting
    "3 EPUB, 2 PDF, 1 nieobsługiwany" should not have to guess which keys it
    got. Order within each list is the order they arrived in.
    """
    sorted_out: "dict[str, list[pathlib.Path]]" = {route: [] for route in ROUTES}
    sorted_out[""] = []
    for path in paths:
        sorted_out[route_for(path)].append(pathlib.Path(path))
    return sorted_out


def every_suffix() -> "tuple[str, ...]":
    """Everything either module reads, for a drop zone that accepts both and
    then asks which is which."""
    return tuple(suffix for suffixes in ROUTES.values() for suffix in suffixes)
