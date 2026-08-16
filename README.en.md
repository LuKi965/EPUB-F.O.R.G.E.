<div align="center">

<img src="packaging/epubforge.png" alt="EPUB F.O.R.G.E." width="128" height="128">

# EPUB F.O.R.G.E.

**Rebuilds any EPUB from scratch into a conforming EPUB 3.3 — while keeping the
book looking the way it looked.**

`0.2.27` · alpha · 2475 tests · **Windows**

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

Container-only mode makes **two** changes inside a document, and they are the
same kind of change twice: it replaces a legacy DOCTYPE with the EPUB 3 one,
carrying the entities with it (`&nbsp;` → `&#160;`), and it fills an empty
`<title>` from the document's own heading. EPUB 2 allowed both; EPUB 3 allows
neither, and this mode rebuilds the package as EPUB 3 — so without the two
repairs a book goes in valid and comes out invalid. Neither a DOCTYPE nor a
`<title>` is rendered in the body, so neither edit can change what the reader
sees.

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

Where the program does not know, it **asks instead of guessing**. A dead link, a
word a conversion cut in half with a hyphen (`wybo-rowy`), and a metadata field
that came out of the parser's guess rather than out of the file — each is a
question with the consequence of every answer spelled out, a recommendation, and
whether it can be undone. **Without an answer nothing changes**, and answers are
stored beside the book, so the same book does not ask twice. Batch runs, the
corpus and every library caller get a book untouched in those places.

## Limits

Things worth knowing before rather than after:

- **Alpha.** The version is `0.2.x`, and `0.2.x` **is** alpha — that is what
  the maturity table in the project's documentation says, and what
  every build since 0.2.0 has said in its own title bar, which reads the stage
  from the code. This paragraph spent several releases claiming we were still
  on our way into alpha, next to a binary labelled `alpha`. The feature set is
  settled and correctness is checked against 93 real books, which is that
  table's definition of the stage.
- **One thing left before beta, and it cannot be written.** Beta (`0.3.x`)
  asked for the book profile, the CSS clean-up and span consolidation: those
  three shipped in 0.2.11, 0.2.14 and 0.2.14. What remains is the fourth
  condition — **somebody other than the author putting their own library
  through it.**
- **The report follows the language setting.** The window, the JSON file and
  the console all speak whatever the interface does; on the command line
  `--report-language` decides. The English `message` stays in the JSON either
  way, because that is the field scripts match on. This covers the detail
  paragraph under a finding too. What stays English is data rather than
  sentences: tag names, metadata values and EPUBCheck's own output.
- **Strict mode can refuse to publish, from 0.2.23.** It asks EPUBCheck
  *before* the file takes its name and will not publish something the validator
  calls invalid — including when the defect arrived with the book and this
  program did not make it. Measured on 0.2.27, the whole public corpus with the
  validator on: **17 books of 19 come out, 2 are refused** — one for a
  fixed-layout document with no `viewport`, one for Media Overlays class names
  with no stylesheet, and both defects arrived with the source. A refusal
  **never touches** the file already at that name. Preserve
  and minimal publish and report as before; the choice is in the window and
  under `--gate`.
- **The appearance check can stop a write too, from 0.2.24, and it is
  mandatory.** The program draws the pages before and after the rebuild and
  compares them; where content is lost it writes nothing by default. Three
  states: off / report / stop.
- **From 0.2.26 the installer carries its own drawing engine** —
  `chrome-headless-shell`, pinned by SHA-256 exactly as EPUBCheck is. It is not
  a browser: there is no interface compiled into it, so it **has nothing to open
  a window with**. Until 0.2.25 the program looked for Chrome or Edge on the
  machine, which was wrong twice over: Edge could open an empty window, and the
  check's answer depended on which browser you happened to have — measured, Edge
  and Chromium disagreed about three of four kinds of damage. It costs about
  110 MB of installer. **From 0.2.28 no browser is looked for on the machine at
  all** — not the `PATH`, not Program Files, not Playwright's downloads, and no
  environment variable can put anything in front of the carried engine. That
  whole apparatus existed for one reason: there was no engine of our own. A
  comparison of two renderings says something about the *book* only if the same
  engine drew both; run against whatever a machine happens to have, it says
  something about the machine. One door is left, for running from source where
  there is nothing to carry: `EPUBFORGE_CHROME`.
- **It does not convert from PDF, MOBI or Word.** That is a different job
  and deliberately out of scope.
- **No DRM removal**, and there will not be.
- **The whole book is held in memory.** With a large library and several
  processes at once, that is noticeable. Since 0.2.24 the program **works it
  out before it starts** — from the ZIP directory, without unpacking — and
  refuses rather than being killed by the kernel halfway through. Across the
  32 books on the shelf the most expensive comes out at 104 MiB, so this is a
  safeguard for a pathological case rather than a threshold anybody will walk
  into. Switchable off, with its own budget field.

## How it is checked

2475 tests, including four independent safety nets:

- **a semantic oracle** — reads the package as a graph and catches the loss of a
  single instance, value or edge;
- **a public corpus** — six real Project Gutenberg books and nine synthetic
  ones with recorded signatures, so a change in what the rebuild produces fails
  for everybody rather than only for the author;
- **the K1 invariant** — all of the source's text must be in the output, in
  order;
- **an input→output balance** — from 0.2.25: what went in, what came out, and
  whether the change ledger accounts for the difference. K1 watches the text;
  this watches everything else — an image that quietly disappears takes not one
  letter with it, and is therefore invisible to K1.

```bash
pytest -q
```

42 of them draw pages with a real browser and **skip by default**: they measure
an engine rather than this program, so run against whatever browser a machine
happens to have they measure the machine. Name the engine to run them:

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
