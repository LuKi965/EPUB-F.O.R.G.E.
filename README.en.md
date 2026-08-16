<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Rebuilds any EPUB from scratch into a conforming EPUB 3.3 — while keeping the
book looking the way it looked.**

`0.2.28` · alpha · 2652 tests · **Windows**

[Install](#install) · [Usage](#usage) · [Modes](#three-modes) ·
[Limits](#limits) · [Changes](CHANGELOG.md)

[![Polski](https://img.shields.io/badge/Polski-informational?style=for-the-badge&logo=googletranslate&logoColor=white)](README.md)

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
> <div align="center"><img src="packaging/to-sie-zateguje.jpg" alt="Spokojnie, to się zateguje" width="380"></div>
>
> *("Spokojnie, to się zateguje" — roughly: relax, it'll sort itself out.)*
>
> In fairness, though: the tool **never overwrites its input**, the write is
> atomic (an interrupted run leaves no half-file), and replacing an existing
> output takes `--force`. That is not a guarantee — it is a list of things that
> are tested.

---

## What it does

An EPUB is a ZIP of XHTML documents, stylesheets and one file describing the
whole. Fifteen years of a dozen generators produced them, each a little
differently and none of them quite to the specification.

This tool **reads a book and builds it again.** It does not patch the input: it
builds a model in memory and writes a fresh EPUB 3.3 container from that. The
result is therefore conformant however broken the input was.

The first rule, checked on every book: **no character of the text is lost.** Not
"almost none" and not "the counts match" — every character of the source's
reading order has to be in the output, in the same order.

The second rule, just as important and more often surprising: **losing an
ornament damages the book too.** The italics the publisher chose, the rule
around an epigraph, the space before a chapter — that is content, not
decoration. So the program would rather keep a deviation from the specification
and describe it than remove it and change how the book looks.

## What this program will not do

Collected at the top, because it is the quickest way to find out whether it is
for you at all:

- **it does not remove DRM**, and it will not;
- **it does not convert from PDF, MOBI or Word** — a different job, deliberately
  out of scope;
- **it removes nothing without a question or a switch.** Anything this program
  ever deletes is either optional to untick or preceded by a question carrying
  the consequences and a recommendation;
- **it does not guess.** Where it does not know, it asks; with no answer,
  nothing changes.

## Three modes

| Mode | What it does | When |
|---|---|---|
| **Preserve appearance** (`preserve`) | full rebuild; repairs what is broken, keeps what the publisher chose | the default; for most books |
| **Enforce the standard** (`strict`) | the same, but conformance wins over appearance where they conflict | when the file is going out for distribution |
| **Container only** (`minimal`) | rebuilds the packaging, never opens a document | when only the structure needs repair |

Container-only mode makes **two** changes inside content, both of the same kind:
it swaps the old DOCTYPE for the EPUB 3 one, carrying the entities with it
(`&nbsp;` → `&#160;`), and fills an empty `<title>` from the document's own
heading. EPUB 2 allowed both, EPUB 3 allows neither — and this mode builds an
EPUB 3, so without them a book goes in valid and comes out invalid. Neither is
anything a reader sees on the page.

## Install

### Windows — no Python, no Java

From [releases](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases):

- **`EPUB-FORGE-x.y.z-setup.exe`** — installer, Start-menu shortcut
- **`EPUB-Forge-x.y.z-portable.zip`** — unpack and run, installs nothing

The installer carries everything the program needs: the EPUBCheck validator, the
engine that draws pages, and the dictionaries. Each pinned by SHA-256 — nothing
ships that this release has not measured.

### From source

```bash
git clone https://github.com/LuKi965/EPUB-F.O.R.G.E.
cd EPUB-F.O.R.G.E.
pip install -e .
```

Needs Python 3.10+. EPUBCheck (for validation) needs Java 11+ and fetches itself
on first use. Without the drawing engine and without dictionaries the program
still works — it does less, and **says in the report what it could not check**.

### About other systems, honestly

**Only Windows is released.** Nothing in the code ties it to Windows, the suite
passes on Linux and most of this program is written there — but **nobody checks
the result on Linux or macOS against real books and a real reading device**, and
that is the only kind of check that means anything here.

## Usage

### The window

```bash
epubforge-gui
```

Drag files in, pick a mode, run. The report appears beside the queue; **Save
batch report…** (Ctrl+Shift+S) writes the whole queue to one JSON file, worst
books first.

Everything this program can do is reachable from the window. It is not a
simplified front end to the command line.

### Command line

```bash
epubforge build book.epub                          # one book
epubforge build *.epub --output rebuilt/           # a whole shelf
epubforge build book.epub --strict --report r.json
epubforge build book.epub --report-language pl     # report in Polish
epubforge inspect book.epub                        # what is inside
epubforge compat                                   # what the profiles do
```

The exit code says what happened: `0` — written, `1` — not written, `2` —
written, with problems worth reading.

### Switches that remove something or change the look

All **off by default**, all reachable from the window:

| switch | what it does |
|---|---|
| `--remove-shop-notices` | removes the shop's visible sentences — order number, "purchased for", the buyer's address. The report prints **every removed sentence word for word**, not a count |
| `--relative-units` | rewrites font sizes from pixels into `rem`, so the reading device's own font setting reaches them |
| `--strict` | conformance wins over appearance where they conflict |
| `--remove-dead` | removes CSS rules and `<span>`s the analysis showed do nothing |

### Compatibility profiles

Optional and off by default. Each one only **adds** — a file, a declaration, an
old element — and none changes the look on a reader that follows the standard.

```bash
epubforge build book.epub --compat kindle,apple
```

`kindle` · `kobo` · `apple` · `legacy` (Adobe RMSDK: PocketBook, Nook, Sony)

## What it tells you about itself

Every run ends in a report where each change has its own line and its own
reason. Five levels: `ERROR`, `WARN`, `PRESERVED` (a deviation kept on purpose,
because removing it would change the look), `FIX`, `INFO`.

The report also says **what it could not check**: a missing validator, a missing
drawing engine and a missing dictionary are all named. A run that saw less has
no business looking like a clean book.

### Watermarks

Hidden shop markers are **tidied rather than removed** by default: repeated
inline styles become one rule and the token itself stays. Visible sentences — an
order number, the buyer's name — are **kept** by default, and since 0.2.28 can
be removed with a switch, with the full list of what went. That reverses an
earlier rule and does so deliberately: these are legally bought books, and such
a sentence can sit in the running text directly in front of a novel's first
sentence.

A publisher's colophon — address, telephone, ISBN — is **not** a watermark and
is never touched. That distinction is what the feature stands or falls on.

### When the program asks

A dead reference, a word cut by a conversion's hyphen (`obo-jętna`), a metadata
field that came out of the parser's guess rather than the file — each is a
question carrying the consequences, a recommendation, and whether it can be
undone. Answers are stored beside the book, so the same book does not ask twice.
Batch runs, the corpus and any library caller get the book untouched in those
places.

For hyphens the program only asks where it has **evidence**: either the book
itself spells the word without a hyphen elsewhere, or a dictionary says the
first half is not a word, so no such compound exists. `savoir-vivre` and
`czarno-czerwony` are never asked about.

## Limits

Things worth knowing before rather than after:

- **Alpha.** `0.2.x` **is** alpha: the feature set is settled and correctness is
  checked against 93 real books.
- **Beta needs a run, not code.** The `0.3.x` conditions are the owner's shelf,
  the public corpus and container fuzzing passing after every release, with the
  result recorded. The code is there; the run over the full shelf is not.
- **Strict mode can refuse to produce a file.** It asks EPUBCheck *before* the
  file takes its name and will not publish something the validator calls invalid
  — including when the defect arrived with the book. Measured over the whole
  public corpus: **17 books of 19 come out, 2 are refused**, both for defects
  that came from the source. A refusal **does not touch** the file already
  sitting under that name.
- **The appearance check can also stop the write, and is mandatory.** The
  program draws the pages before and after and compares them; where content is
  lost it writes nothing by default. Three states: off / report / stop.
- **The drawing engine is the bundled one only.** The program does not look for
  a browser on the machine — not in PATH, not in Program Files. The reason:
  comparing two drawings says something about the *book* only when the same
  engine made both; run against whatever a machine happens to have, it says
  something about the machine. Measured: Edge and Chromium disagreed about three
  of four kinds of damage. It costs the installer about 110 MB. One way in
  remains, for running from source where there is nothing bundled:
  `EPUBFORGE_CHROME`.
- **The report follows the interface language.** Window, JSON and console speak
  the language the interface does; on the command line `--report-language`
  decides. The English `message` always stays in the JSON, because that is the
  interface for scripts. What stays English is data, not sentences: tag names,
  metadata values and EPUBCheck's own messages.
- **The whole book goes into memory.** The program **works this out before it
  starts** — from the ZIP directory, without unpacking — and refuses rather than
  being killed by the kernel halfway. Across 32 books of the shelf the dearest
  comes to 104 MiB, so this guards a pathological case rather than getting in
  anybody's way. Switchable, with its own budget field.

## How it is checked

Over **2700 tests**, a few dozen of which skip where there is nothing to run
them against — no Java, no drawing engine, no dictionaries — and **say why**.
Five independent safety nets:

- **the K1 invariant** — all of the source's text must be in the output, in the
  same order;
- **the input→output balance** — what went in, what came out, and whether the
  ledger explains the difference. K1 watches the text; this watches everything
  else, because an image that vanishes quietly takes no letter with it and is
  invisible to K1;
- **the semantic oracle** — reads the package as a graph and catches the loss of
  a single item, value or edge;
- **the public corpus** — six real Project Gutenberg books and thirteen
  synthetic ones, with recorded signatures; a change to any rebuild fails the
  test for everybody, not just for the author;
- **no functional loss** — every setting must be reachable from the window or
  the command line, every checkbox in the window must set something, and every
  report rule must have an entry in both languages.

```bash
pytest -q                    # the whole suite
python tools/jak-ci.py       # the same, under the release machine's conditions
```

The second hides what the release machine does not have while it runs tests. It
exists because a release failed on two tests that passed locally: the suite was
measuring the machine rather than the program.

42 tests draw pages with a real browser and **skip by default** — they measure
the engine, not this program. Name an engine to run them:

```bash
EPUBFORGE_RENDER_TESTS=1 pytest -q          # plus EPUBFORGE_CHROME if needed
```

## Documentation

[`CHANGELOG.md`](CHANGELOG.md) says what changed and why — each release with its
reasoning rather than a list of commits.

The rest of the project's documents — the roadmap, the corpus write-up, results
on real hardware, the release archive, the K1–K12 rules — are kept privately.
Not because there is anything embarrassing in them, but because they describe
other people's books: somebody's paid-for copies, their defects and their
contents. This repository is public; those files are not for passers-by.

## Authors and licence

**Łukasz "LuKi" Kniotek** — concept, design, decisions and direction. The code
was written by language models under his direction and to his choices.

Copyright © 2026 Łukasz Kniotek.

**GNU GPL v3 or later.** You may use, study, change and redistribute it —
provided whatever you make of it is GPL too, with its source open. A closed
product built on this code is not permitted.

This program is distributed in the hope that it will be useful, but **WITHOUT ANY
WARRANTY**; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See [`LICENSE`](LICENSE) for details.

The application links LGPL libraries (Qt/PySide6, cssutils); their terms apply
independently and allow those libraries to be replaced in the built binary.
