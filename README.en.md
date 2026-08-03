# EPUB F.O.R.G.E. - Factory for Overhauling and Renovating Glitchy EPUBs

Rebuilds an arbitrary EPUB into a standards-clean **EPUB 3.3** without losing what
makes the book itself — cover, artwork, fonts, layout and typography.

It does not patch the file you give it. It reads the book into a format-neutral model,
throws the original container away, and generates a new one: package document,
navigation, manifest, spine, filenames, ZIP layout. That is what makes the result
independent of however broken the input was.

*(Polska wersja: [`README.md`](README.md).)*

## Why rebuilding beats repairing

Bookstore and converter output fails in ways that resist patching: manifests listing
files that aren't there, spines pointing at missing ids, `<center>` and `<font>` from a
2004 HTML converter, ids starting with a digit, undefined HTML entities in files
claiming to be XML, fonts obfuscated against an identifier nobody recorded. A repair
tool has to anticipate each case. A rebuild only has to *read* each case — and the
output is correct by construction.

## What it preserves

Preservation is a hard requirement, not a best effort. Legacy markup is **translated**,
never deleted:

| Source | Output | Rendering |
|---|---|---|
| `<center>` | `<div style="text-align: center">` | identical |
| `<font color size face>` | `<span style="…">` | identical |
| `<table border cellspacing bgcolor>` | CSS equivalents on the element | identical |
| `<tt>` `<big>` `<strike>` | `<span>` with the matching CSS | identical |
| `<a name="x">` | `<a id="x">` | identical |
| obfuscated fonts | deobfuscated, `encryption.xml` dropped | identical |
| WebP / BMP / TIFF | PNG, references rewritten | identical |

## Repairing publisher errors

A separate category: things the browser discards anyway, so repairing them **restores**
the publisher's intent rather than overriding it.

- **`font-style: regular`** — not a CSS value, so parsers dropped the whole
  declaration. Replaced with `normal`.
- **`<p><img/></p>` under running-text rules** — `p { text-indent: 2%; text-align:
  justify }` written for prose was shifting cover and title artwork sideways and never
  centring it. Image-only paragraphs are opted out of both.
- **Media types the manifest gets wrong**, such as the non-existent
  `application/x-font-ttf`.
- **Ids that are not valid XML names**, renamed along with every reference to them,
  including inside the table of contents.

Things that are a publisher's **choice** — even an unusual one — are kept and reported.
`div.dol { position: absolute; bottom: 0 }` pins a dedication to the foot of the page;
that is a layout, not a defect.

## Accessibility

Since June 2025 the European Accessibility Act covers e-books, so accessibility
metadata is no longer optional. The tool emits **EPUB Accessibility 1.1** declarations
derived from what the book demonstrably contains: `schema:accessMode`,
`accessModeSufficient`, `accessibilityFeature`, `accessibilityHazard` and a summary.

One rule governs all of it: **nothing is fabricated.** A tool that writes
`alternativeText` onto a book with no alt text has not improved accessibility — it has
manufactured a false claim and made the problem harder to find. Therefore:

- `alternativeText` appears only when **every** image carries a real description;
- alt text that merely repeats the filename (`alt="title-1"`, `alt="cover"`) is
  detected and does **not** count as a description;
- the cover is described with the book's title, because the cover depicts the book;
- WCAG conformance is **never** asserted automatically — it cannot be established by
  machine, and under the EAA it is the publisher's statement. Use the explicit
  `--claim-conformance` flag.

Gaps that cannot be fixed mechanically — missing descriptions, skipped heading levels,
tables without header cells — are reported as work for a human.

## Conformance vs. appearance

- **`preserve`** (default) — appearance wins. Vendor CSS hacks, scripting and links to
  files the book never contained are kept, each logged as `preserved`.
- **`strict`** — the specification wins. Dead links are unlinked (their text survives),
  Kindle-only `@media` blocks, `adobe-*` properties and out-of-flow positioning are
  dropped. Produces a clean EPUBCheck run.
- **`minimal`** — container only. Content files pass through byte for byte.

## Install

### Windows — no Python, no Java

Grab `EPUB-Forge-<version>-setup.exe` from the
[releases page](https://github.com/LuKi965/EPUB-Forge/releases), or the portable `.zip`.
Both ship the Python runtime, Qt, a minimal Java runtime and EPUBCheck. The installer is
per-user and never prompts for administrator rights.

Two programs are included: `EPUB-Forge.exe` (the window) and `epubforge.exe` (the same
tool on the command line).

### From source

```bash
pip install -e ".[gui]"
```

EPUBCheck is optional here: point `EPUBCHECK_JAR` at `epubcheck.jar`, or put
`epubcheck` on `PATH`.

## Use

```bash
epubforge build book.epub                        # next to the original
epubforge build ~/Books -o ~/Books/clean --check # a library, verified
epubforge build book.epub --strict -o clean.epub # conformance first
epubforge inspect book.epub                      # diagnose without writing
epubforge gui                                    # desktop interface
```

Useful flags: `--no-ncx`, `--strip-scripts`, `--keep-orphans`, `--keep-layout`,
`--no-a11y-metadata`, `--claim-conformance wcag-aa`,
`--title/--author/--publisher/--series/--language`, `--report out.json`, `-v`.

## Interface

Polish or English, switched under **Settings → Interface language** and remembered
between runs. Every option carries a tooltip describing what it does to the book. Light
and dark themes follow the system palette.

## Report

Every run accounts for what it did: `fix`, `preserved`, `warn`, `error`, `info`.
`--report` writes the same data as JSON.

## As a library

```python
from epubforge import rebuild, Policy

result = rebuild("in.epub", "out.epub", Policy.preset("strict"))
print(result.report.to_text())
```

## Pipeline

```
read → fonts → images → structure → metadata → xhtml → css → navigation → accessibility → write
```

Order is load-bearing and documented in `epubforge/stages/__init__.py`.

## Building the packaged app

Needs a JDK 17+ (for `jlink`) and `pip install pyinstaller`.

```bash
python packaging/build.py
python packaging/smoke_test.py
```

`smoke_test.py` clears `PATH`, `JAVA_HOME` and `EPUBCHECK_JAR` before running the
packaged executables, so it fails if the build quietly depends on the build machine.

## Limits

- **DRM is not touched.** Real encryption is detected, refused and reported. Only font
  obfuscation — which is not DRM — is undone.
- Fixed-layout books keep their `rendition:*` properties, but their absolute
  positioning is not re-derived.
- Filenames are folded to ASCII. Polish `ł` has no Unicode decomposition and is dropped
  (`okładka.png` → `okadka.png`); links are rewritten to match.

## Tests

```bash
pytest
```

## Authors

- **Łukasz “LuKi” Kniotek** — concept, direction and requirements
- **Claude (Anthropic)** — design and implementation

MIT licensed — see [`LICENSE`](LICENSE), which also lists the licences of the
components bundled into the packaged builds.
