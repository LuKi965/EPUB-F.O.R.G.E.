<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Rebuilds any EPUB from scratch into a conforming EPUB 3.3 — while keeping the
book looking the way it looked.**

`0.2.10` · alpha · 970 tests · Windows / Linux / macOS

[Install](#install) · [Usage](#usage) · [Modes](#three-modes) ·
[Limits](#limits) · [Development](CONTRIBUTING.md) · [Changes](CHANGELOG.md)

*[Polska wersja](README.md)*

</div>

---

> ### ⚠️ Before you point this at your library
>
> This application was built with so-called **vibe coding** and may be — almost
> certainly is — potential **AI slop**. The authors are not responsible for the
> accidental self-destruction of any file it processes. Our principle is
> **it works on my machine, yours is your problem**. If you don't like it, sort
> it out yourself.
>
> <div align="center"><img src="docs/to-sie-zateguje.jpg" alt="Spokojnie, to się zateguje" width="380"></div>
>
> *("Spokojnie, to się zateguje" — roughly: relax, it'll sort itself out.)*
>
> In fairness, though: the tool **never overwrites its input**, the write is
> atomic (an interrupted run leaves no half-file), and replacing an existing
> output takes `--force`. That is not a guarantee — it is a list of things that
> are tested.

---

## What it does

An EPUB is a ZIP holding XHTML documents, stylesheets and one file describing
the whole. Fifteen years of a dozen generators produced them, each a little
differently and none of them quite to the specification.

This tool **reads a book and builds it again**: it reads what the source
actually declares, builds a model in memory, and writes a fresh, conforming
EPUB 3.3 container out of it. It does not patch the input — it writes a new
file. That is what makes the output correct however broken the input was.

The rule above all others, checked on every book: **no character of text is
lost**. Not "almost none" and not "the counts match" — every character of the
source's reading order has to appear in the output, in the same order.

## Three modes

| Mode | What it does | When |
|---|---|---|
| **Preserve appearance** (`preserve`) | full rebuild; fixes what is broken, leaves what the publisher decided on purpose | the default, for most books |
| **Force the standard** (`strict`) | the same, but conformance wins where the two conflict | when the file is going out to a shop |
| **Container only** (`minimal`) | rebuilds the packaging, never opens the documents | when only the structure needs fixing |

Container-only mode makes exactly **one** change inside a document: it replaces
a legacy DOCTYPE with the EPUB 3 one, carrying the entities with it
(`&nbsp;` → `&#160;`). Without that the output is not a valid EPUB 3, and a book
whose entity has been stranded will not open at all. A DOCTYPE says nothing
about how a page renders, which makes this the one edit that cannot change what
the reader sees.

## Install

### Windows — no Python, no Java

From [releases](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases):

- **`EPUB-FORGE-x.y.z-setup.exe`** — installer, Start menu entry
- **`EPUB-Forge-x.y.z-portable.zip`** — unzip and run, installs nothing

### From source

```bash
git clone https://github.com/LuKi965/EPUB-F.O.R.G.E.
cd EPUB-F.O.R.G.E.
pip install -e .
```

Python 3.10+. EPUBCheck (optional, for validation) needs Java 11+ and fetches
itself on first use.

## Usage

### Window

```bash
epubforge-gui
```

Drop files in, pick a mode, run. The report appears beside the queue; **Save
batch report…** (Ctrl+Shift+S) writes the whole queue to one JSON file, worst
books first.

### Command line

```bash
epubforge build book.epub                      # one book
epubforge build *.epub --output rebuilt/       # a whole shelf
epubforge build book.epub --strict --report r.json
epubforge inspect book.epub                    # what is inside
epubforge compat                               # what the profiles do
```

The exit code says what happened: `0` written, `1` not written, `2` written but
carrying problems worth reading.

### Compatibility profiles

Optional and off by default. Each one only **adds** — a file, a declaration, a
legacy element — and none changes how a conforming reader renders the result.

```bash
epubforge build book.epub --compat kindle,apple
```

`kindle` · `kobo` · `apple` · `legacy` (Adobe RMSDK: PocketBook, Nook, Sony)

## What it tells you about itself

Every run ends in a report where each change has its own line and its own
reason. Five levels: `ERROR`, `WARN`, `PRESERVED` (a deviation kept on purpose,
because removing it would change the rendering), `FIX`, `INFO`.

Watermarks and publisher marks are **not removed** — they are tidied where they
repeat in every chapter, and they stay.

## Limits

Things worth knowing before rather than after:

- **Alpha.** One of the three entry conditions is still unmet, and what it
  needs is time. Coverage of the generator families is **closed**: 93 books,
  all ten families, the run clean — zero EPUBCheck errors, no text lost. What
  remains is three consecutive releases with green corpus metrics, and the
  count stands at **one** (0.2.7): 0.2.6 re-run over the full corpus produced
  fourteen errors, so it started again. The other two — no known defects that
  lose data silently, and a translated report — have been met since 0.2.2 and
  0.2.5 respectively.
- **The report follows the language setting.** The window, the JSON file and
  the console all speak whatever the interface does; on the command line
  `--report-language` decides. The English `message` stays in the JSON either
  way, because that is the field scripts match on. This covers the detail
  paragraph under a finding too. What stays English is data rather than
  sentences: tag names, metadata values and EPUBCheck's own output.
- **No conversion from PDF, MOBI or Word.** Different problem — see
  [`docs/ROADMAP.md`](docs/ROADMAP.md), item 10.
- **No DRM removal**, and there will not be.
- **The whole book is held in memory.** With a large library and several
  processes at once, that is noticeable.

## How it is checked

879 tests, including three independent safety nets:

- **a semantic oracle** — reads the package as a graph and catches the loss of a
  single instance, value or edge;
- **a public corpus** — six real Project Gutenberg books and nine synthetic
  ones with recorded signatures, so a change in what the rebuild produces fails
  for everybody rather than only for the author;
- **the K1 invariant** — all of the source's text must be in the output, in
  order.

```bash
pytest -q
```

## Documentation

| File | About |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | rules K1–K12, versioning, how a release is made |
| [`CHANGELOG.md`](CHANGELOG.md) | what changed and why |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | what is next and what is deliberately out of scope |
| [`docs/URZADZENIA.md`](docs/URZADZENIA.md) | results on real hardware |
| [`docs/archive/`](docs/archive/) | the previous version of this file, with the full design rationale |

## Authors and licence

Łukasz "LuKi" Kniotek, with considerable help from language models — see the
paragraph about vibe coding above.

MIT. Do what you like with it; if you break something, that is yours.
