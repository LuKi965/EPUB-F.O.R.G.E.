# Changelog

Maturity is stated in words, not encoded in the number: `__stage__` sits beside
`__version__` and appears wherever the version does — `alpha` today. MINOR
moves only when the stage does, against the entry conditions in
`CONTRIBUTING.md`. PATCH moves on every release, whatever it contains, so there
is no judgement call to make and therefore no way for one to drift upwards.

The number says nothing about how significant a change was. That is what the
entries below are for.

The version lives in `epubforge/__init__.py` and is the single source for
`pyproject.toml`, `epubforge --version`, the window title and the Windows
installer — bump it there and everything follows.

---

### A note on the numbers below

Releases 0.2.0 through 0.8.1 were numbered under two earlier schemes, both of
which used MINOR as a rough measure of "how much got done". Nothing was ever
tagged or published under those numbers, so they were renumbered rather than
left to imply a maturity the software does not have. The history is kept as
written; only the current version was reset.

## Unreleased

### The report speaks whichever language the interface does

The window had both languages and everything it wrote had one. The saved JSON,
the batch document and the console table were English whatever the setting
said — which is not bilingual, it is Polish in one place and English in three.
That is the shape of the complaint that found it, and it was right.

`to_json(language)` and `batch_to_json(language)` add a `description` field
rendered from the finding's `rule` and `values`; the window passes its own
setting to both. The English `message` does not move and is present in either
document: it is the field a script greps, and replacing it with Polish would be
a broken interface wearing a feature's name. English readers get `description`
too, in English, so no consumer has to special-case a language.

The command line has nowhere to remember a setting, so `--report-language`
decides, defaulting to the window's stored choice, then `LANG`, then English. A
person who set the interface to Polish did not mean "Polish, except on the
command line".

One renderer serves all three now — `Report.headline` — because the console
built its own line out of `finding.message`, which is exactly how it stayed
English while everything around it was translated.

### The release procedure updates the README

Step zero, not the last step: the version, the test count, the alpha conditions
and the list of limitations. It had drifted two releases behind and still said
the report was English-only, which stopped being true in the same release that
made the claim look most convincing. A limitation that is no longer true is
worse than a stale number — it tells someone a thing is missing when it is
there.

### A correction to the 0.2.4 notes

Those notes said "all 79 call sites are converted". That is not what the number
means and it was not true: 79 findings carried an identifier and 57 did not, so
those still printed English in a Polish report. The ratchet counts what is
tagged, not what is left, which is exactly how a migration can look finished
from inside. The wording is corrected, the 57 are done (below), and the
published 0.2.4 release notes carry the wrong sentence where it cannot be
edited after the fact.

### EF-018 is closed, and this time the number means it

Every finding this program can report has an identifier: **136 call sites, 135
catalogued ids, none left over in either direction**. The 57 that had none were
the whole reader, the whole content stage and every stylesheet finding — which
is why a Polish report was still half English no matter how good the catalogue
got.

Both catalogues state their own specifics now, so the English line underneath a
translated one is gone entirely. Measured rather than assumed: across the
fifteen books of the two public corpora, rebuilt under all three profiles, 389
findings, **none without an identifier, none falling back to English, no
placeholder printed at the reader**.

What is still English: the `detail` line under a finding. It is prose rather
than a sentence with a number in it, and translating it is a separate piece of
work rather than the same one continued.

### Thirty-seven English lines that are no longer needed

A translated finding used to carry its English original underneath, because the
specifics — how many entries, which file, which media type — lived in the
sentence and a generic description could not state them. A finding now carries
its values beside its message, and 44 catalogue entries became templates that
state them in either language. Where the template says everything the message
said, the second line is gone.

Polish counts agree with their nouns. English gets away with "(s)"; Polish has
three forms, chosen by the number, and "1 plików" is a mistake rather than a
clumsy phrasing. `{count:plik|pliki|plików}` in a catalogue entry picks the
right one — one for exactly 1, the *few* form for numbers ending 2–4 outside
the teens, the *many* form for the rest.

Two ratchets now, not one: how many sites carry an id, and how many entries
state their own specifics. Either may rise and neither may fall.

## 0.2.4 — alpha — 2026-08-05

**Every finding this program can make now has a name that survives being
reworded, and that name is what the Polish report translates.** The catalogue
was the last of the two unmet alpha conditions; the other was the translation,
and it could not have been done without it.

### At a glance

| | |
|---|---|
| A finding's identity was its English sentence | 79 call sites, 78 catalogued ids |
| The report could not be translated at all | now Polish, 78 of 78 findings |
| A corpus diff said `report.fix: 5 → 6` | now names the rule that moved |
| A container-only rebuild emitted `../` hrefs | 70 of 70 manifest entries, EPUBCheck silent |
| Archive entries declared no file type | every file this program ever wrote |
| A milestone freeze was a thing to remember | now four written steps |

**New:** `tools/device_variants.py`, which builds the archive-level variants
that bisect a reader refusing a valid book. **Fixed:** the package document no
longer walks away from the files it describes.

### Everything, by subject

### Seventy manifest hrefs that climbed out of their own directory

A container-only rebuild put the package document in `EPUB/` and left every
file it describes in `OEBPS/`, because `content_dir` decides where the package
goes and `reorganize_files` decides where the resources go — and `minimal`
turns off only the second. Every manifest entry then had to climb back out:
`href="../OEBPS/images/cover.jpg"`, seventy times over.

That is legal. The path never leaves the container, and EPUBCheck passes it
without a message of any kind — verified on the file this was found in, before
and after. It is also the shape of a zip-slip attack, which is exactly what a
reader guards against, and a reader that refuses the path refuses the book.

