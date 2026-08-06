"""Build the corpus family nobody can go out and buy: the edges.

`docs/ROADMAP.md` point 1 asks for three books at the limits — "brak okładki,
jeden plik 8 MB, 400 pozycji spine" — because memory and performance failures
surface there and nowhere else. Unlike every other family, these are not files
anyone owns: a publisher does not ship a book with four hundred chapters and no
cover. They have to be made, and making them by hand in an EPUB editor is an
afternoon of clicking for a result nobody can reproduce.

    python tools/make_edge_cases.py <folder>

The builders live in `tests/public_corpus.py` beside the other synthetic books,
and three of them are registered there so every test run exercises the edges.
This writes all four into a real corpus folder — including the nine-megabyte
one, which is about memory rather than correctness and has no business being
rebuilt on every test run.

The books are ordinary and valid apart from the one thing each is built to
stress. That is deliberate: a file that is broken in six ways tells you nothing
when it fails, because you cannot say which of the six did it.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests.public_corpus import (  # noqa: E402
    four_hundred_documents,
    no_cover,
    one_huge_image,
    single_document,
)


BOOKS = {
    "brzeg-bez-okladki": no_cover,
    "brzeg-wielka-grafika": one_huge_image,
    "brzeg-400-sekcji": four_hundred_documents,
    "brzeg-jeden-plik": single_document,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="where to write them")
    args = parser.parse_args()

    folder = pathlib.Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, build in BOOKS.items():
        path = build(folder / f"{name}.epub")
        size = path.stat().st_size / 1024**2
        with zipfile.ZipFile(path) as archive:
            entries = len(archive.namelist())
        print(f"{path.name:32s} {size:6.1f} MB  {entries:4d} wpisów")
    print(f"\n{len(BOOKS)} książki w {folder}")
    print("Skopiuj je do katalogu korpusu i uruchom przebieg jak zwykle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
