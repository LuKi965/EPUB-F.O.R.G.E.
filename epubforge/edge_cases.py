"""The corpus family nobody can go out and buy: the edges.

`docs/ROADMAP.md` point [1] asks for three books at the limits — no cover, one
image of 8 MB, four hundred spine items — because memory and performance
failures surface there and nowhere else. Unlike every other family these are not
files anyone owns: no publisher ships a book with four hundred chapters and no
cover, so they have to be made.

This lives in the package rather than beside the tests, and that is the point.
It began as `tools/make_edge_cases.py` importing from `tests/public_corpus.py` —
a command line, on a machine with a checkout and a Python. The one person who
can fill this family runs Windows and the installer, where neither exists, so
the instruction "just run the script" was an instruction to do nothing. A corpus
family that can only be filled by somebody with a development environment is a
family that stays empty.

The books are ordinary and valid apart from the one thing each is built to
stress. That is deliberate: a file broken in six ways tells you nothing when it
fails, because you cannot say which of the six did it.

Generation is byte-deterministic — fixed ZIP timestamps, fixed host-system byte,
no clock and no randomness except the incompressible payload, which is what that
one book is *for*. Two runs on two machines produce the same signature, which is
the only thing that makes a recorded signature worth keeping.
"""

from __future__ import annotations

import os
import pathlib
import zipfile

#: The epoch `writer.py` uses. Without it the hash changes every run and a
#: recorded signature is worthless.
EPOCH = (1980, 1, 1, 0, 0, 0)

#: `zipfile` stamps every entry with the platform it ran on — 0 for Windows,
#: 3 for everything else. A corpus generated on Windows hashed differently from
#: one generated on Linux, every book came back "new", and the regression net
#: proved nothing. Pinned, so the edges are the same file everywhere.
CREATE_SYSTEM = 3

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

#: 1×1 PNG. Small enough to be noise, real enough for an image library to open.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def page(title: str, body: str, *, lang: str = "pl", head: str = "") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}">
<head><meta charset="utf-8"/><title>{title}</title>{head}</head>
<body>{body}</body>
</html>
"""


def nav(entries: list[tuple[str, str]], *, lang: str = "pl") -> str:
    items = "".join(f'<li><a href="{href}">{label}</a></li>' for href, label in entries)
    return page("Spis treści", f'<nav epub:type="toc"><ol>{items}</ol></nav>', lang=lang)


def opf(*, metadata: str = "", manifest: str, spine: str, spine_attrs: str = "",
        version: str = "3.0", title: str = "Książka", lang: str = "pl",
        identifier: str = "urn:uuid:00000000-0000-4000-8000-000000000001") -> str:
    modified = (
        '    <meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>\n'
        if version == "3.0" else ""
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="pub-id">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>{lang}</dc:language>
    <dc:creator>Autor Testowy</dc:creator>
{modified}{metadata}  </metadata>
  <manifest>
{manifest}  </manifest>
  <spine{spine_attrs}>
{spine}  </spine>
</package>
"""


def write(path: pathlib.Path, entries: "dict[str, bytes | str]") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        first = zipfile.ZipInfo("mimetype", date_time=EPOCH)
        first.compress_type = zipfile.ZIP_STORED
        first.create_system = CREATE_SYSTEM
        archive.writestr(first, b"application/epub+zip")
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = CREATE_SYSTEM
            archive.writestr(info, data.encode("utf-8") if isinstance(data, str) else data)
    return path


def item(identifier: str, href: str, media_type: str, properties: str = "") -> str:
    extra = f' properties="{properties}"' if properties else ""
    return f'    <item id="{identifier}" href="{href}" media-type="{media_type}"{extra}/>\n'


# ------------------------------------------------------------------- books

def no_cover(path: pathlib.Path) -> pathlib.Path:
    """A book with no cover image and nothing claiming to be one.

    Every reader shows *something* in a library list, so the question is what
    this program does when there is nothing to show it — and whether it invents
    a cover, which would be adding to somebody's book.
    """
    pages = {
        f"text/ch{i}.xhtml": page(f"Rozdział {i}", f"<h1>Rozdział {i}</h1><p>Treść.</p>")
        for i in range(1, 4)
    }
    manifest = "".join(
        item(f"ch{i}", f"text/ch{i}.xhtml", "application/xhtml+xml") for i in range(1, 4)
    )
    manifest += item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    spine = "".join(f'    <itemref idref="ch{i}"/>\n' for i in range(1, 4))
    return write(path, {
        "META-INF/container.xml": CONTAINER,
        "EPUB/package.opf": opf(manifest=manifest, spine=spine, title="Bez okładki"),
        "EPUB/nav.xhtml": nav([(f"text/ch{i}.xhtml", f"Rozdział {i}") for i in range(1, 4)]),
        **{f"EPUB/{name}": body for name, body in pages.items()},
    })


