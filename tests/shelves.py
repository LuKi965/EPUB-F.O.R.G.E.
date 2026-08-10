"""Every corpus shelf this repository records, and what one is.

A shelf is a folder holding `expected/` — one counts-only signature per book —
and a `runs.json` ledger beside it. The books themselves are never here: they
are somebody's paid-for copies and the signatures are hashes and counts, which
is what makes them safe to keep in a public repository at all.

There was one shelf for a long time and the tests said so in a hardcoded path.
Then a second arrived — 67 Dutch and English books out of Sigil, Word and
Calibre — and immediately found two defects the first could not, because the
first has no book carrying the HTML 3.2 `<body>` palette. A regression net
made of one kind of book only catches one kind of regression, which is the
whole argument of roadmap point [1] restated by experience.

So the shelves are enumerated rather than named. Adding a third is dropping a
folder in, and every ledger test picks it up.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

#: What each shelf is for, in one line, keyed by folder name. A shelf with no
#: entry here still counts — the tests enumerate folders, not this table — but
#: an unexplained pile of signatures is a pile nobody will dare change.
DESCRIBED = {
    "corpus": "the owner's Polish shelf: 93 books, mostly bought from Polish shops",
    "corpus_mixed": "67 Dutch and English books out of Sigil, Word and Calibre",
    "corpus_gutenberg": "six Project Gutenberg books the test suite builds itself",
}


def shelves() -> list[pathlib.Path]:
    """Every folder holding a ledger and its signatures, in a stable order."""
    return sorted(
        path
        for path in ROOT.iterdir()
        if path.is_dir() and (path / "runs.json").is_file() and (path / "expected").is_dir()
    )


def ledger(shelf: pathlib.Path) -> list[dict]:
    return json.loads((shelf / "runs.json").read_text(encoding="utf-8"))


def signatures(shelf: pathlib.Path) -> list[pathlib.Path]:
    return sorted((shelf / "expected").glob("*.json"))
