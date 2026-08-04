# Changelog

The scheme is `0.MINOR.PATCH`. **MINOR** goes up when the tool does something
new or different that a user would notice — a stage, a flag, a change in what
the output contains. **PATCH** covers everything else, defect fixes included:
the number describes the scope of a change, not its importance. Importance is
what this file is for.

MINOR is not a decimal fraction. 0.9 is followed by 0.10, then 0.11, and 0.42 is
a perfectly ordinary version of this program. Reaching 1.0 is not something that
happens by counting — the conditions for it are listed in `CONTRIBUTING.md`, and
they are about the corpus, the invariants and the API, not about the tally.

The version lives in `epubforge/__init__.py` and is the single source for
`pyproject.toml`, `epubforge --version`, the window title and the Windows
installer — bump it there and everything follows.

## 0.8.1

A second audit, and a pattern worth naming: four of the five serious defects
found across both audits have the same shape — **the code asked the source
about something the source is under no obligation to be truthful about, or did
not ask everything it could have.** That is now K11 in `CONTRIBUTING.md`, the
sibling of K4: K4 governs what the tool claims on the way out, K11 what it
believes on the way in.

This release is a PATCH under the versioning rule adopted here: it repairs
defects and strengthens tests without changing what the tool sets out to do.

### Fixed
- **The archive size limits could be bypassed by lying.** They read
  `file_size` and `compress_size` from the ZIP header, which is not a fact
  about the archive — it is whatever its author wrote there. Patch the field
  and the guard waves the entry through; the decompressor then produces the
  real payload, and the CRC check that eventually complains only runs after the
  memory has already been allocated. Measured here: a 300 MiB entry declaring
  itself as 1000 bytes cost **601.7 MiB** of peak allocation, and a 10 GB one
  would have killed the process before anything noticed.

  The ceiling is now enforced while decompressing, in chunks, so the same file
  is refused at **2.6 MiB**. The header check stays as a cheap first pass — an
  archive that admits to holding a 300 MiB entry is still turned away without
  reading a byte — but it is no longer the only one.
- **The series number could come from the wrong collection.** EPUB 3 allows a
  book to belong to several: the seventh Chronicle, published inside a boxed
  set as part one. The 0.8.0 fix separated a `set` from a `series` by *name*,
  but the number was still taken from whichever `group-position` appeared
  first, so that book came out as "Chronicles, volume 1". Collections are now
  resolved whole, and the number comes from the collection the name came from.
  This was a regression introduced by the previous fix.
- **The K1 helper silently skipped documents.** It selected content by file
  extension and excluded navigation by looking for "nav" in the filename.
  Neither is a fact about an EPUB: the manifest decides what a content document
  is, `.xml` occurs in the wild, and a chapter called
  `navigare-necesse-est.xhtml` is a chapter. Both guesses failed in the same
  direction — they *excluded* real content, so the invariant covered less of
  the book and still passed. On fixtures whose names we chose that could never
  surface; on a corpus of real books it would have happened constantly and
  silently. Documents now come from container.xml → package document →
  manifest and spine, with navigation recognised by `properties="nav"`.

### Changed
- Corpus signatures are named by the book's hash instead of its title. The
  content never leaked, but `autor - Ostatnie życzenie.json` in a public
  repository leaks the shelf, which is the same class of information the
  arrangement exists to keep local. It also survives renaming a file on disk,
  which previously orphaned its signature without a trace.
- Corpus signatures measure `preserve` as well as `strict`. `preserve` is what
  users actually get by default, and it was the one mode nothing watched.
- `--record` now prints a field-level diff before overwriting. "12 books gained
  a css warning" is something you can review; "40 hashes changed" is not.

## 0.8.0

An external audit found two defects that had gone unnoticed through 154 tests.
Both share a shape worth naming: they corrupted **data** without changing the
**shape** of the output — same files, same counts, same validator verdict. No
behaviour test was ever going to catch that, so the suite gained a category
that can: `tests/test_invariants.py`, which asserts properties of the whole
output rather than individual repairs.

### Fixed
- **The series number was lost on the second pass.** `group-position` is, by
  definition, always a refinement of the collection it numbers — there is
  nothing else for it to point at — and the reader skipped every refinement
  before reaching the branch that handles it. The branch was unreachable code.
  A book rebuilt once kept its series number; rebuilt twice, it lost it,
  because the first pass had already moved the number from
  `calibre:series_index` to the EPUB 3 spelling.
