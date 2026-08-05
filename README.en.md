# EPUB F.O.R.G.E.

**F**actory for **O**verhauling and **R**enovating **G**litchy **E**PUBs

Rebuilds an arbitrary EPUB into a standards-clean **EPUB 3.3** without losing
what makes the book itself — cover, artwork, fonts, layout and typography.

*(Polska wersja: [`README.md`](README.md).)*

---

## Contents

1. [What it actually does](#what-it-actually-does)
2. [What it preserves](#what-it-preserves)
3. [What it repairs](#what-it-repairs)
4. [What it leaves alone](#what-it-leaves-alone)
5. [Modes](#modes)
6. [Reader compatibility](#reader-compatibility)
7. [Accessibility](#accessibility)
8. [Install](#install)
9. [Use](#use)
10. [The report](#the-report)
11. [How it is built](#how-it-is-built)
12. [Building the packaged app](#building-the-packaged-app)
13. [Limits](#limits)
14. [Development](#development)
15. [Authors and licence](#authors-and-licence)

---

## What it actually does

It does not patch the file you give it. It reads the book into a format-neutral
model, throws the original container away, and generates a new one: package
document, navigation, manifest, spine, filenames, ZIP layout.

That is not architectural decoration, it is the reason this works. Bookstore and
converter output fails in ways that resist patching: manifests listing files
that aren't there, spines pointing at missing ids, `<center>` and `<font>` from
a 2004 HTML converter, ids starting with a digit, undefined HTML entities in
files claiming to be XML, fonts obfuscated against an identifier nobody
recorded. A *repair* tool has to anticipate each case. A rebuild only has to
**read** each case — and the output is correct by construction rather than by
checklist.

The rule everything else follows from:

> Repair what is a **clear defect**. Keep what is a **publisher's decision**,
> however unusual. Where it cannot be told apart, appearance wins and the doubt
> goes in the report.

---

## What it preserves

Preservation is a hard requirement, not a best effort. Legacy markup is
**translated**, never deleted:

| Source | Output | Rendering |
|---|---|---|
| `<center>` | `<div style="text-align: center">` | identical |
| `<font color size face>` | `<span style="…">` | identical |
| `<table border cellspacing bgcolor>` | CSS equivalents on the element | identical |
| `<tt>` `<big>` `<strike>` | `<span>` with the matching CSS | identical |
| `<a name="x">` | `<a id="x">` | identical |
| obfuscated fonts | deobfuscated, `encryption.xml` dropped | identical |
| WebP / BMP / TIFF | PNG, references rewritten | identical |

### Watermarks

Retailer watermarks (*social DRM*) are **not removed** — that is between you and
the shop, not the tool. They are tidied, because as shipped they wreck the book
technically: a single token injected into a
`<div style="font-size:1px !important">` at the end of **every** document — 34
copies in one book measured here, 27 and 23 in two others.

The token text is never touched. What goes is the inline `!important` styling
repeated thirty-odd times, replaced by one rule, and the marker gains
`aria-hidden` so a screen reader stops spelling it out at the end of every
chapter. Human-readable protection notices — the ones meant to be read — are
recognised separately and left exactly as written.

---

## What it repairs

A separate category: things the browser discards anyway, so repairing them
**restores** the publisher's intent rather than overriding it.

- **`font-style: regular`** — not a CSS value, so parsers dropped the whole
  declaration. Replaced with `normal`.
- **`<p><img/></p>` under running-text rules** —
  `p { text-indent: 2%; text-align: justify }` written for prose was shifting
  cover and title artwork sideways and never centring it.
- **A block box directly inside an inline one** — a heading built as
  `<h1><a><span style="display:block">…</span></a></h1>`. The block splits the
  inline into anonymous boxes and margins start behaving unpredictably; the
  wrapper is promoted to `inline-block`.
- **Media types the manifest gets wrong**, such as the non-existent
  `application/x-font-ttf`.
- **Ids that are not valid XML names**, renamed along with every reference to
  them, including inside the table of contents.
- **Undefined entities** (`&nbsp;` and friends) in files declaring themselves as
  XML, which readers fail fatally on.

### How it knows a defect from a decision

The image-paragraph repair is the clearest example, because it is where
"fixing a defect" could so easily become "imposing a taste". Before an
image-only paragraph is centred, the CSS cascade is read:

- `p.ilustracja { text-align: right }` — the rule targets this paragraph by
  class, so it is a **decision about this image**. Obeyed.
- `body.cover { text-align: center }` — the rule targets the container and the
  alignment is inherited. Still a decision about where that artwork sits, so it
  is obeyed too; the image **is already** centred, and writing anything would be
  a fix reported for work not done.
- `p { text-align: justify }` — a rule written for prose that happens to land on
  artwork through inheritance. The paragraph is opted out of it.
- inline styles — always respected.
- a selector too complex to read unambiguously — treated as targeted. In doubt,
  the tool **does not touch it**.

Both properties — `text-align` and `text-indent` — are inherited, so the
nearest ancestor that says anything about them decides. Where the alignment was
chosen but a paragraph indent leaked in from a rule about running text, only
the indent goes and the alignment stays as written.

Books that style their illustrations deliberately therefore come out untouched;
only pages where nothing decided the alignment are centred. Across a 65-book
survey the rule stood aside 485 times and acted 54 — nine times more often it
does nothing at all.

---

## What it leaves alone

Things that are a publisher's **choice** — even a strange one — are kept and
reported as `preserved`:

- `div.dol { position: absolute; bottom: 0 }` pins a dedication to the foot of
  the page; that is a layout, not a defect. (Removed only under `strict`.)
- Reader-specific CSS hacks, `@media amzn-*`, `adobe-*` properties.
- Scripting — some fixed-layout books fall apart without it.
- Links to files the book never contained: the text survives, the defect is
  reported.

**DRM is not touched.** Real encryption is detected, refused and reported; only
font obfuscation, which is not DRM, is undone.

---

## Modes

Where conformance genuinely conflicts with appearance, the mode decides — and
every deviation is reported either way.

| Mode | What wins | What it does |
|---|---|---|
| **`preserve`** *(default)* | appearance | Repairs clear defects. Deviations that work are kept and logged as `preserved`. |
| **`strict`** | the specification | Dead links are unlinked (their text survives); Kindle-only `@media` blocks, `adobe-*` properties and out-of-flow positioning are dropped. |
| **`minimal`** | nothing | Only the container is regenerated: OPF, navigation, ZIP layout. XHTML and CSS come out **byte for byte** as they went in. |

Under `minimal` the XHTML and CSS stages do not run at all. Parsing a document
and writing it back changes its bytes even when nothing is wrong with it, so the
only way to keep that promise is not to open those files.

---

## Reader compatibility

The product of this tool is a standards-clean book. Some devices do not follow
the standard, and they do not fail loudly: the reader does not complain, it just
renders the book wrong — an empty table of contents, a cover that never appears,
chapters run together into one paragraph.

So the compatibility profiles are **opt-in and off by default**, and every one of
them only **adds**: a file, a declaration, a legacy element. None removes or
rewrites what the book already had, and none changes how a reader that follows
the specification renders it. That is the admission price — a concession that
could damage the book on correct software is not a concession, it is a
regression.

| Profile | Devices | What it adds |
|---|---|---|
| `kindle` | Amazon Kindle (Send-to-Kindle, KFX/KF8 conversion) | `<guide>`, HTML5 block stylesheet, legacy page-break spelling |
| `kobo` | Rakuten Kobo reading the EPUB directly | NCX, `<guide>`, HTML5 block stylesheet |
| `apple` | Apple Books (iOS, macOS) | `META-INF/com.apple.ibooks.display-options.xml` |
| `legacy` | Adobe RMSDK — PocketBook, Nook, Sony, older Kobo and Onyx | all of the above |

Why each one:

- **`<guide>`** — Amazon's converter and RMSDK-based readers look for the cover
  and the start-reading position there, not in the EPUB 3 navigation. The
  element is no longer part of EPUB 3.3, though EPUBCheck still accepts it: the
  file stays valid, but it carries something the specification dropped.
- **HTML5 block declarations** — RMSDK renders an element it does not know as
  inline, so a book built from `<section>` collapses into one running paragraph.
  The stylesheet is linked **ahead of** the book's own, so every rule the
  publisher wrote still wins.
- **`page-break-*`** — the modern fragmentation properties postdate these
  engines. The legacy spelling is inserted **before** the modern one, so in a
  current renderer the publisher's declaration still wins.
- **`specified-fonts`** — without this file Apple Books ignores every embedded
  face and substitutes its own. Written only when the book actually embeds
  fonts: declaring something that is not there would simply be untrue.

With all four profiles enabled the output still passes EPUBCheck with zero
errors and zero warnings, and a test pins that.

```bash
epubforge compat                       # what each profile does, why, and what it costs
epubforge build book.epub --compat kindle,apple
```

What this is **not**: a cure for a device that refuses to open a file at all.
That fault lies elsewhere and no profile will fix it.

The profiles are optional because in practice they are often unnecessary: on a
Kobo the full rebuild opens normally with **no profile at all** — measured, and
recorded in [`docs/URZADZENIA.md`](docs/URZADZENIA.md). Turn a profile on when
your device shows it needs one, not in advance.

---

## Accessibility

Since June 2025 the European Accessibility Act covers e-books, so accessibility
metadata is no longer optional. The tool emits **EPUB Accessibility 1.1**
declarations derived from what the book demonstrably contains:
`schema:accessMode`, `accessModeSufficient`, `accessibilityFeature`,
`accessibilityHazard` and a summary.

One rule governs all of it: **nothing is fabricated.** A tool that writes
`alternativeText` onto a book with no alt text has not improved accessibility —
it has manufactured a false claim and made the problem harder to find.
Therefore:

- `alternativeText` appears only when **every** image carries a real
  description;
- alt text that merely repeats the filename (`alt="title-1"`, `alt="cover"`) is
  detected and does **not** count as a description;
- the cover is described with the book's title, because the cover depicts the
  book;
- WCAG conformance is **never** asserted automatically — it cannot be
  established by machine, and under the EAA it is the publisher's statement. Use
  the explicit `--claim-conformance` flag.

Gaps that cannot be fixed mechanically — missing descriptions, skipped heading
levels, tables without header cells — are reported as work for a human.

---

## Install

### Windows — no Python, no Java

Grab `EPUB-FORGE-<version>-setup.exe` from the
[releases page](https://github.com/LuKi965/EPUB-F.O.R.G.E./releases), or the
portable `.zip`. Both ship the Python runtime, Qt, a minimal Java runtime and
EPUBCheck, so nothing has to be installed on the target machine. The installer
is per-user and never prompts for administrator rights.

Two programs are included: `EPUB-Forge.exe` (the window) and `epubforge.exe`
(the same tool on the command line).

### From source

```bash
pip install -e ".[gui]"
```

EPUBCheck is optional here: point `EPUBCHECK_JAR` at `epubcheck.jar`, or put
`epubcheck` on `PATH`.

---

## Use

```bash
epubforge build book.epub                        # next to the original
epubforge build ~/Books -o ~/Books/clean --check # a library, verified
epubforge survey ~/Books                         # what breaks across it, ranked
epubforge inventory ~/Books --json survey.json   # what the books are made of
epubforge build book.epub --strict -o clean.epub # conformance first
epubforge build book.epub --compat kobo          # concessions for one device
epubforge inspect book.epub                      # diagnose without writing
epubforge gui                                    # desktop interface
```

Useful flags: `--no-ncx`, `--strip-scripts`, `--drop-orphans`, `--keep-layout`,
`--keep-watermark-markup`, `--no-a11y-metadata`, `--claim-conformance wcag-aa`,
`--compat`, `--modified`, `--title/--author/--publisher/--series/--language`,
`--report out.json`, `-v`.

### Interface

Polish or English, switched under **Settings → Interface language** and
remembered between runs. Every option carries a tooltip describing what it does
to the book, not what the option is called. Light and dark themes follow the
system palette.

### As a library

```python
from epubforge import rebuild, Policy

result = rebuild("in.epub", "out.epub", Policy.preset("strict"))
print(result.report.to_text())
```

---

## The report

Every run accounts for what it did. Entries are one of `fix`, `preserved`,
`warn`, `error`, `info`. `--report` writes the same data as JSON.

```
fix        package        rebuilt the package from EPUB 2.0 to EPUB 3.3
fix        css            corrected 5 declarations using the invalid value 'regular'
fix        xhtml          centred 1 image-only paragraph and removed its text indent
preserved  css            kept 1 absolute/fixed position rule in a reflowable book
preserved  compat         added the EPUB 2 <guide> element for readers that look for it
warn       accessibility  2 images have alt text that only repeats the filename
```

### Sense of humour

The personality lives in the documentation and in the fixed text of the
interface, not in a running commentary. During work there is exactly one dry
remark, and it is rare: it appears only when a book turns up with **nothing** to
fix, which is unusual enough to deserve a raised eyebrow. Otherwise the tool
keeps quiet — a joke after every book stops being funny by the third one, and
one next to a warning is simply in the way.

---

## How it is built

```
read → fonts → images → structure → metadata → xhtml → css
     → navigation → accessibility → compatibility → write
```

Order is load-bearing and documented in `epubforge/stages/__init__.py`:

- **fonts before metadata** — deobfuscation is keyed on the *source* identifier,
  which normalisation may replace;
- **structure before content** — it freezes the path map href rewriting depends
  on;
- **accessibility before compatibility** — it must measure the book proper, not
  the device concessions layered on top;
- **compatibility last** — it is the one stage that deliberately steps away from
  the standard, and nothing earlier should have to know about it.

Layers: `reader.py` lowers any file into the model (`model.py`), the stages in
`stages/` transform it, `writer.py` raises it back into a container. Nothing in
the model knows about ZIP files or OPF syntax.

### Guarantees

Three properties of the output are checked as a whole, independently of what any
stage does. They have their own test file because they are a different category
from behaviour tests: a behaviour test says "this defect is repaired", these say
"whatever you add next, the output still has this property".

| | Property |
|---|---|
| **K1** | No readable character is lost. `<body>` content in spine order is identical before and after. |
| **K2** | The output is a function of the input. Two runs produce the same bytes — the one moving part, `dcterms:modified`, can be pinned with `--modified` or `SOURCE_DATE_EPOCH`. |
| **K3** | A second pass changes nothing. Idempotence at the level of file contents, not of file names. |

The full set of rules, each naming the test that enforces it, is in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

### Tests

```bash
pytest
```

The suite rebuilds a fixture carrying the damage described above and checks the
result — including, when EPUBCheck is installed, that `strict` validates with
zero errors and zero warnings, with every compatibility profile enabled too.

`epubforge survey` reports what breaks across a whole library, ranked by how many
books show each defect, writing nothing. Filenames are omitted unless
`--with-names` is passed.

`epubforge inventory` answers the prior question — what the books *are*: their
provenance (traces of Calibre, InDesign, Word, a PDF conversion, as a list rather
than one value, because files are layered), the damage they carry, and their
typographic conventions. A survey can only name defects the tool already knows
about; an inventory is what tells you which rules are worth writing. Output is
counts and character frequencies; `--map` writes the hash-to-filename mapping
separately and is the only file that names anything.

Regression against real books runs separately. They cannot go into a public
repository, so they live in a gitignored directory and only **metrics** are
committed: EPUBCheck counts, whether the text invariant held, the shape of the
report and the hash of the output — for `preserve` and `strict` separately.
Signatures are named by the book's hash rather than its title: the content never
leaked, but a list of titles in a public repository is the same class of
information the whole arrangement exists to keep local. The test skips itself
when the directory is absent. Details in [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Building the packaged app

Needs a JDK 17+ (for `jlink`) and `pip install pyinstaller`.

```bash
python packaging/build.py
python packaging/build.py --skip-java    # ~60 MB, no validation
python packaging/smoke_test.py
```

`smoke_test.py` clears `PATH`, `JAVA_HOME` and `EPUBCHECK_JAR` before running
the packaged executables, so it fails if the build quietly depends on the build
machine.

Windows installers are produced by `.github/workflows/build-windows.yml`. Push a
`v*` tag to release, or run the workflow by hand.

---

## Limits

- **DRM is not touched.** Real encryption is detected, refused and reported.
- Fixed-layout books keep their `rendition:*` properties, but their absolute
  positioning is not re-derived.
- Filenames are folded to ASCII, transliterating the letters Unicode cannot
  decompose (`okładka.png` → `okladka.png`, `Żółć.xhtml` → `Zolc.xhtml`). Links
  are rewritten to match.
- There is **no typography layer** — quotation marks, dashes, non-breaking
  spaces, mojibake. It is the one large category of converter damage the tool
  does not touch, deliberately scheduled last because it is the only thing that
  breaks the K1 guarantee. See [`docs/ROADMAP.md`](docs/ROADMAP.md).
- The whole book is held in memory. Irrelevant for one file, relevant for a
  batch counted in thousands.
- Report text is in English.

---

## Development

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the rules a new feature may not break,
  each naming the test that enforces it.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what comes next, in what order, and why
  that order.
- [`docs/KORPUS.md`](docs/KORPUS.md) *(Polish)* — how to put your own library to
  work without a single book leaving your disk.
- [`docs/URZADZENIA.md`](docs/URZADZENIA.md) *(Polish)* — the log of trials on
  real readers. A validator says whether a file conforms; it does not say
  whether a Kobo will open it.

### Version and maturity are different things

This is **pre-alpha**, and the program says so itself wherever it reports its
version:

```
epub-forge 0.1.7 (pre-alpha)
```

The number no longer tries to carry that information, because it cannot: a
figure climbing towards 1.0 reads as progress towards a release whatever anyone
intended. PATCH moves on every release, whatever it contains; MINOR moves only
when the maturity stage does, against written entry conditions.

| Stage | | |
|---|---|---|
| **pre-alpha** | `0.1.x` | prototype; works on the author's books, no corpus yet |
| **alpha** | `0.2.x` | verified against 30+ real books, report translated |
| **beta** | `0.3.x` | complete, used by somebody other than the author |
| **1.0** | | stable — full conditions in [`CONTRIBUTING.md`](CONTRIBUTING.md) |

In practice: the tool **never overwrites the source file**, and a test enforces
that — but keep your originals anyway. This is a prototype and it is labelled as
one.

---

## Authors and licence

- **Łukasz “LuKi” Kniotek** — concept, direction and requirements
- **Claude (Anthropic)** — design and implementation

MIT licensed — see [`LICENSE`](LICENSE), which also lists the licences of the
components bundled into the packaged builds.