When the files do not move, the package document does not move either: it
stays where the source had it, and says so (`package.layout-kept`). The
invariant — no manifest href begins with `../` — is now a test across all three
profiles, because nothing else was ever going to catch it.

Found while writing up why an InkBOOK Focus hangs on our output; whether it is
*the* cause there is still unknown, and the investigation is written down in
`docs/sprawy/INKBOOK-FOCUS.md` rather than carried in anyone's head.
`tools/device_variants.py` rebuilds the archive-level variants that bisect a
reader like it — one file per property the specification leaves free, plus the
control file without which no result means anything.

### Every archive entry now says it is a file

`create_system = 3` on a ZIP entry means "the mode field holds Unix
attributes", and the mode this program wrote was `0o644` — permissions with the
file-type bits left at zero, which is neither a regular file nor a directory.
Every EPUB this program has ever produced said that about every entry in it.
Nothing on a desktop cares. A reader that reads the field and believes it is a
different matter, and both files known to open on the device that started this
were `0o100644`.

The content directory may also be the archive root now, which is where Calibre
puts the package document and where some readers were built to look for it.
Making it configurable was four lines and exposed three wrong ones: joining a
directory that is empty produced `/content.opf` and `/images/…`, a leading
slash that is not a container path at all, and EPUBCheck said so 214 times.
All four join sites go through `paths.content_path` now.

### A finding now has a name that does not change (EF-018, in progress)

The identity of a finding used to be its English sentence. Three consequences,
all of which had already happened: rewording a message broke a test that was
never about the wording; `survey.py` had to strip numbers and quoted fragments
with regular expressions before it could count anything, which is a symptom
rather than a solution; and the report could not be translated at all, because
a sentence that *is* the identity cannot be replaced by its Polish equivalent
without changing what it identifies.

`epubforge/rules.py` is the catalogue — `nav.repointed`,
`xhtml.doctype-modernised` — with one line each saying what the finding means.
That mapping is the thing a translation replaces, and the reason it exists.
`Finding.rule` carries it, `--report` output carries it, and `survey.py` groups
by it wherever it is present: where the identity exists, the guessing stops.

There are more than a hundred call sites, so this lands over several changes.
`tests/test_rules.py` holds it to a ratchet — the number of tagged sites may
rise and may not fall, an id nothing raises fails the suite, and an id raised
but not catalogued fails it too. **79 call sites carry an id**, the catalogue
and the code agree in both directions, and the exemption list is empty.

One call site turned out to be two findings sharing one call. Replacing a
navigation document the source had is routine; generating one it never had is a
correction. They carried different levels and different messages through a
conditional expression, which is how they came to share an identity neither of
them could have.

### The report speaks Polish

The second of the two unmet alpha conditions. The window has been bilingual for
a while and the report has not, and the reason was structural rather than
effort: a sentence that *is* the identity of a finding cannot be swapped for its
Polish equivalent without changing what it identifies. The catalogue is what
made this possible, and it is exactly what a translation replaces.

All 78 findings have a Polish description. `report.to_text("pl")` and the window
use it; English is unchanged, byte for byte, because a translation that alters
the original is a rewrite wearing a translation's name.

The original message stays underneath the translated line. Thirty-seven of the
seventy-eight still interpolate their values straight into the sentence — how
many entries, which file, which media type — and dropping that to gain Polish
would trade information for language. Turning those into templates with their
values alongside is what removes the second line; until then it is there and
said out loud rather than quietly lost.

A copied English line in the Polish catalogue fails the suite: that is the shape
a stalled translation takes, and it looks finished.

### A corpus diff now names the behaviour, not the counter

Signatures record which rules fired and how often, so a book whose signature
moves reads as `+a11y.missing-alt ×3, −nav.entry-dropped` instead of
`report.fix: 5 → 6`. The second says a number went up; finding out which
behaviour changed meant rebuilding the book by hand. This is what the
identifiers were for.

Both corpora are re-recorded to carry the distribution.

### The milestone cycle is a procedure now, not a memory

Releasing a milestone is four steps in one turn: build and release, freeze
`frozen/vX.Y.Z-<name>`, open the next milestone's branch, and print the list of
branches that can be deleted. Written into `CONTRIBUTING.md` because step two
was deferred once and produced a branch called `claude/safety-gate` that had
been moved onto `main` repeatedly and held work with nothing to do with the
Safety Gate. A label on a moving target is not a freeze.

`tools/branches.py` prints what is safe to delete — merged into the trunk, not a
`frozen/` marker, not in use — because remote deletion is refused from the build
environment with the same 403 that refuses a tag push, so a person does it.

## 0.2.3 — alpha — 2026-08-05

**Thirty-two real books and six from Project Gutenberg were pointed at this
release, and they found five defects that no fixture could have.** Four books
came out invalid; one of them turned a source EPUBCheck passed cleanly into 235
errors. All five are closed.

### At a glance

| | |
|---|---|
| The publisher's contents page was destroyed | K1 violation, 4 of 32 books |
| Replacing the navigation left dead references | invalid output, 27 links in one book |
| Container-only mode stranded entities | book would not open, 4 of 32 books |
| Metadata written the EPUB 3 way was dropped | 11 of 32 books |
| Manifest properties were withdrawn silently | every book with a false declaration |

**New:** one JSON report for a whole run, in the window (Ctrl+Shift+S) and on
the command line. **Fixed:** the report panel stayed blank when the queue held
a single book.

### Everything, by subject

### Container-only mode carries its entities with it