- **A book with no alt text at all came out claiming it had some.** The content
  stage supplies `alt=""` where an image has none, and recorded in the run's
  context that it had done so; the accessibility stage read that note and
  correctly withheld `alternativeText`. But the note lived only inside one run,
  and the output goes to disk and comes back. On a second pass the same empty
  alt was indistinguishable from a publisher's deliberate one, so the book was
  declared to have alternative text it does not have. Under the European
  Accessibility Act that is not cosmetic.

  The repair is not to remember harder. An empty alt asserts "this image is
  decorative" and nothing here can verify that, so it no longer counts as a
  description at all — only `role="presentation"` or `aria-hidden="true"`, which
  somebody wrote deliberately, does. That over-reports on books using an empty
  alt correctly, which is the safe direction, and the report says exactly why.
- **The output was not byte-reproducible.** `container.xml` and the package
  document were written through a code path that stamps the wall clock, while
  every other entry carried a fixed timestamp. Two runs on the same input
  produced different files. All entries are now written the same way.
- A collection of type `set` — a boxed edition — was recorded as a series.

### Added
- `tests/test_invariants.py`: K1 no readable character is lost, K2 the output
  is a function of the input, K3 a second pass changes nothing. The third would
  have caught both defects above; the weaker idempotency test it replaces
  compared file *names* and passed while the data changed underneath.
- `Policy.modified_override`, `--modified` and `SOURCE_DATE_EPOCH`, which pin
  `dcterms:modified`. With every ZIP timestamp already fixed, that was the last
  moving part: the output is now byte-identical across runs, and a test proves
  it.
- Ceilings on what an archive may expand to — per entry, in total, and by
  compression ratio. The whole book is held in memory by design and files
  arrive by drag-and-drop, so an archive must not be able to ask for unbounded
  allocation. The limits sit far above any real book and a test asserts that
  ordinary content is never refused.
- `tests/test_corpus.py`: regression against real books without putting anyone's
  book in the repository. The books stay in a gitignored directory; only a small
  metric signature per book is committed — EPUBCheck counts, whether the text
  invariant held, the report's shape and the output hash. The module skips
  itself when the directory is absent.
- `CONTRIBUTING.md` — the rules a new feature may not break, each naming the
  test that enforces it — and `docs/ROADMAP.md`, which records what comes next,
  in what order, and the four places where we deliberately departed from the
  advice we were given.
- `"schema": 1` in the JSON report. The moment anything outside this project
  reads `--report`, its shape is an interface.

### Changed
- Filenames keep their Polish letters. `unicodedata.NFKD` cannot decompose `ł`,
  so the ASCII fold dropped it without trace and `okładka.png` became
  `okadka.png`. A transliteration table is applied first: `okladka.png`,
  `Żółć.xhtml` → `Zolc.xhtml`. `đ ø æ œ ß þ ð` and friends are the same defect
  in other alphabets and cost nothing to cover.

## 0.7.0

### Added
- Optional reader-family compatibility profiles: `--compat kindle`, `kobo`,
  `apple`, `legacy`, and the matching checkboxes in the interface. All off by
  default, because the product of this tool is a standards-clean book and each
  profile is a deliberate step away from that.

  Every measure is **additive** — it adds a file, a declaration or a legacy
  element, and never removes or rewrites what the book already had. That is the
  admission price: a concession that could damage the book on correct software
  would be a regression, not a concession. With all four profiles enabled the
  output still passes EPUBCheck with zero errors and zero warnings, and a test
  pins that.

  What the measures are: the EPUB 2 `<guide>`, which is where Amazon's
  converter and RMSDK readers look for the cover and the start-reading
  position; a stylesheet declaring the HTML5 sectioning elements as blocks,
  because RMSDK renders an element it does not know as inline and collapses a
  book built from `<section>` into one running paragraph; the legacy
  `page-break-*` spelling mirrored beside each modern `break-*` declaration;
  and `META-INF/com.apple.ibooks.display-options.xml`, without which Apple
  Books substitutes its own font for every embedded face.
- `epubforge compat` prints what each profile does, why a device needs it and
  what it costs, so `--compat` is not a guess.

### Fixed
- `minimal` mode did not do what it promised. It was documented and described
  as leaving content files byte for byte, but the XHTML and CSS stages ran
  regardless, so every document came back reserialised. The two stages are now
  skipped outright in that mode — parsing a document changes its bytes even
  when nothing about it is wrong, so the only way to keep the promise is not to
  open the file.
