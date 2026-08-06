"""Build the corpus family nobody can go out and buy: the edges.

The books themselves live in `epubforge/edge_cases.py`, in the package rather
than beside the tests, because the window builds them too — Corpus tab, "Dołóż
brzegi". That button is the way this gets done on a machine with an installer
and no checkout, which is the machine the corpus actually lives on.

This stays as the command line for the same job:

    python tools/make_edge_cases.py <folder>

One definition, two ways in. It used to be the *only* way in, and the family sat
empty for four releases while being named as the thing in the way.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from epubforge.edge_cases import EDGES, build_edges  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="where to write them")
    args = parser.parse_args()

    folder = pathlib.Path(args.folder)
    for path in build_edges(folder):
        size = path.stat().st_size / 1024**2
        with zipfile.ZipFile(path) as archive:
            entries = len(archive.namelist())
        what = EDGES[path.stem][1]
        print(f"{path.name:26s} {size:6.1f} MB  {entries:4d} wpisów   {what}")
    print(f"\n{len(EDGES)} książki w {folder}")
    print("Skopiuj je do katalogu korpusu i uruchom przebieg jak zwykle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