A legacy DOCTYPE declares entities two ways, and the second is the one that
matters: every XHTML 1.1 document may write `&nbsp;` because `xhtml11.dtd`
declares it. Under EPUB 3 nothing fetches that DTD, so taking the declaration
away without taking the entity with it stranded the reference — *Fatal Error
while parsing file: The entity "nbsp" was referenced, but not declared*.

One book had **235 EPUBCheck errors against a source that had none**, and 228
of them were consequences: seven documents would not parse, so every navigation
link into them was reported as an undefined fragment. There were never 221 dead
anchors; there were seven unparseable files.

The named entities now travel with the DOCTYPE, rewritten to numeric references
— the same character, needing no declaration. What this mode promises is that
the book looks the same; bytes were only ever a convenient way of keeping that
promise. A name nothing can resolve stops the swap and is reported, because a
book that will not open is worse than one that is merely invalid.

Four of thirty-two real books were affected. All four: EPUBCheck clean.

### One report for a whole run

Saving a report per book is right for one book and unusable for thirty: the
question a batch raises is *which* of them needs attention. `batch_to_json`
writes one document — run totals first, then every book in full, worst first,
so it can be read from the top and abandoned as soon as it stops being
interesting. In the window under *Zapisz raport zbiorczy…* (Ctrl+Shift+S), and
on the command line whenever `--report` names a file rather than a directory.

That fixed a defect of the same shape: `--report out.json` with five books
wrote all five to one path in turn, leaving a report about whichever book came
last — indistinguishable from a report about the run.

### Two findings of mine that were not defects, and two that were

**Both findings reported in 0.2.1 were mine, and neither was a defect.** They
were announced as losses neither audit had caught. Checking them against
EPUBCheck rather than against my own fixture:

| Reported as | Actually |
|---|---|
| `item/@properties="scripted"` dropped | a **correction**. The fixture declared `scripted` on a document with no script, and EPUBCheck errors on the *source*: "The property 'scripted' should not be declared in the OPF file" |
| `itemref/@properties` dropped | a **false positive in the oracle**. Every token was still there; the writer sorts them, and the oracle compared `properties` as a string when it is an unordered set of tokens |

The fixture also declared `page-spread-center` without its `rendition:` prefix,
which EPUBCheck calls an undefined property. Two invalid constructs in a fixture
whose entire job is to be valid.

`TOKEN_LISTS` in `tests/opf_graph.py` fixes the oracle, with two tests: one that
reorders every `properties` attribute in the package and expects silence, and
one that removes a single token and expects a finding. An oracle that produces
false findings spends the credibility the true ones need.

**Two real defects came out of checking.**

A manifest property withdrawn because the document does not bear it out is now
**reported**. It was silent, which meant a publisher got a package differing
from theirs with nothing to explain it. `minimal` still keeps a false
declaration, because it promises to touch nothing and that promise covers
declarations that are wrong.

And the scripting check itself was broken: `any(root.iter(qname("script")))`
truth-tests the *elements*, and an lxml element with no children is falsy. A
document whose only script was `<script>void 0;</script>` came out undeclared —
a reading system would have been told it needs no scripting support. lxml had
been emitting a `FutureWarning` about this exact construct the whole time. The
suite now runs clean under `-W error::FutureWarning`.

Tests: 498 → 503.

### Two defects found by thirty-two real books

Commercial Polish editions, run through all three modes. Four of the thirty-two failed, all four in the same
two ways, and neither defect had a test because neither can happen to a book
written to be a test.

**The publisher's contents page was being destroyed.** A nav document is
allowed to sit in the reading order, and when it does it is two things at once:
the machine-readable navigation, and a page the publisher wrote that the reader
can turn to. Regenerating it served the first and destroyed the second —
"Spis treści", "Punkty orientacyjne" and the publisher's own chapter labels
replaced by ours. Text the source had and the output did not, which is K1, on
four books out of thirty-two.

The page now stays as an ordinary content document and the regenerated
navigation goes in beside it, outside the reading order. One nav document, as
EPUB 3 requires; the publisher's page, as the reader expects. Reported as
`PRESERVED`.

**Replacing a nav document left references pointing at nothing.** The
regenerated nav listed the page it had just deleted, and in one book
twenty-seven chapters carried a "back to contents" link to it:

```
ERROR: Referenced resource "EPUB/text/0015-table_of_contents.xhtml"
       could not be found in the EPUB. (EPUB/nav.xhtml)
```

The output was invalid, and the report said nothing. References in the
navigation tables, the landmarks, the page list and inside content documents
now follow the document that replaced it, and the repointing is reported.

All four books: EPUBCheck clean, K1 satisfied. The `nav-in-spine.epub`
signature moves deliberately — `text_added: 47 → 0`, the source's text now
preserved to the character.

Tests: 503 → 524.

### Metadata written the EPUB 3 way was being dropped

Only
`<meta name= content=>` — the EPUB 2 spelling — was carried through. Anything
said as `<meta property="…">` that the model had no field for went silently,
and the vocabulary is open by design: "not recognised" says something about
this program and nothing about the book.

Apple's `ibooks:specified-fonts` is what exposed it, on eleven of thirty-two
real books. Unknown properties are now carried with their qualifiers, and the
prefix declaration comes with them — without one the property is not a property
but an error, which EPUBCheck reports as *Undeclared prefix*. Only prefixes the
output actually uses are declared, so regenerating that attribute rather than
copying it still holds.

Tests: 524 → 529.

### One edit in container-only mode, dead anchors, and a blank report panel