- The About dialog's logo was a blur. `QPixmap` handed a multi-size `.ico`
  loads the *first* directory entry, which is the 16×16 one, and scaling that
  up to a 72-point badge is exactly as bad as it sounds. It now loads the
  256×256 PNG and renders at the display's pixel ratio.
- Combo boxes clipped the descenders of their own labels — which in Polish
  means every ą, ę and g.

## 0.6.0

### Changed
- Renamed to **EPUB F.O.R.G.E.** — *Fabryka Odbudowy i Renowacji Glitchujących
  EPUB-ów* / *Factory for Overhauling and Renovating Glitchy EPUBs*. The window
  title, About dialog, installer and documentation follow; executable and
  distribution folder names are deliberately unchanged so the Windows build
  keeps working.

### Added
- A rare dry remark, shown only when a book arrives with nothing at all to fix.
  The tool's personality lives in its documentation and in the fixed text of
  the interface; a wisecrack after every book stops being funny by the third
  one, and one beside a warning or an error is simply in the way.

### Fixed
- The Windows build stopped working the moment the repository itself was
  renamed to `EPUB-F.O.R.G.E.`. A trailing dot is legal in a repository name
  and illegal in a Windows directory name, so the runner's workspace —
  `D:\a\<repo>\<repo>` — became a path that cannot exist. `actions/checkout`
  aborts on it while validating `GITHUB_WORKSPACE`, which happens before it
  reads its own inputs, so its `path:` option cannot help; and every `run:`
  step would fail identically, that directory being their default working
  directory. The job now clones into a fixed dot-free path and never touches
  the workspace. Renaming the repository without the trailing dot remains the
  real fix and would let the workflow go back to a plain checkout — the
  displayed name can keep its dots regardless.

## 0.5.1

### Fixed
- The `schema:` prefix used by the accessibility metadata is only *reserved*
  from EPUB 3.3 onwards. A reader built against EPUB 3.0 or 3.1 sees an
  undeclared prefix on every accessibility property, and a strict one can
  reject the package document — which presents to the user as a book that will
  not open at all. The prefix is now declared on `<package>`, which is
  redundant under 3.3 and legal there, so it costs nothing and restores older
  devices. EPUBCheck never flagged this because it validates against 3.3.

## 0.5.0

### Added
- Publisher watermarks are consolidated instead of being left to smear through
  the book. Retailer "social DRM" stamps a per-purchase token into a
  `<div style="font-size:1px !important">` at the end of **every** document —
  34 copies in one book measured here, 27 and 23 in two others. The token text
  is never touched, but the repeated inline `!important` styling becomes a
  single rule, and the marker gains `aria-hidden` so a screen reader stops
  spelling it out at the end of every chapter.
- Visible watermark notices — the human-readable "this document is protected,
  order ##…" block — are recognised separately and left exactly as written,
  because they are meant to be read. They are reported, and if the notice
  carries an e-mail address that is called out, since it identifies the buyer.
- `--keep-watermark-markup` leaves the markup untouched.

### Fixed
- Nothing in the watermark heuristic may catch ordinary content: an unanchored
  font-size pattern read `10px` as `1` and `0.9em` as `0`, which would have
  pulled legitimate fine print into the watermark path. Sizes are now compared
  numerically, and only absolute units count — `em` and `%` are how publishers
  set small print.
- The consolidated rule hides at `font-size: 0`, not `1px`, because publishers
  hide these at `0pt` as often as at `1px` and the replacement must never be
  more visible than what it replaces.

## 0.4.0

Driven by three more real books: Book 3, and Book 8 before
and after a manual repair.

### Added
- Repair for a block-level box nested directly inside an inline one — a chapter
  heading built as `<h1><a><span style="display:block">…</span></a></h1>`. The
  block splits the inline into anonymous boxes and margins and centring then
  behave unpredictably; the wrapper is promoted to `inline-block`, which is a
  legal container in the same position.

### Fixed
- Undefined entities such as `&nbsp;` survived into the output. With
  `resolve_entities=False` lxml accepts them as entity nodes and the strict
  parse *succeeds*, so the fallback that rewrites them never ran — and the
  EPUB 3 `<!DOCTYPE html>` does not declare them, making readers fail fatally.
  Entities are now normalised before the strict parse rather than after it.
- `width="10%"` on an image is valid XHTML 1.1 but invalid XHTML 5, where the
  attribute must be a bare integer. Non-integer values move to CSS; integers
  stay as attributes.
- `remote-resources` was declared for documents whose only external reference
  was an ordinary hyperlink. The property covers resources a document embeds,
  not where its links point.