def one_huge_image(path: pathlib.Path, megabytes: int = 9) -> pathlib.Path:
    """A single image larger than most whole books.

    The model holds every resource as bytes, so this is the shape that turns a
    comfortable rebuild into an uncomfortable one. Nine megabytes is over the
    eight the roadmap names and small enough to keep on a disk somebody uses.
    """
    # Incompressible on purpose: noise, so the archive is as large as the file.
    payload = PNG + os.urandom(megabytes * 1024 * 1024)
    manifest = (
        item("plate", "images/plate.png", "image/png", "cover-image")
        + item("ch1", "text/ch1.xhtml", "application/xhtml+xml")
        + item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    )
    return write(path, {
        "META-INF/container.xml": CONTAINER,
        "EPUB/package.opf": opf(
            manifest=manifest,
            spine='    <itemref idref="ch1"/>\n',
            title="Jedna wielka plansza",
        ),
        "EPUB/nav.xhtml": nav([("text/ch1.xhtml", "Plansza")]),
        "EPUB/text/ch1.xhtml": page(
            "Plansza", '<p><img src="../images/plate.png" alt="Plansza"/></p>'
        ),
        "EPUB/images/plate.png": payload,
    })


def four_hundred_documents(path: pathlib.Path, count: int = 400) -> pathlib.Path:
    """Four hundred spine items, where per-document work stops being free.

    Anything the rebuild does once per document — parsing, cascade resolution,
    rewriting every href — is multiplied here, and a cost that hides at thirty
    documents does not hide at four hundred.
    """
    entries: "dict[str, bytes | str]" = {}
    manifest = ""
    spine = ""
    toc: list[tuple[str, str]] = []
    for index in range(1, count + 1):
        name = f"text/s{index:04d}.xhtml"
        entries[f"EPUB/{name}"] = page(
            f"Sekcja {index}",
            f"<h1>Sekcja {index}</h1><p>Krótki akapit numer {index}.</p>",
        )
        manifest += item(f"s{index:04d}", name, "application/xhtml+xml")
        spine += f'    <itemref idref="s{index:04d}"/>\n'
        if index <= 40:  # A table of contents nobody would write in full.
            toc.append((name, f"Sekcja {index}"))
    manifest += item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    entries["META-INF/container.xml"] = CONTAINER
    entries["EPUB/package.opf"] = opf(
        manifest=manifest, spine=spine, title="Czterysta sekcji"
    )
    entries["EPUB/nav.xhtml"] = nav(toc)
    return write(path, entries)


def single_document(path: pathlib.Path, paragraphs: int = 4000) -> pathlib.Path:
    """The opposite edge: one document holding the whole book.

    A back-conversion or a scan-to-EPUB often produces this, and it is the case
    where nothing can be split, skipped or streamed — the whole text is one
    parse.
    """
    body = "<h1>Całość</h1>" + "".join(
        f"<p>Akapit numer {i}, wypełniający tekst o umiarkowanej długości.</p>"
        for i in range(1, paragraphs + 1)
    )
    manifest = (
        item("all", "text/all.xhtml", "application/xhtml+xml")
        + item("nav", "nav.xhtml", "application/xhtml+xml", "nav")
    )
    return write(path, {
        "META-INF/container.xml": CONTAINER,
        "EPUB/package.opf": opf(
            manifest=manifest, spine='    <itemref idref="all"/>\n', title="Jeden plik"
        ),
        "EPUB/nav.xhtml": nav([("text/all.xhtml", "Całość")]),
        "EPUB/text/all.xhtml": page("Całość", body),
    })


#: What each book is at the limit of, keyed by the name it gets on disk. The
#: description is shown in the window, so somebody who finds four unfamiliar
#: files in their corpus folder can tell what they are for.
EDGES: "dict[str, tuple[object, str, str]]" = {
    "brzeg-bez-okladki": (
        no_cover, "brak okładki", "no cover image and nothing claiming to be one",
    ),
    "brzeg-wielka-grafika": (
        one_huge_image, "jedna grafika 9 MB", "a single 9 MB image, larger than most books",
    ),
    "brzeg-400-sekcji": (
        four_hundred_documents, "400 pozycji spine", "four hundred spine items",
    ),
    "brzeg-jeden-plik": (
        single_document, "cała książka w jednym pliku", "the whole book in one document",
    ),
}


def build_edges(folder: "pathlib.Path | str") -> list[pathlib.Path]:
    """Write all four into *folder* and return the paths, sorted.

    Overwrites by name, so running it twice leaves four files rather than
    eight — the corpus counts books, and a duplicate would inflate a family
    that is being filled precisely because it is short.
    """
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(build(folder / f"{name}.epub") for name, (build, _, _) in EDGES.items())