**The container-only mode makes exactly one edit inside a document now.** A
legacy DOCTYPE makes its output an invalid EPUB 3 — *Irregular DOCTYPE: found
"-//W3C//DTD XHTML 1.1//EN"* — and a DOCTYPE says nothing about how a page
renders, so replacing it is the one change that cannot alter what the reader
sees. Done on the bytes, because opening the document is what this mode
promises not to do. A DOCTYPE declaring its own entities is left alone: those
entities are used, and `<!DOCTYPE html>` does not define them, so swapping it
would turn a merely invalid book into one that will not parse.

The byte-identity test was not relaxed to accommodate this — it normalises the
DOCTYPE on both sides and still demands every other byte match.

**The same mode was leaving dead anchors in the navigation.** Whether a
fragment exists is checked against ids collected while rewriting documents, and
this mode does not rewrite them, so every anchor was assumed live. Reading the
ids costs a parse and changes nothing.

**The report panel stayed blank for a queue of one.** Drawing it was left to
`itemSelectionChanged`, which does not fire when the row is already selected —
so with a single book the report only appeared after a second was added and the
user clicked between them.

Tests: 529 → 534.

### The DOCTYPE swap could strand an entity

The swap above had a hole, and a real book found it. A legacy DOCTYPE declares entities two ways — an internal subset, which was
guarded, and the external DTD it names, which was not. Every XHTML 1.1 document
may write `&nbsp;` because `xhtml11.dtd` declares it, so replacing the
declaration stranded the reference: *Fatal Error while parsing file: The entity
"nbsp" was referenced, but not declared*. A book that will not open, from one
that was merely invalid. The swap now happens only when the document uses no
named entity beyond the five XML built-ins.

Numeric references are unaffected, and `&amp;` and its four siblings do not
block the swap — treating them as a reason to stop would mean never modernising
anything.

Tests: 534 → 537.

## 0.2.2 — alpha

**EF-004 closed.** The last three constructs the model had no room for now
survive a rebuild, and both oracles' defect lists are empty.

| | |
|---|---|
| `<collection>` | carried whole — role, other attributes, nested collections, links, and any `<metadata>` verbatim, because the role vocabulary is open and there is nothing honest to model field by field |
| remote manifest items | declared, never fetched. Dropping one meant the output no longer declared a resource the source did |
| the second `belongs-to-collection` | every membership is kept with its own type and position; a book in a boxed set *and* a series used to keep whichever came first |

A `set`-typed collection now comes back as a set. The old test asserted it came
back *absent* — which read as a decision ("a boxed edition is not a series") but
was the single series field showing through. Not being a series is a reason to
keep it as a set, not to drop it.

**Six real books joined the corpus** — Project Gutenberg, public domain,
committed with the source, three of them Polish. They earned it on the first
run by exposing a defect in the measurement itself: `text_invariant` was false
on all six, and no text had been lost. The field compared character counts for
*equality*, so generating a cover page — two characters — reported a broken
invariant. K1 says no character is lost; it does not say none may be added, and
nothing else in the program was checking K1 at runtime.

It now checks what K1 actually claims: every character of the source's reading
order still appears in the output's, in order. Four tests say so, including one
that reorders text without changing its length — which the count could never
have caught, and neither could a book written to be a test.

Tests: 461 → 498.

## 0.2.1 — alpha

**A stronger oracle, and the first part of EF-004 closed with it.**

`tests/opf_graph.py` reads the package document as a graph: nodes with values
and qualifiers, edges for `refines`, `fallback`, `media-overlay`, spine and
collection membership, and a multiset rather than a set. The oracle it replaces
asked whether the *name* of a construct still appeared somewhere, which is why
a book with two `<collection>` elements could come back with one and pass. Node
identity survives the things a rebuild is entitled to do — moving a file,
renumbering it, transcoding an image — and nothing else.

It found two losses that neither audit listed:

| | |
|---|---|
| `item/@properties="scripted"` | `preserve` dropped the property that tells a reading system the document contains scripting |
| `itemref/@properties` | `page-spread-center` lost, so a fixed-layout page no longer says which side of the fold it belongs on |

**Media Overlays now survive, and this was worse than a loss.** Three separate
omissions combined into one invalid book:

- the SMIL file was carried as opaque bytes and moved to `misc/`, which left its
  own `src` attributes pointing at files that were no longer there;
- `item/@media-overlay` was never read, and EPUBCheck rejects a SMIL file whose
  document does not point back at it;
- `media:duration` was skipped because it is a refinement, and refinements were
  assumed to belong to collections.

`item/@fallback` is fixed in the same change, and it was the most invisible kind
of defect: the field existed on the model and had no line in the writer, so it
was read and then quietly dropped. A `fallback` or `media-overlay` naming an id
the manifest does not define is now reported rather than guessed at.

Both oracles carry a ratchet in the other direction too: an entry describing a
loss that no longer happens fails the suite until it is deleted. Four entries
were removed by that rule while this change was being written, which is the
point of having it.

`media-overlays.epub` in the public corpus has a new signature, deliberately.

Tests: 428 → 461.

## 0.2.0 — alpha

**Safety Gate complete.** Ten tasks, seven of the eight P0 findings from
`audit_consolidation/` closed, and every one verified with the reproduction that
exposed it rather than with a test written afterwards. The program can no longer
lie about the outcome of a run, and can no longer destroy somebody else's file
on the way.

What changed, in one line each — the detail is under 0.1.7 and 0.1.8:

