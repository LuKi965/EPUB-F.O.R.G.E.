# EPUB-Forge

Rebuilds an arbitrary EPUB into a standards-clean **EPUB 3.3** without losing what
makes the book itself — cover, artwork, fonts, layout and typography.

It does not patch the file you give it. It reads the book into a format-neutral
model, throws the original container away, and generates a new one: package
document, navigation, manifest, spine, filenames, ZIP layout. That is what makes
the result independent of however broken the input was.

## Why rebuilding beats repairing

Bookstore and converter output fails in ways that resist patching: manifests that
list files which aren't there, spines pointing at missing ids, `<center>` and
`<font>` from a 2004 HTML converter, ids starting with a digit, undefined HTML
entities in files claiming to be XML, fonts obfuscated against an identifier
nobody recorded. A repair tool has to anticipate each case. A rebuild only has to
*read* each case — and the output is correct by construction.

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

## Conformance vs. appearance

Where the two genuinely conflict, the mode decides — and every deviation is
reported either way.

- **`preserve`** (default) — appearance wins. Vendor CSS hacks, scripting and
  links to files the book never contained are kept, each logged as `preserved`.
  The book looks exactly as it did; some source defects remain conformance
  errors.
- **`strict`** — the specification wins. Dead links are unlinked (their text
  survives), Kindle-only `@media` blocks are dropped. Produces a clean EPUBCheck
  run.
- **`minimal`** — container only. Content files are passed through untouched;
  only the OPF, navigation and ZIP structure are regenerated.

## Install

```bash
pip install -e ".[gui]"
```

EPUBCheck is optional and used only for verification. Point `EPUBCHECK_JAR` at
`epubcheck.jar`, or put `epubcheck` on `PATH`.

## Use

```bash
# Rebuild one book next to the original
epubforge build book.epub

# A whole library into one folder, verified as it goes
epubforge build ~/Books -o ~/Books/clean --check

# Full conformance, appearance second
epubforge build book.epub --strict -o clean.epub

# What is wrong with this file, without writing anything?
epubforge inspect book.epub

# Desktop interface: drag books in, review the report, write them out
epubforge gui
```

Useful flags: `--no-ncx`, `--strip-scripts`, `--keep-orphans`, `--keep-layout`,
`--title/--author/--publisher/--series/--language`, `--report out.json`, `-v`.

## The report

Every run accounts for what it did. Findings are one of `fix` (a defect
corrected), `preserved` (a deviation kept on purpose), `warn`, `error`, or
`info`. `--report` writes the same data as JSON.

```
fix        fonts       deobfuscated 1 embedded font(s) and dropped META-INF/encryption.xml
fix        images      transcoded image/webp to PNG for universal reader support
fix        xhtml       converted legacy presentational markup to CSS
preserved  css         kept 1 vendor-specific at-rule(s) that target particular readers
warn       reader      spine referenced an unknown manifest id; the entry was dropped
```

## As a library

```python
from epubforge import rebuild, Policy

result = rebuild("in.epub", "out.epub", Policy.preset("strict"))
print(result.report.to_text())
```

## Pipeline

Stage order is load-bearing and documented in `epubforge/stages/__init__.py`.

```
read → fonts → images → structure → metadata → xhtml → css → navigation → write
```

`fonts` runs before `metadata` because deobfuscation is keyed on the *source*
identifier, which normalisation may replace. `structure` runs before `xhtml`
because it freezes the path map that href rewriting depends on.

## Limits

- **DRM is not touched.** Real encryption is detected, refused and reported.
  Only font obfuscation — which is not DRM — is undone.
- Fixed-layout books are carried through with their `rendition:*` properties
  intact, but their absolute positioning is not re-derived.
- Filenames are folded to ASCII. Polish `ł` has no Unicode decomposition and is
  dropped (`okładka.png` → `okadka.png`); links are rewritten to match.

## Tests

```bash
pytest
```

The suite rebuilds a fixture carrying the damage described above and asserts on
the result — including, when EPUBCheck is installed, that `--strict` output
validates with zero errors and zero warnings.