- Navigation entries pointing at a fragment that no longer exists now fall back
  to the document, instead of leaving a dangling anchor for validators.
- Image paragraphs already centred by a generic rule are no longer given a
  redundant inline style.

## 0.3.0

### Added
- EPUB Accessibility 1.1 discovery metadata (`schema:accessMode`,
  `accessModeSufficient`, `accessibilityFeature`, `accessibilityHazard`,
  `accessibilitySummary`), derived only from what the book demonstrably
  contains. Relevant since the European Accessibility Act began covering
  e-books in June 2025.
- Detection of alt text that merely repeats the filename (`alt="title-1"`,
  `alt="cover"`). It satisfies a validator and tells a screen-reader user
  nothing, so it does not count as a description and `alternativeText` is
  withheld.
- The cover image is described with the book's title instead of being left with
  a placeholder or an empty alt.
- Accessibility gaps a machine cannot fill — missing descriptions, skipped
  heading levels, tables without header cells — are reported as human work.
- `--claim-conformance {wcag-a,wcag-aa,wcag-aaa}` records the publisher's own
  conformance assertion. Never set automatically: WCAG cannot be established
  mechanically, and under the EAA the claim carries legal weight.
- `--no-a11y-metadata` to skip the declarations entirely.
- Interface language is switchable between Polish and English under
  Settings → Interface language, and remembered between runs.
- An About dialog naming the authors, the licence and the bundled components
  with their licences.
- Polish README, with the English one kept as `README.en.md`.

### Changed
- The image-paragraph correction now reads the CSS cascade before acting. A rule
  aimed at a paragraph by class or id — `p.ilustracja { text-align: right }` —
  is a decision about that image and is obeyed, while a blanket
  `p { text-align: justify }` written for prose is treated as inheritance that
  happens to land on the artwork. Inline styles are likewise respected. Books
  that style their images deliberately are therefore left alone; only pages
  where nothing decided the alignment are centred.

### Fixed
- The portable build showed no icon in the taskbar or window. PyInstaller's
  `icon=` only stamps the executable's resource, which is what Explorer draws;
  Qt needs the file at runtime, and Windows needs an explicit AppUserModelID or
  it groups the process under the host interpreter.

## 0.2.0

### Added
- Self-contained Windows build: PyInstaller distribution bundling the Python
  runtime, Qt, a jlink-built Java runtime and EPUBCheck, plus an Inno Setup
  installer and a portable ZIP. Nothing needs to be installed on the target
  machine.
- Polish interface with tooltips that describe what each option does to the
  book, and per-item tooltips on the rebuild modes.
- Fluent-flavoured styling with light and dark variants selected from the
  system palette.
- Repair of publisher CSS errors: `font-style`/`font-weight: regular`, which is
  not a CSS value and caused parsers to discard the whole declaration.
- Image-only paragraphs are opted out of body-text indentation and centred, so
  cover and title artwork is no longer shifted by rules meant for running text.
- Stylesheet findings are surfaced: reader-specific properties such as
  `adobe-hyphenate`, and font stacks that end without a generic family.
- `--strict` removes reader-specific CSS properties and out-of-flow positioning.

### Changed
- The report now accounts for structural work. Upgrading the package from
  EPUB 2 to 3.3, relocating files and generating a navigation document count as
  fixes; a real rebuild can no longer report "0 fixed".
- Media types the manifest declares incorrectly are reported rather than being
  corrected silently.
- The GUI gained a "Kept" column so deliberate deviations are visible without
  opening the report.

### Fixed
- Content documents recovered by the HTML parser serialised with an `html:`
  prefix on every element instead of a default namespace.
- Fragment identifiers in the navigation document and NCX were not remapped
  when the ids they pointed at had to be renamed.
- Spine-order filename prefixes accumulated (`0000-0000-…`) when a book was
  rebuilt more than once.

### Reverted
- Out-of-flow positioning is no longer stripped from reflowable books by
  default. A rule such as `div.dol { position: absolute; bottom: 0 }` pins a
  dedication to the foot of the page — that is a layout the publisher chose,
  not a defect, so it is now reported and kept unless `--strict` is used.

## 0.1.0

Initial version: reads any EPUB 2 or 3 into a format-neutral model and
regenerates a conforming EPUB 3.3 container from it — package document,
navigation, manifest, spine, filenames and ZIP layout. Legacy presentational
markup is translated to equivalent CSS rather than dropped, obfuscated fonts
are deobfuscated, and non-core image formats are transcoded with references
rewritten. DRM is detected and refused.