| | |
|---|---|
| EF-001 | a stage that raises no longer ends in a file |
| EF-002 | a batch settles every destination before writing, and refuses a collision |
| EF-003 | the write is atomic; a failure leaves the previous output byte-identical |
| EF-005 | nothing is deleted unless asked, until the dependency graph can prove it unused |
| EF-006 | no accessibility claim without evidence for every graphic |
| EF-007 | a nav document in the reading order stays in the reading order |
| EF-008 | container names read through a model; collisions detected, not resolved by luck |
| EF-011 | the exit code says what happened |
| EF-019 | an existing destination is not replaced without `--force` |
| EF-023 | the corpus regression runs for everybody, not for one shelf |

Tests: 307 → 413.

### The maturity claim, and what it is standing on

`CONTRIBUTING.md` lists three conditions for leaving pre-alpha. **Three of the
three are unmet, and this release is being called alpha anyway** — a decision by
the project owner, recorded here rather than left for somebody to discover.

| Condition | Actual state |
|---|---|
| corpus ≥ 30 books, metrics green across three consecutive releases | 64 books exist, recorded on 0.1.6. Releases 0.1.7 and 0.1.8 deliberately changed the output, so the signatures need re-recording and the three-release run has not happened. |
| message catalogue ready, report translated | Neither. The report is English-only and findings have no stable identifiers (EF-018). |
| **no known defects that lose data silently** | **False.** EF-004 is open and confirmed: Media Overlays, remote resources, `fallback`, `media:duration` and one of two collections still disappear with zero errors reported. |

The third is not a formality. A book with read-aloud narration loses its
synchronisation, passes EPUBCheck, and says nothing about it. Anyone handed this
release should know that; the README limits section says so too.

What alpha does mean here, honestly stated: the failure modes that could destroy
your work are closed, and the ones that remain are about **completeness of the
output**, not about safety. That is a real threshold, and it is the one worth
crossing before giving the program to other people. It is simply not the
threshold the version table describes.

Closing EF-004 is the whole of the next block of work.

## 0.1.8 — pre-alpha

Closes the last of the P0 findings. Archive entry names are read through a model
instead of being folded into shape by one expression and stored.

### Fixed
- **Two archive entries with one name no longer resolve by iteration order**
  (EF-008). The later one won and the earlier one was gone, silently. When both
  bodies are identical nothing is lost and the run continues with a note; when
  they differ, one of the two documents cannot be represented whatever the tool
  does, so the read stops rather than picking for you.
- **A name that climbs out of the container is dropped, not copied through.**
  An entry literally called `../outside.bin` used to survive a `minimal` rebuild
  into the output. This tool never unpacks an archive, so it was never at risk
  itself — whoever unpacked the result was.
- **Names that differ only by case, or only by Unicode normalisation, are
  reported.** Both are legal and distinct inside the archive, and both are one
  file on a filesystem that folds case or normalisation — which is most of them
  outside Linux. The book is not refused, because it reads perfectly well where
  it was made; the warning names the pair.
- Every name the reader has to rewrite — backslash separators, a leading slash,
  a drive letter, `.` or `..` segments, percent-encoding — now appears in the
  report. Folding them silently meant a name that had been changed looked
  exactly like one that had not.

### Added
- `epubforge/ocf.py` — container names as a value with an account of what was
  changed, and collision detection under four views: identical, percent-decoded,
  NFC, case-folded.
- `tests/test_ocf_paths.py`.
- **A corpus regression that runs for everybody** (EF-023). The private corpus is
  the strongest net this project has and it runs on one machine in the world;
  everywhere else the test skipped. `tests/public_corpus.py` builds nine books
  from what the 64-book survey established about real ones, byte-deterministically
  so their signatures mean the same thing on every machine, and
  `tests/corpus_public/` holds those signatures at 40 KB.

  Three of the nine exist because the measured library contains **no** example:
  right-to-left, Media Overlays and fixed layout. Those are where the model is
  thinnest — reading direction has already been lost once, in every mode
  including the one that promises to touch nothing — and until now nothing in
  the repository exercised them at all.

  Real public-domain books would be a better second corpus and remain wanted;
  this environment cannot reach Project Gutenberg to fetch any.

## 0.1.7 — pre-alpha

First of the Safety Gate releases. Nothing here adds a capability; all of it
stops the program from doing something it should never have been able to do.
The findings are from `audit_consolidation/`, where each one has a runnable
reproduction.

### Changed
- **Unreferenced files are no longer deleted by default** (EF-005). The
  reference graph does not follow `img@srcset`, `<picture><source srcset>` or
  links made from inside an SVG, so "nothing points at this" was not the same
  claim as "nothing needs this" — measured, not supposed: a valid PNG used only
  through `srcset` was deleted while the markup pointing at it stayed. The
  output validated and rendered a hole. `--drop-orphans` brings the old
  behaviour back for anyone who wants it; the flag that used to exist,
  `--keep-orphans`, is gone rather than left as a silent no-op.
- **The exit code says what happened** (EF-011). A book that produced an ERROR
  was written, announced in green as `written`, and exited 0 unless
  `--strict-exit` was passed — so a script read a damaged book as a finished
  one. Now: `0` clean, `1` nothing written, `2` written with errors. The message
  distinguishes `written` from `written with errors`, and `--strict-exit` now
  means what its name suggests — warnings count too.
- **An existing file at the destination is no longer replaced without asking**
  (EF-019). The source file has always been protected by an explicit guard, and
  that guard was the reason nobody looked at the rest: pointing `-o` at any
  other file replaced it, silently, exit 0. `--force` is the way to say yes.
- **The write is all or nothing** (EF-003). `write_epub` opened the destination
  directly, so a failure partway through left a truncated file under the name
  the user knew — measured before the fix: 2338 bytes became 1196. The archive
  is now built under a temporary name beside the destination, closed, read back
  and checked for the things a half-written container gets wrong, and only then
  moved into place with `os.replace`. A `KeyboardInterrupt` is treated the same
  as a disk filling up.
- **A batch settles every destination before it writes anything** (EF-002).
  Destinations were derived one book at a time from the basename, so nothing in
  the program ever held two of them at once and had the chance to notice they
  were the same. Two books called `tom-1.epub` under different authors resolved
  to one file: the second overwrote the first, both were announced as written,
  exit 0. The run is now refused with both source paths named. `--dry-run`
  prints the plan and writes nothing.
- **A navigation document that was part of the reading order stays there**
  (EF-007). A visible table of contents is a nav document in the spine — the
  page a reader can turn to. Regenerating it removed the old resource, and
  removing a resource removes its spine entry with it, so the page vanished:
  two spine items in, one out, no error and no warning. Position and `linear`
  are now carried over and the change is reported.
- **Accessibility metadata is no longer asserted without evidence** (EF-006).
  Two claims were being made on the strength of not having looked. A document
  whose only graphic was an inline `<svg>` with no title, desc or ARIA label
  came out declaring `alternativeText`, because the survey counted `<img>`
  elements and an inline SVG is not one. And `accessibilityHazard: none` was
  decided from video and script alone, so a CSS keyframe animation, an animated
  GIF and an animating SVG all passed as motionless. Inline SVG is now counted
  and examined; a graphic in an unknown state blocks the positive claim; and
  anything that might move makes the hazard `unknown` rather than `none`.
  These are the publisher's assertions under EPUB Accessibility 1.1 — a false
  one tells a reader who depends on it that the book is usable.
- **A stage that raises no longer ends in a file** (EF-001). The exception
  became an ERROR line, the remaining stages ran on a model the failure had
  left half-modified, and the writer produced a book that looked finished.
  Nothing about the file said otherwise — not its size, not its structure, not
  EPUBCheck. That is what made this the worst defect in the program rather than
  merely one of them: every other failure could leave the building through it.
  The run now stops, nothing is written, and the report names the stage.

### Added
- `Result.status` — `succeeded`, `succeeded-with-problems`, `blocked` or
  `failed`. Front ends used to work this out from `output_path is not None`,
  which cannot tell "finished" from "crashed, and we wrote the pieces anyway".
  A refusal (DRM, writing over the source) is now `blocked` rather than sharing
  a label with a malfunction.
- `tests/test_cli_contract.py` — the command line had no tests at all, which is
  precisely where two of these defects lived. Exit codes and refusals are a
  contract with whoever runs the program, and are now pinned as one.
- `tests/test_failure_injection.py` — parameterised over every stage in the real
  pipeline, so a stage added later is covered the day it is added. It also
  covers the write itself: a failure at three different points, a container
  that reads back wrong, and the temporary file not being left behind.
- `epubforge/plan.py` — destinations, collisions and occupied targets as a value
  that can be inspected before anything happens.

## 0.1.6 — pre-alpha

The other half of the same afternoon's data: the three books a 64-book survey
could not read, and the three complaints from the person running it.

### Fixed
- **Three books died on a comment.** `ValueError: Input object is not an XML
  element: lxml.etree._Comment` — one Polish shop writes its order number into
  `<metadata>` as an XML comment, Sigil leaves it there, and the metadata loop
  called `itertext()` on it. lxml refuses to walk a comment, so the rebuild
  ended before anything else could run. Nothing else about those books was
  unusual.

  The comment now **survives the rebuild**, which is the only consistent answer:
  it carries an order number, that is a watermark by any other name, and this
  tool does not remove watermarks. One containing `--` is dropped instead of
  mangled — XML has no escape for it — and nothing else in the package changes.
- **The cover was shown at its own pixel size when nothing sized it.** Found in
  a book a Calibre edit had left with the cover stylesheet in the archive root
  and the cover page still linking `../Styles/cover.css`: the link dangles, no
  rule reaches the image, and a 1600px cover meets a six-inch screen. Where
  **nothing** sizes the cover — no rule anywhere in the chain, no `width`
  attribute, no inline style — it now gets `max-width: 100%; max-height: 100%`.
  Both can only ever shrink an image below its natural size, so the worst case
  is a reader ignoring them. A cover the publisher did size is untouched.

### Changed
- **No more console window on Windows.** Ticking "check with EPUBCheck" starts
  a JVM, and a GUI process starting a console binary gets a console: a black
  rectangle that appears, does nothing, and disappears — once per book, so 64
  times on a library run. Started with `CREATE_NO_WINDOW` now. The progress it
  looked like it should be showing is in the window, and the status line says
  when the validator is the thing taking the time.
- **The corpus tab explains what it is for.** It was described in terms of what
  it stores rather than what it does, and it read as though it were signing the
  user's files. It is a safety net for this program: it notices when a change
  here alters what the rebuild produces for books nobody ever handed over. The
  status word for that is now "inny wynik" — a different result — because
  "changed" sounded like the book had been changed.
- The mode tooltip says outright that **every mode rebuilds the container**, and
  that the choice is only about what happens to the content. "Keep the
  appearance" reads like "leave the file alone", and it never meant that.

## 0.1.5 — pre-alpha

Everything here came out of one afternoon's data from somebody else's shelf: a
65-book survey, an inventory, one corpus signature and five EPUBs. Nothing in
this release was found by the test suite.

### Fixed
- **A cover that was already centred got "centred" anyway — and a cover the
  publisher had aligned on purpose got overruled.** `text-align` and
  `text-indent` are inherited, and the repair only ever looked at the paragraph
  itself. A page built as `body.cover { text-align: center }` around a bare
  `<div><img/></div>` shows nothing on the `<div>`, so the tool concluded
  nobody had chosen an alignment and wrote its own — a reported fix that
  changed nothing. The same blindness runs the other way and is the reason this
  is a defect rather than noise: a rule naming the container is a decision
  about the image inside it, and it was being overwritten. Both properties now
  resolve along the ancestor chain, and a decision made a level up counts as a
  decision. Where the alignment was chosen but a running-text indent still
  leaks in, only the indent is removed, and that is reported as what it is.
- **`text_invariant` in a corpus signature was false on books whose text was
  untouched.** The rebuild generates the navigation document EPUB 3 requires,
  and that document is a list of chapter titles — text, to anything counting
  characters across content documents. Every EPUB 2 book in a corpus therefore
  reported that its text had changed. The comparison is now over spine
  documents only, which is what K1 has always meant.
- **The same book built on Windows and on Linux came out with different
  bytes.** `zipfile` stamps every entry with the system it ran on — 0 for
  Windows, 3 for everything else — in both the local header and the central
  directory. Nothing about the book differed; every file inside was identical.
  It surfaced the only way it could: a corpus signature recorded on one machine
  and checked on another reported that the output had changed, for every book,
  forever. Proven rather than guessed — forcing the field to 0 here reproduces
  the Windows hash exactly, in both modes. Now pinned to 3, matching the Unix
  permission bits the writer already sets.

  **Signatures recorded on Windows before 0.1.5 will show `output` changed
  once.** That change is this fix and nothing else.
- **The corpus read only the top level of a folder.** Libraries are filed in
  subfolders, so a shelf of hundreds was measured as one book and reported as a
  success. The survey has always walked the tree; the corpus now agrees with
  it, and books are labelled by their path so two shelves may hold the same
  filename.
- **Save in the library tab wrote the previous result under the new name.**
  Running a survey, switching to inventory and pressing Save produced the
  survey called `spis.json`. Changing anything that would alter the answer now
  withdraws the old one.

### Changed
- A survey reports **why** books failed, not just how many. `crashed: 3` with
  nothing else is an alarm nobody can act on. Reasons are grouped by what went
  wrong and counted; paths are stripped out of them, and filenames still travel
  only with `--with-names`. The window shows them too, which is where they were
  missing.
- `schema` in a survey JSON is now `2`.

## 0.1.4 — pre-alpha

### Fixed
- **Entities a book declared for itself became visible text on the page.** A
  document may declare its own entities in the DOCTYPE's internal subset — a
  habit of DocBook and TeX pipelines, and of some publishers. EPUB 3 replaces
  that DOCTYPE with one declaring nothing, so the subset has to go; but the
  references stayed behind, resolved to nothing, and the ampersand was escaped.
  The reader saw `&mypauza;` where a dash belonged. Silently, in `preserve`
  mode, with a report entry about a different kind of entity entirely.

  They are now resolved before the subset is dropped, and by this tool rather
  than by the parser: handing it to libxml2 means turning `resolve_entities`
  back on, which is what shuts XXE and runaway expansion. External declarations
  are never resolved, nesting is bounded, and a document that tries to grow
  tenfold is refused whole. Both outcomes are reported.
- The K1 helper mis-parsed a *source* document carrying an internal subset:
  `lxml.html` cannot find `<body>` past one and returns the stray `]>` as text,
  so the invariant would have failed over punctuation while the real damage was
  identical on both sides and invisible.

### Added
- **The library, survey, inventory and corpus features are in the window**, not
  only on the command line. Three tabs: rebuild, library (survey or inventory
  over a folder), and corpus (record signatures, or check against them). The
  long jobs run off the UI thread with progress, and nothing is written beside
  anybody's books.
- `epubforge/corpus.py` and `epubforge corpus` — the corpus was previously a
  pytest fixture, which meant the person holding the books needed a checkout to
  help. It is a feature now; the test suite is a thin wrapper over it.

### Changed
- **The window scales.** It asked for a fixed 1180×760, which opens taller than
  a 1366×768 laptop screen; it now takes a share of the available desktop with
  a floor low enough for the layout to survive. The options column sits in a
  scroll area rather than being cut off — with the run button inside it — and
  neither splitter can collapse a panel to nothing.
- The title said "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E.", because
  Qt appends `applicationDisplayName` to a title that already carried the name.
- The status line follows the tab. "Drop EPUB files anywhere in this window" is
  good advice on one tab and untrue on the other two.

## 0.1.3 — pre-alpha

The first release driven by data from a real library rather than from reasoning
about one. A survey of 32 books arrived, and it immediately said two things.

### Added
- `epubforge inventory` — what the books *are*, as against what the tool does to
  them. Provenance (traces of Calibre, InDesign, Word, a PDF conversion — as a
  list, since files are layered), damage counts, and a typographic census.
  A survey can only name defects the tool already knows about, so it cannot
  surprise anybody; an inventory is what says which rules are worth writing at
  all. Output is counts and character frequencies, keyed by a hash; `--map`
  writes the hash-to-filename mapping separately and is the only file that names
  anything.

  It reads through `read_epub` rather than scanning bytes, and that is the whole
  design. Three measurements are wrong by construction on raw markup and wrong
  in a way nobody notices, because a number that is too high still looks like a
  number: `&nbsp;` counted as six characters instead of one non-breaking space,
  source indentation counted as doubled spacing, and a hyphen before a line
  break read as evidence of the very thing that would license the riskiest rule
  we have planned. Tests pin each one.
- `Book.source_package` keeps the package document as it arrived. Half of what
  identifies a generator is written there — `calibre:series`, InDesign's
  identifiers — and the model has normalised it away by the time anything else
  could look.

### Removed
- The report no longer says a book has no print page numbers. Across 32 real
  books it fired on all 32, which is what an absence looks like when it is the
  norm rather than a defect: the publisher is the only one who can supply them,
  so the entry named a fact nobody could act on and pushed the findings that
  mattered further down the page. A finding that is always true is not a
  finding.
- The inventory does not count runs of ordinary spaces, though the sketch it
  grew from did. HTML collapses whitespace, so a double space is invisible to a
  reader and cannot be damage; counting it on markup measures how the file was
  indented and nothing else.

## 0.1.2 — pre-alpha

### Fixed
- `docs/KORPUS.md` told the reader to run `epubforge survey`, which does not
  work after installing: the application directory is not on `PATH`, so the
  command that the whole document is built around fails with "not recognised".
  The document also interleaved two different procedures — one needing only the
  installed application, one needing a Python checkout — without saying which
  was which, so there was no way to follow it end to end. It is now split into
  two labelled paths with numbered steps, and every command is one that works
  as written.
- The installer adds a Start-menu shortcut opening a prompt with the
  application on `PATH` for that window. Scoped to the session deliberately:
  editing the real `PATH` is a change to somebody's machine and this needs no
  such thing.

## 0.1.1 — pre-alpha

A third audit, and the structural conclusion it reached is worth more than any
individual fix: **the model is a contract.** The rebuild emits the package
document from the model, which is what makes the output correct however broken
the input was — and the price is that a construct never read into the model
disappears without a trace. No warning, no report entry, no validator error,
because the result is perfectly valid. Just poorer. That is K12, and it now has
a test that can see it.

### Fixed
- **The reading direction was lost in every mode, including `minimal`.**
  `page-progression-direction` was not read or written anywhere, so a Hebrew,
  Arabic or manga edition came out opening the wrong way — silently, in the one
  mode that promises to touch nothing. `package/@dir` went with it. Everything
  expressed as `<meta>` survived a rebuild and everything expressed as an
  attribute of a structural element did not; no test could tell the difference
  because both outputs were valid EPUB.
- **Transliterated titles and names were dropped.** `alternate-script` is how a
  library catalogue links "Natsume Sōseki" to 夏目漱石. After the previous
  release, `_read_collection` was the only reader of refinements, and the code
  said as much in a comment — a true statement that turned out to cost
  something.
- **Running out of the archive budget produced half a book instead of a
  refusal.** The whole-archive budget was passed to the per-entry limit, so
  exhausting it looked like a run of oversized entries: the loop continued, four
  of six images vanished, the result was a valid EPUB, and the fifth image was
  blamed for "expanding past the limit" when it was an ordinary one megabyte.
  The two are different questions and now have different answers — a monstrous
  entry is skipped, an exhausted budget refuses the book. A regression the
  0.8.1 fix introduced.
- `page-spread-center` without its `rendition:` prefix is EPUB 3.0 spelling and
  an undefined property in 3.3. Found by the new fixture, and it made the
  output invalid for any book written to the older specification.
- `dc:type`, `dc:coverage` and `dc:relation` are carried through instead of
  dropped. They had no field in the model, which is not a reason to discard a
  publisher's statement about their own work.

### Added
- `epubforge survey` — what breaks across a whole library, ranked by how many
  books show each defect, writing nothing. A hundred separate reports are a
  hundred things to read; this is one answer to the question of what to fix
  next. Findings are normalised before counting, so "corrected 5 declarations"
  and "corrected 12" are one row rather than two. **Filenames are omitted unless
  `--with-names` is given**: a survey is meant to be shareable, and a list of
  titles says more about a shelf than about the tool.
- `tests/kitchen_sink.py` and `tests/test_package_completeness.py`: a package
  carrying one of everything EPUB 3.3 §5 allows, and a test comparing the
  constructs going in against those coming out. Whatever disappears must be
  repaired or listed with a reason — and two further tests keep the list honest,
  one rejecting an entry without a reason and one rejecting an entry for
  something the fixture never had.
- K12 in `CONTRIBUTING.md`, completing a set: K4 governs what the tool claims on
  the way out, K11 what it believes on the way in, K12 what it drops in between.
- A note on the **scope of K1**: it is a character-stream invariant, so it
  cannot see two paragraphs merged into one. That matters at the typography
  stage, where joining paragraphs broken by a PDF conversion is planned and is
  among the riskiest things this tool could do. Corpus signatures now record a
  block count, so such a change has somewhere to show up.
- `docs/KORPUS.md` — how to put a personal library to work without a single book
  leaving the disk.
- The test suite runs a second time under a different `PYTHONHASHSEED` in CI.
  Iterating a set is the classic way for K2 to quietly stop holding, and a
  single-process run can never notice.

## 0.1.0 — pre-alpha

### Changed
- **Version reset to 0.1.0, and maturity moved out of the number.** Two earlier
  schemes both used MINOR as a measure of how much had been built, so a day's
  work put the tool at 0.8 — which reads as four fifths of the way to a release
  it is nowhere near. The second attempt slowed the increments and left the
  inflated number in place, which fixed the symptom.

  The number now counts releases and nothing else: PATCH moves on every one,
  with no judgement call to make. Maturity is a separate word, `__stage__`,
  shown wherever the version is shown — `epub-forge 0.1.0 (pre-alpha)` — and
  MINOR moves only when that word does, against written entry conditions for
  alpha, beta and 1.0. Nothing had been tagged or released under the old
  numbers, so nothing points at them.

  Everything below this line was built during 0.1.x; the old headings are kept
  as written rather than rewritten, since they are a record of what happened.

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
